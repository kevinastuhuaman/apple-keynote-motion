#!/usr/bin/env python3
"""Patch one native Keynote BuildChunk start relationship in a deck copy.

This edits only the `automatic` and `referent` flags on one caller-specified
KN.BuildChunkArchive record. It never writes in place. The output must still
pass a Keynote reopen/save round trip, native timeline extraction, and rendered
playback QA before it is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


START_FLAGS = {
    "on-click": (False, True),
    "after-build": (True, True),
    "with-build": (True, False),
}


def require_iwa_file():
    try:
        from keynote_parser.codec import IWAFile
    except ImportError as exc:
        raise RuntimeError(
            "keynote-parser is required for native BuildChunk edits. Install it "
            "in an isolated environment with: python -m pip install keynote-parser"
        ) from exc
    return IWAFile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def patch_member(
    raw: bytes,
    *,
    member: str,
    chunk_identifier: str,
    mode: str,
) -> tuple[bytes, dict[str, object]]:
    automatic, referent = START_FLAGS[mode]
    iwa = require_iwa_file().from_buffer(raw, member)
    matches = []

    for compressed_chunk in iwa.chunks:
        for segment in compressed_chunk.archives:
            if str(segment.header.identifier) != chunk_identifier:
                continue
            for obj in segment.objects:
                descriptor = getattr(type(obj), "DESCRIPTOR", None)
                pbtype = getattr(descriptor, "full_name", None)
                if pbtype != "KN.BuildChunkArchive":
                    continue
                before = {
                    "automatic": bool(getattr(obj, "automatic", False)),
                    "referent": bool(getattr(obj, "referent", False)),
                }
                obj.automatic = automatic
                obj.referent = referent
                matches.append(
                    {
                        "segment_identifier": chunk_identifier,
                        "pbtype": pbtype,
                        "before": before,
                        "after": {
                            "automatic": automatic,
                            "referent": referent,
                        },
                    }
                )

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one KN.BuildChunkArchive {chunk_identifier} in "
            f"{member}; found {len(matches)}"
        )

    return iwa.to_buffer(), matches[0]


def patch_deck(
    source: Path,
    output: Path,
    *,
    member: str,
    chunk_identifier: str,
    mode: str,
) -> dict[str, object]:
    if source.resolve() == output.resolve():
        raise ValueError("Output must be a new deck path; in-place edits are disabled")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")

    with zipfile.ZipFile(source, "r") as source_zip:
        if member not in source_zip.namelist():
            raise KeyError(f"Archive member not found: {member}")
        patched_member, change = patch_member(
            source_zip.read(member),
            member=member,
            chunk_identifier=chunk_identifier,
            mode=mode,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w") as output_zip:
            output_zip.comment = source_zip.comment
            for info in source_zip.infolist():
                payload = patched_member if info.filename == member else source_zip.read(info)
                output_zip.writestr(info, payload)

    return {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "member": member,
        "chunk_identifier": chunk_identifier,
        "mode": mode,
        "change": change,
        "source_sha256": sha256(source),
        "output_sha256": sha256(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--member", required=True)
    parser.add_argument("--chunk-identifier", required=True)
    parser.add_argument("--mode", choices=sorted(START_FLAGS), required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = patch_deck(
        args.source,
        args.output,
        member=args.member,
        chunk_identifier=args.chunk_identifier,
        mode=args.mode,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
