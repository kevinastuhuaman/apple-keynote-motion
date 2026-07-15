#!/usr/bin/env python3
"""Normalized read-only access to direct and wrapped Keynote archives."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from zipfile import ZipFile, ZipInfo, is_zipfile


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    size: int
    compressed: int
    source: str
    info: ZipInfo


class KeynoteArchive:
    """Expose a Keynote package as normalized package-relative members.

    Most `.key` files store `Index/*.iwa` and `Data/*` directly. Some shared
    Apple event archives wrap a full package inside `<name>.key_backup/`, with
    the IWA index stored in a nested `Index.zip`. This class supports both
    without extracting either archive.
    """

    def __init__(self, deck: Path) -> None:
        self.deck = Path(deck)
        self.outer: ZipFile | None = None
        self.index: ZipFile | None = None
        self._nested_bytes: BytesIO | None = None
        self._members: dict[str, ArchiveMember] = {}
        self.layout = "unknown"
        self.package_prefix = ""
        self.outer_entry_count = 0
        self.index_entry_count = 0

    def __enter__(self) -> "KeynoteArchive":
        if not self.deck.is_file():
            raise FileNotFoundError(f"Deck does not exist: {self.deck}")
        if not is_zipfile(self.deck):
            raise ValueError(f"Deck is not a readable zip-style .key archive: {self.deck}")

        try:
            return self._open()
        except BaseException:
            try:
                self.__exit__(None, None, None)
            except Exception:
                pass
            raise

    def _open(self) -> "KeynoteArchive":
        self.outer = ZipFile(self.deck)
        outer_names = set(self.outer.namelist())
        self.outer_entry_count = len(outer_names)

        if "Index/Document.iwa" in outer_names:
            self.index = self.outer
            self.layout = "direct"
            self._members = {
                info.filename: ArchiveMember(
                    name=info.filename,
                    size=info.file_size,
                    compressed=info.compress_size,
                    source="outer",
                    info=info,
                )
                for info in self.outer.infolist()
            }
            self.index_entry_count = sum(
                1 for name in outer_names if name.startswith("Index/")
            )
            return self

        candidates = sorted(
            name for name in outer_names if name == "Index.zip" or name.endswith("/Index.zip")
        )
        for candidate in candidates:
            nested_bytes = BytesIO(self.outer.read(candidate))
            nested: ZipFile | None = None
            try:
                nested = ZipFile(nested_bytes)
                has_document = "Index/Document.iwa" in set(nested.namelist())
            except Exception:
                try:
                    if nested is not None:
                        nested.close()
                finally:
                    nested_bytes.close()
                continue
            if not has_document:
                try:
                    nested.close()
                finally:
                    nested_bytes.close()
                continue

            self.index = nested
            self._nested_bytes = nested_bytes
            self.layout = "wrapped-index-zip"
            self.package_prefix = candidate[: -len("Index.zip")]
            break

        if self.index is None:
            raise ValueError(
                "Keynote archive has neither top-level Index/Document.iwa nor a valid Index.zip"
            )

        members: dict[str, ArchiveMember] = {}
        for info in self.outer.infolist():
            if not info.filename.startswith(self.package_prefix):
                continue
            normalized = info.filename[len(self.package_prefix) :]
            if not normalized or normalized == "Index.zip":
                continue
            members[normalized] = ArchiveMember(
                name=normalized,
                size=info.file_size,
                compressed=info.compress_size,
                source="outer",
                info=info,
            )

        for info in self.index.infolist():
            members[info.filename] = ArchiveMember(
                name=info.filename,
                size=info.file_size,
                compressed=info.compress_size,
                source="index",
                info=info,
            )

        self._members = members
        self.index_entry_count = len(self.index.infolist())
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        resources = (
            self.index if self.index is not self.outer else None,
            self.outer,
            self._nested_bytes,
        )
        first_error: Exception | None = None
        try:
            for resource in resources:
                if resource is None:
                    continue
                try:
                    resource.close()
                except Exception as error:
                    if first_error is None:
                        first_error = error
        finally:
            self.index = None
            self.outer = None
            self._nested_bytes = None

        if first_error is not None and exc_type is None:
            raise first_error

    def infolist(self) -> list[ArchiveMember]:
        return list(self._members.values())

    def namelist(self) -> list[str]:
        return list(self._members)

    def getinfo(self, name: str) -> ArchiveMember:
        try:
            return self._members[name]
        except KeyError as exc:
            raise KeyError(f"No normalized package member named {name}") from exc

    def open(self, member: ArchiveMember | str) -> BinaryIO:
        selected = self.getinfo(member) if isinstance(member, str) else member
        if selected.source == "index":
            if self.index is None:
                raise RuntimeError("Archive is closed")
            return self.index.open(selected.info)
        if self.outer is None:
            raise RuntimeError("Archive is closed")
        return self.outer.open(selected.info)

    def read(self, member: ArchiveMember | str) -> bytes:
        with self.open(member) as stream:
            return stream.read()
