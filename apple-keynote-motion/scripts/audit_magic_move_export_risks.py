#!/usr/bin/env python3
"""Find zero-size drawable trees that can break Keynote Magic Move export.

Keynote 15.3 was observed asserting in KNMagicMoveMatchMaker when a morph match
requested a texture for a zero-width or zero-height bounding rectangle. This
read-only audit reports candidates; it does not claim every candidate fails.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from extract_native_build_timeline import (
    CrossFileRecordResolver,
    friendly_target_type,
    reference_identifier,
    target_geometry,
)
from keynote_archive import KeynoteArchive
from recover_slide_order import recover


PLACEHOLDER_FIELDS = (
    "bodyPlaceholder",
    "titlePlaceholder",
    "slideNumberPlaceholder",
)


def is_zero_geometry(geometry: dict[str, Any]) -> bool:
    width = geometry.get("width")
    height = geometry.get("height")
    return (width is not None and width <= 0) or (height is not None and height <= 0)


def iter_child_refs(data: dict[str, Any]) -> Iterable[tuple[int, str]]:
    for index, value in enumerate(data.get("children", [])):
        identifier = reference_identifier(value)
        if identifier:
            yield index, identifier


def walk_drawable(
    identifier: str,
    path: str,
    records: dict[str, dict[str, Any]],
    resolver: CrossFileRecordResolver,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    if visited is None:
        visited = set()
    if identifier in visited:
        return []
    visited.add(identifier)
    resolver.hydrate(identifier, records)
    record = records.get(identifier)
    if record is None:
        return [
            {
                "path": path,
                "identifier": identifier,
                "pbtype": None,
                "type": "unresolved",
                "geometry": None,
                "zero_size": False,
            }
        ]

    data = record["data"]
    geometry = target_geometry(data)
    rows = [
        {
            "path": path,
            "identifier": identifier,
            "pbtype": record["pbtype"],
            "type": friendly_target_type(record["pbtype"], data),
            "geometry": geometry,
            "zero_size": is_zero_geometry(geometry),
        }
    ]
    for child_index, child_identifier in iter_child_refs(data):
        rows.extend(
            walk_drawable(
                child_identifier,
                f"{path}/children[{child_index}]",
                records,
                resolver,
                visited,
            )
        )
    return rows


def slide_drawable_tree(
    member: str, resolver: CrossFileRecordResolver
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_records, _ = resolver.records_for_member(member)
    records = dict(source_records)
    slide_record = next(
        (record for record in records.values() if record["pbtype"] == "KN.SlideArchive"),
        None,
    )
    if slide_record is None:
        raise ValueError(f"No KN.SlideArchive in {member}")
    slide = slide_record["data"]
    rows: list[dict[str, Any]] = []
    for index, value in enumerate(slide.get("ownedDrawables", [])):
        identifier = reference_identifier(value)
        if identifier:
            rows.extend(
                walk_drawable(identifier, f"ownedDrawables[{index}]", records, resolver)
            )
    for field in PLACEHOLDER_FIELDS:
        identifier = reference_identifier(slide.get(field))
        if identifier:
            rows.extend(walk_drawable(identifier, field, records, resolver))
    transition_attributes = ((slide.get("transition") or {}).get("attributes") or {})
    return rows, transition_attributes


def paired_zero_paths(
    source: list[dict[str, Any]], destination: list[dict[str, Any]]
) -> list[str]:
    source_paths = {row["path"] for row in source if row["zero_size"]}
    destination_paths = {row["path"] for row in destination if row["zero_size"]}
    return sorted(source_paths & destination_paths)


def audit(deck: Path) -> dict[str, Any]:
    ordering = recover(deck)
    rows = ordering["rows"]
    findings: list[dict[str, Any]] = []
    with KeynoteArchive(deck) as archive:
        resolver = CrossFileRecordResolver(archive)
        resolver.build_index()
        for index, source_row in enumerate(rows[:-1]):
            if source_row["transition"] != "apple:magic-move-implied-motion-path":
                continue
            destination_row = rows[index + 1]
            source_tree, transition_attributes = slide_drawable_tree(
                source_row["archive_name"], resolver
            )
            destination_tree, _ = slide_drawable_tree(
                destination_row["archive_name"], resolver
            )
            source_zero = [row for row in source_tree if row["zero_size"]]
            destination_zero = [row for row in destination_tree if row["zero_size"]]
            paired = paired_zero_paths(source_tree, destination_tree)
            fade_unmatched = transition_attributes.get(
                "customMagicMoveFadeUnmatchedObjects"
            )
            if paired and fade_unmatched is True:
                severity = "high"
            elif paired and fade_unmatched is False:
                severity = "mitigated"
            elif source_zero or destination_zero:
                severity = "medium"
            else:
                severity = "none"
            findings.append(
                {
                    "source_document_slide": source_row["slide_number"],
                    "destination_document_slide": destination_row["slide_number"],
                    "source_archive": source_row["archive_name"],
                    "destination_archive": destination_row["archive_name"],
                    "risk": severity,
                    "fade_unmatched_objects": fade_unmatched,
                    "paired_zero_paths": paired,
                    "source_zero_size": source_zero,
                    "destination_zero_size": destination_zero,
                }
            )
    return {
        "schema_version": "1.0",
        "truth_standard": {
            "geometry": "native-observed",
            "risk": "inferred from a reproduced Keynote 15.3 export assertion",
        },
        "deck": str(deck),
        "keynote_failure_signature": (
            "KNMagicMoveMatchMaker zero width or height bounding rect for texture"
        ),
        "magic_move_pairs": len(findings),
        "high_risk_pairs": sum(row["risk"] == "high" for row in findings),
        "medium_risk_pairs": sum(row["risk"] == "medium" for row in findings),
        "mitigated_pairs": sum(row["risk"] == "mitigated" for row in findings),
        "findings": findings,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Magic Move Export Risk Audit",
        "",
        "Geometry is `native-observed`. Risk labels are `inferred` from a reproduced "
        "Keynote 15.3 movie-export assertion.",
        "",
        f"- Magic Move pairs: **{report['magic_move_pairs']}**",
        f"- High-risk paired zero paths: **{report['high_risk_pairs']}**",
        f"- Medium-risk unpaired zero objects: **{report['medium_risk_pairs']}**",
        f"- Paired zero paths with Fade Unmatched disabled: **{report['mitigated_pairs']}**",
        "",
        "| Pair | Risk | Fade unmatched | Paired zero paths | Source zero | Destination zero |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for finding in report["findings"]:
        lines.append(
            f"| {finding['source_document_slide']}→"
            f"{finding['destination_document_slide']} | {finding['risk']} | "
            f"{finding['fade_unmatched_objects']} | "
            f"{len(finding['paired_zero_paths'])} | "
            f"{len(finding['source_zero_size'])} | "
            f"{len(finding['destination_zero_size'])} |"
        )
    lines.extend(
        [
            "",
            "A flagged pair is not automatically broken. If native movie export fails, "
            "inspect paired paths first; test a scratch copy with Fade Unmatched Objects "
            "disabled before modifying any geometry.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    deck = args.deck.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = audit(deck)
    (output_dir / "magic-move-export-risks.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_markdown(output_dir / "magic-move-export-risks.md", report)
    print(
        json.dumps(
            {
                "magic_move_pairs": report["magic_move_pairs"],
                "high_risk_pairs": report["high_risk_pairs"],
                "medium_risk_pairs": report["medium_risk_pairs"],
                "mitigated_pairs": report["mitigated_pairs"],
                "output_dir": str(output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
