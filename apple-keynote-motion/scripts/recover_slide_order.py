#!/usr/bin/env python3
"""Recover Keynote slide navigator order from a .key archive.

Read-only parser for the WWDC20 study deck. It decodes Snappy-framed .iwa
members, performs minimal schema-less protobuf parsing, and joins the
Document.iwa navigator records to Index/Slide*.iwa files.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.util
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from csv_safety import spreadsheet_safe_row
from keynote_archive import KeynoteArchive
from keynote_effects import TRANSITION_EFFECTS


PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{4,}")
MAX_DECODED_CHUNK_BYTES = 256 * 1024 * 1024
MAX_DECODED_IWA_BYTES = 512 * 1024 * 1024


class Snappy:
    def __init__(self) -> None:
        lib_path = ctypes.util.find_library("snappy") or "/opt/homebrew/lib/libsnappy.dylib"
        try:
            self.lib = ctypes.CDLL(lib_path)
        except OSError as exc:
            raise RuntimeError(
                "libsnappy is required to decode Keynote .iwa files. "
                "Install snappy with Homebrew or make libsnappy discoverable. "
                f"Attempted: {lib_path}"
            ) from exc
        self.lib.snappy_uncompressed_length.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.lib.snappy_uncompressed_length.restype = ctypes.c_int
        self.lib.snappy_uncompress.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.lib.snappy_uncompress.restype = ctypes.c_int

    def uncompress(self, data: bytes) -> bytes:
        out_len = ctypes.c_size_t()
        rc = self.lib.snappy_uncompressed_length(data, len(data), ctypes.byref(out_len))
        if rc != 0:
            raise RuntimeError(f"snappy_uncompressed_length failed: {rc}")
        if out_len.value > MAX_DECODED_CHUNK_BYTES:
            raise RuntimeError(
                "decoded Snappy chunk exceeds the 256 MiB safety limit: "
                f"{out_len.value} bytes"
            )
        out = ctypes.create_string_buffer(out_len.value)
        rc = self.lib.snappy_uncompress(data, len(data), out, ctypes.byref(out_len))
        if rc != 0:
            raise RuntimeError(f"snappy_uncompress failed: {rc}")
        return out.raw[: out_len.value]


def decompress_iwa(data: bytes, snappy: Snappy) -> bytes:
    pos = 0
    decoded_size = 0
    chunks: list[bytes] = []
    while pos < len(data):
        if len(data) - pos < 4:
            raise RuntimeError("truncated IWA chunk header")
        chunk_type = data[pos]
        chunk_len = data[pos + 1] | (data[pos + 2] << 8) | (data[pos + 3] << 16)
        pos += 4
        if chunk_len > len(data) - pos:
            raise RuntimeError(
                f"truncated IWA chunk payload: declared {chunk_len} bytes, "
                f"found {len(data) - pos}"
            )
        chunk = data[pos : pos + chunk_len]
        pos += chunk_len
        decoded_chunk = snappy.uncompress(chunk) if chunk_type == 0 else chunk
        decoded_size += len(decoded_chunk)
        if decoded_size > MAX_DECODED_IWA_BYTES:
            raise RuntimeError("decoded IWA payload exceeds the 512 MiB safety limit")
        chunks.append(decoded_chunk)
    return b"".join(chunks)


def read_varint(buf: bytes, pos: int, end: int | None = None) -> tuple[int, int]:
    if end is None:
        end = len(buf)
    value = 0
    shift = 0
    while pos < end:
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")
    raise EOFError("unterminated varint")


def parse_fields(buf: bytes) -> list[tuple[int, int, int, int | bytes]]:
    pos = 0
    out: list[tuple[int, int, int, int | bytes]] = []
    while pos < len(buf):
        start = pos
        key, pos = read_varint(buf, pos)
        field = key >> 3
        wire_type = key & 7
        if wire_type == 0:
            value, pos = read_varint(buf, pos)
        elif wire_type == 1:
            value = buf[pos : pos + 8]
            pos += 8
        elif wire_type == 2:
            size, pos = read_varint(buf, pos)
            value = buf[pos : pos + size]
            pos += size
        elif wire_type == 5:
            value = buf[pos : pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wire_type} at {start}")
        if pos > len(buf):
            raise ValueError("field overran buffer")
        out.append((start, field, wire_type, value))
    return out


def parse_fields_partial(buf: bytes) -> list[tuple[int, int, int, int | bytes]]:
    """Return valid leading protobuf fields and stop at trailing record noise."""

    pos = 0
    out: list[tuple[int, int, int, int | bytes]] = []
    while pos < len(buf):
        start = pos
        try:
            key, pos = read_varint(buf, pos)
            field = key >> 3
            wire_type = key & 7
            if wire_type == 0:
                value, pos = read_varint(buf, pos)
            elif wire_type == 1:
                value = buf[pos : pos + 8]
                pos += 8
            elif wire_type == 2:
                size, pos = read_varint(buf, pos)
                value = buf[pos : pos + size]
                pos += size
            elif wire_type == 5:
                value = buf[pos : pos + 4]
                pos += 4
            else:
                break
            if pos > len(buf):
                break
            out.append((start, field, wire_type, value))
        except (EOFError, ValueError):
            break
    return out


def all_varints(buf: bytes) -> list[int]:
    values: list[int] = []
    pos = 0
    while pos < len(buf):
        value, pos = read_varint(buf, pos)
        values.append(value)
    return values


def archive_header_at(buf: bytes, off: int) -> tuple[int, int, int, int, int, list] | None:
    try:
        header_len, payload_start = read_varint(buf, off)
    except Exception:
        return None
    payload_end = payload_start + header_len
    if header_len <= 0 or payload_end > len(buf) or header_len > 10000:
        return None
    try:
        fields = parse_fields(buf[payload_start:payload_end])
    except Exception:
        return None
    if len(fields) < 2:
        return None
    if not (fields[0][1] == 1 and fields[0][2] == 0):
        return None
    if not (fields[1][1] == 2 and fields[1][2] == 2 and isinstance(fields[1][3], bytes)):
        return None
    try:
        meta_fields = parse_fields(fields[1][3])
    except Exception:
        return None
    has_iwa_marker = any(
        field == 2 and wire == 2 and value == b"\x01\x00\x05"
        for _, field, wire, value in meta_fields
    )
    if not has_iwa_marker:
        return None
    return off, payload_start, payload_end, header_len, int(fields[0][3]), meta_fields


def ids_from_meta(meta_fields: list) -> list[int]:
    for _, field, wire, value in meta_fields:
        if field == 5 and wire == 2 and isinstance(value, bytes):
            return all_varints(value)
    return []


def ref_value(value: int | bytes) -> int | None:
    if not isinstance(value, bytes) or len(value) > 10:
        return None
    try:
        fields = parse_fields(value)
    except Exception:
        return None
    if len(fields) == 1 and fields[0][1] == 1 and fields[0][2] == 0:
        return int(fields[0][3])
    return None


def first_ref_field(payload: bytes, field_number: int) -> int | None:
    for _, field, wire, value in parse_fields_partial(payload):
        if field == field_number and wire == 2:
            ref = ref_value(value)
            if ref is not None:
                return ref
    return None


def ordered_refs_from_field(payload: bytes, container_field: int, repeated_field: int) -> list[int]:
    for _, field, wire, value in parse_fields(payload):
        if field != container_field or wire != 2 or not isinstance(value, bytes):
            continue
        refs: list[int] = []
        for _, inner_field, inner_wire, inner_value in parse_fields(value):
            if inner_field == repeated_field and inner_wire == 2:
                ref = ref_value(inner_value)
                if ref is not None:
                    refs.append(ref)
        return refs
    return []


def normalize_string(text: str) -> str:
    apple_index = text.find("apple:")
    if apple_index > 0 and not any(ch.isalnum() for ch in text[:apple_index]):
        return text[apple_index:]
    return text.strip()


def slide_transition_and_topic(decoded_slide: bytes) -> tuple[str, str]:
    strings = [
        normalize_string(match.group().decode("utf-8", errors="ignore"))
        for match in PRINTABLE_RE.finditer(decoded_slide)
    ]
    transition = "unknown"
    for idx, value in enumerate(strings):
        if value != "Transition":
            continue
        for follow in strings[idx + 1 : idx + 8]:
            if follow == "none" or follow in TRANSITION_EFFECTS or follow.startswith("apple:magic-move"):
                transition = follow
                break
        if transition != "unknown":
            break
    text_values: list[str] = []
    for value in strings:
        if value.startswith("apple:") or value in {
            "Transition",
            "All at Once",
            "Action",
            "decimal",
            "none",
            "zh-Hans",
        }:
            continue
        if len(value) < 2 or sum(ch.isalpha() for ch in value) == 0:
            continue
        if value not in text_values:
            text_values.append(value)
    return transition, " | ".join(text_values[:5])


def recover(deck: Path) -> dict:
    if not deck.is_file():
        raise FileNotFoundError(f"Deck does not exist: {deck}")
    if not zipfile.is_zipfile(deck):
        raise ValueError(f"Deck is not a readable zip-style .key archive: {deck}")
    snappy = Snappy()
    slide_by_id: dict[int, str] = {}
    slide_motion: dict[int, tuple[str, str]] = {}

    with KeynoteArchive(deck) as archive:
        for name in archive.namelist():
            if not (name.startswith("Index/Slide") and name.endswith(".iwa")):
                continue
            decoded = decompress_iwa(archive.read(name), snappy)
            header_len, payload_start = read_varint(decoded, 0)
            header = decoded[payload_start : payload_start + header_len]
            slide_id = int(parse_fields(header)[0][3])
            slide_by_id[slide_id] = name
            slide_motion[slide_id] = slide_transition_and_topic(decoded)

        document = decompress_iwa(archive.read("Index/Document.iwa"), snappy)
        archive_layout = archive.layout
        package_prefix = archive.package_prefix

    root_header = archive_header_at(document, 0)
    if root_header is None:
        raise RuntimeError("Could not parse root Document.iwa archive header")
    root_ids = ids_from_meta(root_header[5])

    root_known = set([root_header[4], *root_ids])
    root_headers = [
        header
        for off in range(len(document))
        if (header := archive_header_at(document, off)) and header[4] in root_known
    ]
    root_headers.sort(key=lambda item: item[0])
    root_payload_end = root_headers[1][0] if len(root_headers) > 1 else len(document)
    root_payload = document[root_header[2] : root_payload_end]
    navigator_object_id = first_ref_field(root_payload, 2)
    if navigator_object_id is None:
        raise RuntimeError("Could not find navigator object reference in Document.iwa root payload")

    navigator_header = next(
        (header for header in root_headers if header[4] == navigator_object_id),
        None,
    )
    if navigator_header is None:
        raise RuntimeError(f"Could not find navigator object header {navigator_object_id}")

    child_ids = ids_from_meta(navigator_header[5])
    child_id_set = set(child_ids)
    child_headers = []
    seen_offsets: set[int] = set()
    for off in range(navigator_header[2], len(document)):
        header = archive_header_at(document, off)
        if header and header[4] in child_id_set and header[0] not in seen_offsets:
            seen_offsets.add(header[0])
            child_headers.append(header)
    child_headers.sort(key=lambda item: item[0])

    all_records = [navigator_header, *child_headers]
    payload_by_id: dict[int, bytes] = {}
    for idx, header in enumerate(all_records):
        next_off = all_records[idx + 1][0] if idx + 1 < len(all_records) else len(document)
        payload_by_id[header[4]] = document[header[2] : next_off]

    navigator_payload = payload_by_id[navigator_object_id]
    ordered_node_ids = ordered_refs_from_field(navigator_payload, 3, 2)
    rows: list[dict] = []
    for index, node_id in enumerate(ordered_node_ids, start=1):
        node_payload = payload_by_id[node_id]
        slide_id = first_ref_field(node_payload, 2)
        if slide_id is None:
            raise RuntimeError(f"Navigator node {node_id} has no field-2 slide reference")
        archive_name = slide_by_id.get(slide_id)
        if archive_name is None:
            raise RuntimeError(f"Slide object {slide_id} from node {node_id} has no Slide*.iwa file")
        transition, topic = slide_motion[slide_id]
        rows.append(
            {
                "slide_number": index,
                "navigator_node_id": node_id,
                "slide_object_id": slide_id,
                "archive_name": archive_name,
                "transition": transition,
                "topic": topic,
            }
        )

    ordered_slide_ids = {row["slide_object_id"] for row in rows}
    missing_slides = [
        {"slide_object_id": slide_id, "archive_name": name}
        for slide_id, name in sorted(slide_by_id.items())
        if slide_id not in ordered_slide_ids
    ]

    return {
        "deck": str(deck),
        "archive_layout": archive_layout,
        "package_prefix": package_prefix,
        "document_root_id": root_header[4],
        "navigator_object_id": navigator_object_id,
        "navigator_child_id_count": len(child_ids),
        "navigator_node_count": len(ordered_node_ids),
        "slide_file_count": len(slide_by_id),
        "ordered_slide_count": len(rows),
        "missing_slides": missing_slides,
        "transition_counts": dict(Counter(row["transition"] for row in rows)),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deck", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()

    args.deck = args.deck.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    result = recover(args.deck)

    csv_path = out_dir / "slide-order.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "slide_number",
                "navigator_node_id",
                "slide_object_id",
                "archive_name",
                "transition",
                "topic",
            ],
        )
        writer.writeheader()
        writer.writerows(spreadsheet_safe_row(row) for row in result["rows"])

    transition_rows = [row for row in result["rows"] if row["transition"] != "none"]
    transition_csv_path = out_dir / "transition-slides-ordered.csv"
    with transition_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "slide_number",
                "navigator_node_id",
                "slide_object_id",
                "archive_name",
                "transition",
                "topic",
            ],
        )
        writer.writeheader()
        writer.writerows(spreadsheet_safe_row(row) for row in transition_rows)

    magic_move_csv_path = out_dir / "magic-move-slides-ordered.csv"
    with magic_move_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "slide_number",
                "navigator_node_id",
                "slide_object_id",
                "archive_name",
                "transition",
                "topic",
            ],
        )
        writer.writeheader()
        writer.writerows(
            spreadsheet_safe_row(row)
            for row in transition_rows
            if row["transition"] == "apple:magic-move-implied-motion-path"
        )

    summary = {key: value for key, value in result.items() if key != "rows"}
    (out_dir / "slide-order-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
