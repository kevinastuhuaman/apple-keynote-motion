#!/usr/bin/env python3
"""Query a private library created by build_private_asset_library.py."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--query")
    parser.add_argument("--deck")
    parser.add_argument("--slide", type=int, action="append", help="Source slide number; repeat for any-match lookup")
    parser.add_argument("--sha256", help="Exact SHA-256 or unique leading prefix")
    parser.add_argument("--kind", choices=("image", "video", "audio", "document", "other"))
    parser.add_argument("--category")
    parser.add_argument("--orientation", choices=("landscape", "portrait", "square"))
    parser.add_argument("--min-width", type=int)
    parser.add_argument("--min-height", type=int)
    parser.add_argument("--with-alpha", action="store_true")
    parser.add_argument("--has-preview", action="store_true")
    parser.add_argument("--exclude-small", action="store_true")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    database = args.library.expanduser().resolve()
    if database.is_dir():
        database = database / "catalog.sqlite"
    if not database.is_file():
        parser.error(f"catalog not found: {database}")
    root = database.parent

    clauses: list[str] = []
    values: list[object] = []
    if args.query:
        clauses.append(
            "lower(coalesce(o.preferred_name,'') || ' ' || o.recovered_name || ' ' || o.category || ' ' || o.tags_json) LIKE ?"
        )
        values.append(f"%{args.query.casefold()}%")
    if args.slide:
        placeholders = ",".join("?" for _ in args.slide)
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(o.slide_numbers_json) AS source_slide "
            f"WHERE CAST(source_slide.value AS INTEGER) IN ({placeholders}))"
        )
        values.extend(args.slide)
    if args.sha256:
        sha_value = args.sha256.casefold()
        if len(sha_value) == 64:
            clauses.append("lower(b.sha256) = ?")
            values.append(sha_value)
        else:
            clauses.append("lower(b.sha256) LIKE ?")
            values.append(f"{sha_value}%")
    for column, value in (
        ("o.deck_id", args.deck),
        ("b.kind", args.kind),
        ("o.category", args.category),
        ("b.orientation", args.orientation),
    ):
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)
    if args.min_width:
        clauses.append("b.width >= ?")
        values.append(args.min_width)
    if args.min_height:
        clauses.append("b.height >= ?")
        values.append(args.min_height)
    if args.with_alpha:
        clauses.append("b.has_alpha = 1")
    if args.has_preview:
        clauses.append("b.preview_path IS NOT NULL")
    if args.exclude_small:
        clauses.append("o.is_small_variant = 0")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    values.append(args.limit)

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        f"""
        SELECT o.deck_id, coalesce(o.preferred_name,o.recovered_name) AS name,
               o.archive_member, b.sha256,
               o.category, o.slide_numbers_json, b.kind, b.width, b.height,
               b.duration, b.codec, b.has_alpha, b.object_path, b.preview_path
        FROM occurrences o JOIN objects b ON o.sha256=b.sha256
        {where}
        ORDER BY o.is_small_variant, o.is_descriptive_name DESC, b.width DESC, b.size_bytes DESC
        LIMIT ?
        """,
        values,
    ).fetchall()
    connection.close()

    payload = []
    for row in rows:
        item = dict(row)
        item["slides"] = json.loads(item.pop("slide_numbers_json"))
        item["object_path"] = str(root / item["object_path"])
        item["preview_path"] = str(root / item["preview_path"]) if item["preview_path"] else None
        payload.append(item)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("| Deck | Name | Category | Dimensions / Duration | Slides | Object |")
    print("| --- | --- | --- | --- | --- | --- |")
    for row in payload:
        dimensions = (
            f"{row['width']}x{row['height']}"
            if row.get("width") and row.get("height")
            else f"{row['duration']:.1f}s"
            if row.get("duration")
            else ""
        )
        slides = ", ".join(map(str, row["slides"][:12]))
        print(
            f"| {row['deck_id']} | {str(row['name']).replace('|', '/')} | "
            f"{row['category']} | {dimensions} | {slides} | `{row['object_path']}` |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
