#!/usr/bin/env python3
"""Analyze text continuity and text builds from exported Keynote artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from csv_safety import spreadsheet_safe_row

try:
    from .analyze_transition_object_diffs import (
        AnalysisError,
        Diagnostics,
        MotionIndex,
        ObjectDataset,
        HORIZONTAL_SIZE_TOLERANCE_RATIO,
        POSITION_TOLERANCE_RATIO,
        VERTICAL_SIZE_TOLERANCE_RATIO,
        SlideSize,
        clean_display_text,
        load_motion_classes,
        load_objects,
        load_transitions,
        match_cost,
        match_exact_buckets,
        minimum_cost_eligible_pairs,
        normalized_size_delta,
        object_sort_key,
        pair_distance,
        positive_float_argument,
        remove_pairs,
        resolved_path,
    )
except ImportError:
    from analyze_transition_object_diffs import (
        AnalysisError,
        Diagnostics,
        MotionIndex,
        ObjectDataset,
        HORIZONTAL_SIZE_TOLERANCE_RATIO,
        POSITION_TOLERANCE_RATIO,
        VERTICAL_SIZE_TOLERANCE_RATIO,
        SlideSize,
        clean_display_text,
        load_motion_classes,
        load_objects,
        load_transitions,
        match_cost,
        match_exact_buckets,
        minimum_cost_eligible_pairs,
        normalized_size_delta,
        object_sort_key,
        pair_distance,
        positive_float_argument,
        remove_pairs,
        resolved_path,
    )


TEXT_BUILD_EFFECTS = {
    "apple:zoom character",
    "apple:fade and move character",
    "apple:move in character",
    "apple:dissolve character",
}
OUTPUT_FIELDS = [
    "slide_number",
    "to_slide",
    "transition",
    "duration",
    "motion_class",
    "source_text_items",
    "dest_text_items",
    "matched_text_items",
    "moved_text_items",
    "scaled_text_items",
    "appeared_text_items",
    "disappeared_text_items",
    "character_build_effects",
    "all_build_effects",
    "top_text_moves",
    "appeared_text_samples",
    "disappeared_text_samples",
]


def text_objects_for_slide(
    dataset: ObjectDataset, slide_number: int
) -> list[dict[str, Any]]:
    objects = []
    for obj in dataset.objects.get(slide_number, []):
        object_type = obj["object_type"]
        is_text_item = object_type == "text item"
        is_text_shape = object_type == "shape" and bool(obj["identity_text"])
        if not (is_text_item or is_text_shape):
            continue
        if (
            obj["identity_text"]
            or (obj.get("width") not in (None, 0))
            or (obj.get("height") not in (None, 0))
        ):
            objects.append(obj)
    return objects


def text_similarity(source_text: str, dest_text: str) -> float:
    if not source_text or not dest_text:
        return 0.0
    return SequenceMatcher(None, source_text, dest_text, autojunk=False).ratio()


def match_texts(
    source: list[dict[str, Any]],
    dest: list[dict[str, Any]],
    source_size: SlideSize,
    dest_size: SlideSize,
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    Counter[str],
]:
    remaining_source = list(source)
    remaining_dest = list(dest)
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    methods: Counter[str] = Counter()

    text_matches, remaining_source, remaining_dest = match_exact_buckets(
        remaining_source,
        remaining_dest,
        key_function=lambda obj: (
            (obj["object_type"], obj["identity_key"]) if obj["identity_key"] else None
        ),
        source_size=source_size,
        dest_size=dest_size,
    )
    matches.extend(text_matches)
    if text_matches:
        methods["exact_text"] += len(text_matches)

    name_matches, remaining_source, remaining_dest = match_exact_buckets(
        remaining_source,
        remaining_dest,
        key_function=lambda obj: (
            (obj["object_type"], obj["object_name_key"])
            if obj["object_name_key"]
            else None
        ),
        source_size=source_size,
        dest_size=dest_size,
    )
    matches.extend(name_matches)
    if name_matches:
        methods["object_name"] += len(name_matches)

    average_diagonal = (source_size.diagonal + dest_size.diagonal) / 2.0
    candidate_costs: dict[tuple[int, int], float] = {}
    candidate_methods: dict[tuple[int, int], str] = {}
    for source_obj in remaining_source:
        for dest_obj in remaining_dest:
            source_text = source_obj["identity_key"]
            dest_text = dest_obj["identity_key"]
            distance = pair_distance(source_obj, dest_obj, source_size, dest_size)
            distance_ratio = math.inf if distance is None else distance / average_diagonal
            size_delta = normalized_size_delta(
                source_obj, dest_obj, source_size, dest_size
            )
            same_index = source_obj["object_index"] == dest_obj["object_index"]
            similarity = text_similarity(source_text, dest_text)

            if not source_text and not dest_text:
                if not same_index and not (
                    distance_ratio <= 0.05 and size_delta <= 0.10
                ):
                    continue
                method = "blank_geometry"
            elif source_text and dest_text:
                minimum_length = min(len(source_text), len(dest_text))
                if minimum_length < 4 or similarity < 0.90:
                    continue
                if not same_index and distance_ratio > 0.15:
                    continue
                method = "near_text"
            else:
                continue

            cost = match_cost(source_obj, dest_obj, source_size, dest_size)
            cost += (1.0 - similarity) * 0.25 if source_text and dest_text else 0.0
            if same_index:
                cost -= 0.05
            key = (id(source_obj), id(dest_obj))
            candidate_costs[key] = cost
            candidate_methods[key] = method

    heuristic_matches = minimum_cost_eligible_pairs(
        remaining_source,
        remaining_dest,
        lambda source_obj, dest_obj: candidate_costs[(id(source_obj), id(dest_obj))],
        lambda source_obj, dest_obj: (
            id(source_obj), id(dest_obj)
        ) in candidate_costs,
    )
    methods.update(
        candidate_methods[(id(source_obj), id(dest_obj))]
        for source_obj, dest_obj in heuristic_matches
    )

    matches.extend(heuristic_matches)
    remaining_source, remaining_dest = remove_pairs(
        remaining_source, remaining_dest, heuristic_matches
    )
    matches.sort(key=lambda pair: (object_sort_key(pair[0]), object_sort_key(pair[1])))
    return matches, remaining_source, remaining_dest, methods


def analyze(
    transitions: list[dict[str, Any]],
    motions: MotionIndex,
    dataset: ObjectDataset,
    diagnostics: Diagnostics,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    match_methods: Counter[str] = Counter()
    for transition in transitions:
        slide_number = transition["slide_number"]
        if not dataset.has_slide(slide_number + 1):
            diagnostics.warn(
                "missing_destination_slide",
                f"slide {slide_number}: no destination slide {slide_number + 1} "
                "was found in the object TSV; skipping transition",
            )
            continue
        source_size = dataset.size_for(slide_number)
        dest_size = dataset.size_for(slide_number + 1)
        motion_row = motions.find(transition["archive_name"])
        if motion_row is None:
            diagnostics.warn(
                "missing_motion_record",
                f"slide {slide_number}: no motion JSON record matches {transition['archive_name']!r}",
            )
            motion_row = {}
        settings = dataset.slide_settings.get(slide_number)
        if settings is None:
            diagnostics.warn(
                "missing_slide_settings",
                f"slide {slide_number}: no slide record was found in the object TSV",
            )
            settings = {}

        source = text_objects_for_slide(dataset, slide_number)
        dest = text_objects_for_slide(dataset, slide_number + 1)
        matches, disappeared, appeared, row_match_methods = match_texts(
            source, dest, source_size, dest_size
        )
        match_methods.update(row_match_methods)
        moved: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        scaled: list[tuple[dict[str, Any], dict[str, Any]]] = []
        average_width = (source_size.width + dest_size.width) / 2.0
        average_height = (source_size.height + dest_size.height) / 2.0
        movement_threshold = average_width * POSITION_TOLERANCE_RATIO
        width_tolerance = average_width * HORIZONTAL_SIZE_TOLERANCE_RATIO
        height_tolerance = average_height * VERTICAL_SIZE_TOLERANCE_RATIO

        for source_obj, dest_obj in matches:
            distance = pair_distance(source_obj, dest_obj, source_size, dest_size)
            if distance is not None and distance > movement_threshold:
                moved.append((distance, source_obj, dest_obj))
            source_width = source_obj.get("width")
            dest_width = dest_obj.get("width")
            source_height = source_obj.get("height")
            dest_height = dest_obj.get("height")
            width_delta = (
                None
                if source_width is None or dest_width is None
                else dest_width / dest_size.width * average_width
                - source_width / source_size.width * average_width
            )
            height_delta = (
                None
                if source_height is None or dest_height is None
                else dest_height / dest_size.height * average_height
                - source_height / source_size.height * average_height
            )
            if (
                width_delta is not None
                and abs(width_delta) > width_tolerance
                or height_delta is not None
                and abs(height_delta) > height_tolerance
            ):
                scaled.append((source_obj, dest_obj))

        character_builds = [
            effect
            for effect in motion_row.get("build_effects", [])
            if effect in TEXT_BUILD_EFFECTS
        ]
        top_moves = sorted(
            moved,
            key=lambda item: (
                -item[0],
                object_sort_key(item[1]),
                object_sort_key(item[2]),
            ),
        )[:8]
        appeared_sorted = sorted(appeared, key=object_sort_key)
        disappeared_sorted = sorted(disappeared, key=object_sort_key)
        rows.append(
            {
                "slide_number": slide_number,
                "to_slide": slide_number + 1,
                "transition": transition["transition"],
                "duration": settings.get("duration", ""),
                "motion_class": clean_display_text(motion_row.get("motion_class")),
                "source_text_items": len(source),
                "dest_text_items": len(dest),
                "matched_text_items": len(matches),
                "moved_text_items": len(moved),
                "scaled_text_items": len(scaled),
                "appeared_text_items": len(appeared),
                "disappeared_text_items": len(disappeared),
                "character_build_effects": "; ".join(character_builds),
                "all_build_effects": "; ".join(
                    motion_row.get("build_effects", [])
                ),
                "top_text_moves": "; ".join(
                    f"{(source_obj['identity_text'] or '[blank]')[:60]} {distance:.0f}px"
                    for distance, source_obj, _ in top_moves
                ),
                "appeared_text_samples": "; ".join(
                    (obj["identity_text"] or "[blank]")[:60]
                    for obj in appeared_sorted[:8]
                ),
                "disappeared_text_samples": "; ".join(
                    (obj["identity_text"] or "[blank]")[:60]
                    for obj in disappeared_sorted[:8]
                ),
            }
        )
    return rows, match_methods


def text_motion_score(row: dict[str, Any]) -> int:
    return (
        int(row["moved_text_items"]) * 3
        + int(row["scaled_text_items"]) * 4
        + int(row["appeared_text_items"])
        + int(row["disappeared_text_items"])
    )


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> list[Path]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AnalysisError(f"Could not create output directory {output_dir}: {exc}") from exc
    if not output_dir.is_dir():
        raise AnalysisError(f"Output path is not a directory: {output_dir}")

    csv_path = output_dir / "text-motion-by-transition.csv"
    report_path = output_dir / "text-motion-layer-report.md"
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    spreadsheet_safe_row(
                        {field: row.get(field, "") for field in OUTPUT_FIELDS}
                    )
                )
    except OSError as exc:
        raise AnalysisError(f"Could not write CSV {csv_path}: {exc}") from exc

    transition_counts = Counter(row["transition"] for row in rows)
    text_motion_count = sum(
        1
        for row in rows
        if int(row["moved_text_items"])
        or int(row["scaled_text_items"])
        or int(row["appeared_text_items"])
        or int(row["disappeared_text_items"])
    )
    character_build_count = sum(1 for row in rows if row["character_build_effects"])
    duration_counts = Counter(row["duration"] for row in rows)
    top_text = sorted(
        rows,
        key=lambda row: (
            -text_motion_score(row),
            int(row["slide_number"]),
            row["transition"],
        ),
    )[:30]

    lines = [
        "# Text Motion And Slide Transition Layers",
        "",
        "This report separates the three motion layers:",
        "",
        "1. Slide-level transition between slide N and slide N+1.",
        "2. Text object changes across that slide transition: move, scale, appear, disappear.",
        "3. Native on-slide text/character builds found in the decoded Keynote records.",
        "",
        "## Slide-Level Transition Coverage",
        "",
        f"- Transition slides analyzed: {len(rows)}",
        f"- Transition slides with text object changes across the slide boundary: {text_motion_count}",
        f"- Transition slides with native character/text build effects: {character_build_count}",
        "",
    ]
    for transition, count in sorted(
        transition_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"- `{transition or 'unknown'}`: {count}")
    lines.extend(["", "## Duration Distribution", ""])
    for duration, count in sorted(
        duration_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"- `{duration or 'unknown'}`: {count}")
    lines.extend(["", "## Native Character/Text Build Effects", ""])
    build_counter: Counter[str] = Counter()
    for row in rows:
        for effect in row["character_build_effects"].split("; "):
            if effect:
                build_counter[effect] += 1
    for effect, count in sorted(
        build_counter.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"- `{effect}`: {count} transition slides")
    lines.extend(["", "## Highest Text-Motion Transition Slides", ""])
    for row in top_text:
        score = text_motion_score(row)
        if score == 0:
            continue
        lines.append(
            f"- Slide {row['slide_number']} -> {row['to_slide']}: `{row['transition']}`, duration {row['duration']}; "
            f"text {row['source_text_items']} -> {row['dest_text_items']}, moved {row['moved_text_items']}, "
            f"scaled {row['scaled_text_items']}, appeared {row['appeared_text_items']}, disappeared {row['disappeared_text_items']}. "
            f"Builds: {row['character_build_effects'] or 'none'}. Top moves: {row['top_text_moves'] or 'n/a'}"
        )
    lines.extend(["", "## Interpretation", ""])
    lines.append(
        "- Slide-level transitions and native text builds are separate layers and should be interpreted independently."
    )
    lines.append(
        "- Text continuity is inferred from normalized exported text or object names, with conservative geometry-assisted matching for near-edits and blank objects."
    )
    lines.append(
        "- Character build effects animate text within a slide or build step; they do not by themselves establish slide-to-slide continuity."
    )
    lines.append(
        "- No private Keynote object identifiers are synthesized; ambiguous text objects remain appeared or disappeared."
    )
    try:
        report_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(f"Could not write report {report_path}: {exc}") from exc
    return [csv_path, report_path]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze text continuity and native character builds using exported "
            "Keynote transition, motion, and native-state artifacts."
        )
    )
    parser.add_argument(
        "--transitions-csv",
        required=True,
        type=Path,
        help="ordered transition CSV containing slide_number, archive_name, and transition",
    )
    parser.add_argument(
        "--motion-json",
        required=True,
        type=Path,
        help="native motion summary JSON containing slides_archive_sorted",
    )
    parser.add_argument(
        "--object-tsv",
        required=True,
        type=Path,
        help="native-state TSV containing slide and object rows",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="directory for the two compatibility output artifacts",
    )
    parser.add_argument(
        "--slide-width",
        type=positive_float_argument,
        help="slide width override; required with --slide-height when TSV slide rows omit dimensions",
    )
    parser.add_argument(
        "--slide-height",
        type=positive_float_argument,
        help="slide height override; required with --slide-width when TSV slide rows omit dimensions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.slide_width is None) != (args.slide_height is None):
        parser.error("--slide-width and --slide-height must be provided together")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    diagnostics = Diagnostics()
    transitions_path = resolved_path(args.transitions_csv)
    motion_path = resolved_path(args.motion_json)
    object_path = resolved_path(args.object_tsv)
    output_dir = resolved_path(args.output_dir)
    size_override = (
        SlideSize(args.slide_width, args.slide_height)
        if args.slide_width is not None
        else None
    )

    try:
        transitions = load_transitions(transitions_path, diagnostics)
        motions = load_motion_classes(motion_path, diagnostics)
        dataset = load_objects(
            object_path,
            size_override=size_override,
            diagnostics=diagnostics,
        )
        logging.info(
            "Loaded %d transitions, %d motion records, and %d objects",
            len(transitions),
            len(motions.by_archive),
            dataset.object_count,
        )
        if size_override is not None:
            logging.info(
                "Using slide-size override %.4gx%.4g",
                size_override.width,
                size_override.height,
            )
        else:
            logging.info("Using dimensions exported in object TSV slide rows")
        rows, match_methods = analyze(transitions, motions, dataset, diagnostics)
        outputs = write_outputs(rows, output_dir)
    except AnalysisError as exc:
        logging.error("%s", exc)
        return 2

    result = {
        "transition_rows": len(rows),
        "text_object_rows": sum(
            len(text_objects_for_slide(dataset, slide_number))
            for slide_number in dataset.objects
        ),
        "match_methods": dict(sorted(match_methods.items())),
        "diagnostics": diagnostics.as_dict(),
        "outputs": [str(path) for path in outputs],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
