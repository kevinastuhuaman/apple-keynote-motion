#!/usr/bin/env python3
"""Aggregate normalized archive and native-motion reports for many Keynote decks."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(corpus_root: Path) -> list[dict[str, Any]]:
    inventory_root = corpus_root / "inventory"
    native_root = corpus_root / "native-motion"
    rows: list[dict[str, Any]] = []

    for inventory_path in sorted(inventory_root.glob("*/archive-summary.json")):
        slug = inventory_path.parent.name
        native_path = native_root / slug / "native-motion-summary.json"
        order_path = native_root / slug / "slide-order" / "slide-order-summary.json"
        if not native_path.exists():
            continue

        inventory = read_json(inventory_path)
        native = read_json(native_path)
        order = read_json(order_path) if order_path.exists() else {}
        slides = native.get("slides_archive_sorted", [])
        transition_counts = native.get("transition_counts", {})
        motion_classes = native.get("motion_class_counts", {})

        slides_with_builds = sum(bool(slide.get("build_effects")) for slide in slides)
        slides_with_actions = sum(bool(slide.get("action_effects")) for slide in slides)
        slides_with_media = sum(bool(slide.get("media_triggers")) for slide in slides)
        slides_with_structural_motion = sum(
            bool(slide.get("build_effects") or slide.get("action_effects")) for slide in slides
        )
        slides_with_any_motion = sum(
            bool(
                slide.get("transition") not in {None, "none", "unknown"}
                or slide.get("build_effects")
                or slide.get("action_effects")
            )
            for slide in slides
        )

        known_common = {
            "none",
            "unknown",
            "apple:magic-move-implied-motion-path",
            "apple:dissolve",
            "apple:push",
            "apple:ca-dissolve-and-flip",
        }
        rare_transitions = {
            name: count
            for name, count in transition_counts.items()
            if name not in known_common and count
        }

        slide_count = int(order.get("ordered_slide_count", native.get("slide_count", 0)))
        rows.append(
            {
                "slug": slug,
                "deck_name": Path(inventory.get("deck", slug)).name,
                "archive_layout": inventory.get("archive_layout", native.get("archive_layout")),
                "size_bytes": int(inventory.get("deck_size_bytes", 0)),
                "slide_count": slide_count,
                "transition_slide_count": int(native.get("transition_slide_count", 0)),
                "magic_move": int(
                    transition_counts.get("apple:magic-move-implied-motion-path", 0)
                ),
                "dissolve": int(transition_counts.get("apple:dissolve", 0)),
                "push": int(transition_counts.get("apple:push", 0)),
                "object_flip": int(
                    transition_counts.get("apple:ca-dissolve-and-flip", 0)
                ),
                "rare_transitions": rare_transitions,
                "slides_with_builds": slides_with_builds,
                "slides_with_actions": slides_with_actions,
                "slides_with_structural_motion": slides_with_structural_motion,
                "slides_with_media": slides_with_media,
                "slides_with_any_motion": slides_with_any_motion,
                "motion_density": (
                    round(slides_with_any_motion / slide_count, 4) if slide_count else 0
                ),
                "static_class_count": int(motion_classes.get("STATIC", 0)),
                "unknown_transition_count": int(transition_counts.get("unknown", 0)),
            }
        )
    return rows


def write_outputs(rows: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus-summary.json").write_text(
        json.dumps({"deck_count": len(rows), "decks": rows}, indent=2), encoding="utf-8"
    )

    fieldnames = [
        "slug",
        "deck_name",
        "archive_layout",
        "size_bytes",
        "slide_count",
        "transition_slide_count",
        "magic_move",
        "dissolve",
        "push",
        "object_flip",
        "rare_transitions",
        "slides_with_builds",
        "slides_with_actions",
        "slides_with_structural_motion",
        "slides_with_media",
        "slides_with_any_motion",
        "motion_density",
        "static_class_count",
        "unknown_transition_count",
    ]
    with (out_dir / "corpus-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["rare_transitions"] = json.dumps(
                row["rare_transitions"], sort_keys=True
            )
            writer.writerow(csv_row)

    lines = [
        "# Keynote Reference Corpus",
        "",
        "Counts below are archive-derived motion signals, not verified build instances.",
        "",
        "| Deck | Slides | MM | Dissolve | Push | Flip | Build slides | Action slides | Motion density |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(rows, key=lambda item: (-item["motion_density"], item["slug"])):
        lines.append(
            f"| {row['slug']} | {row['slide_count']} | {row['magic_move']} | "
            f"{row['dissolve']} | {row['push']} | {row['object_flip']} | "
            f"{row['slides_with_builds']} | {row['slides_with_actions']} | "
            f"{row['motion_density']:.1%} |"
        )
    (out_dir / "corpus-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    rows = build_rows(args.corpus_root.expanduser().resolve())
    if not rows:
        parser.error("no paired inventory/native-motion reports found")
    write_outputs(rows, args.out_dir.expanduser().resolve())
    print(json.dumps({"deck_count": len(rows), "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
