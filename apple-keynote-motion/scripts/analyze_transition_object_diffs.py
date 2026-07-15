#!/usr/bin/env python3
"""Analyze adjacent-slide object diffs from exported Keynote artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from csv_safety import spreadsheet_safe_row

MAGIC_MOVE = "apple:magic-move-implied-motion-path"
POSITION_TOLERANCE_RATIO = 3.0 / 1920.0
LARGE_MOVE_RATIO = 120.0 / 1920.0
HORIZONTAL_SIZE_TOLERANCE_RATIO = 3.0 / 1920.0
VERTICAL_SIZE_TOLERANCE_RATIO = 3.0 / 1080.0
HORIZONTAL_CANVAS_PADDING_RATIO = 5.0 / 1920.0
VERTICAL_CANVAS_PADDING_RATIO = 5.0 / 1080.0
ANONYMOUS_MATCH_TYPES = {"group", "shape", "line", "table"}
DIMENSION_KEY_PAIRS = (
    ("slide_width", "slide_height"),
    ("canvas_width", "canvas_height"),
    ("document_width", "document_height"),
    ("width", "height"),
)
OUTPUT_FIELDS = [
    "slide_number",
    "to_slide",
    "archive_name",
    "transition",
    "motion_class",
    "duration",
    "effect",
    "source_objects",
    "dest_objects",
    "matched_objects",
    "moved_objects",
    "large_moves",
    "scaled_objects",
    "appeared_objects",
    "disappeared_objects",
    "off_canvas_objects",
    "complexity_score",
    "labels",
    "top_moves",
    "build_effects",
    "action_effects",
    "media_triggers",
]


class AnalysisError(RuntimeError):
    """Raised for an invalid input artifact or unusable analysis configuration."""


@dataclass(frozen=True)
class SlideSize:
    width: float
    height: float

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)


@dataclass
class Diagnostics:
    counts: Counter[str] = field(default_factory=Counter)
    max_examples_per_code: int = 5

    def warn(self, code: str, message: str) -> None:
        self.counts[code] += 1
        count = self.counts[code]
        if count <= self.max_examples_per_code:
            logging.warning("%s: %s", code, message)
        elif count == self.max_examples_per_code + 1:
            logging.warning("%s: further warnings suppressed", code)

    def as_dict(self) -> dict[str, int]:
        return dict(sorted(self.counts.items()))


@dataclass
class ObjectDataset:
    objects: dict[int, list[dict[str, Any]]]
    slide_settings: dict[int, dict[str, str]]
    slide_sizes: dict[int, SlideSize]
    default_size: SlideSize | None
    object_count: int

    def size_for(self, slide_number: int) -> SlideSize:
        size = self.slide_sizes.get(slide_number, self.default_size)
        if size is None:
            raise AnalysisError(
                f"No slide dimensions are available for slide {slide_number}. "
                "Add dimensions to slide rows in the object TSV or pass both "
                "--slide-width and --slide-height."
            )
        return size


@dataclass
class MotionIndex:
    by_archive: dict[str, dict[str, Any]]
    by_stem: dict[str, dict[str, Any]]

    def find(self, archive_name: str) -> dict[str, Any] | None:
        normalized = normalize_archive_name(archive_name)
        return self.by_archive.get(normalized) or self.by_stem.get(Path(normalized).stem)


def as_text(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_archive_name(value: Any) -> str:
    return as_text(value).strip().replace("\\", "/")


def clean_display_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFC", as_text(value))
    return re.sub(r"\s+", " ", normalized).strip()


def identity_key(value: Any) -> str:
    return unicodedata.normalize("NFKC", clean_display_text(value))


def parse_finite_float(
    value: Any,
    *,
    field_name: str,
    line_number: int,
    diagnostics: Diagnostics,
) -> float | None:
    text = as_text(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        diagnostics.warn(
            "invalid_number",
            f"line {line_number}: {field_name}={text!r}; treating it as missing",
        )
        return None
    if not math.isfinite(number):
        diagnostics.warn(
            "invalid_number",
            f"line {line_number}: {field_name}={text!r} is not finite; treating it as missing",
        )
        return None
    return number


def parse_positive_int(
    value: Any,
    *,
    field_name: str,
    line_number: int,
    diagnostics: Diagnostics,
) -> int | None:
    text = as_text(value).strip()
    try:
        number = int(text)
    except (TypeError, ValueError):
        diagnostics.warn(
            "invalid_integer",
            f"line {line_number}: {field_name}={text!r}; skipping row",
        )
        return None
    if number < 1:
        diagnostics.warn(
            "invalid_integer",
            f"line {line_number}: {field_name}={text!r} must be positive; skipping row",
        )
        return None
    return number


def parse_slide_extra(
    extra: Any,
    *,
    line_number: int,
    diagnostics: Diagnostics,
) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in as_text(extra).split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            diagnostics.warn(
                "malformed_slide_extra",
                f"line {line_number}: ignored segment without '=': {part!r}",
            )
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if not key:
            diagnostics.warn(
                "malformed_slide_extra",
                f"line {line_number}: ignored segment with an empty key",
            )
            continue
        parsed[key] = value.strip()
    return parsed


def read_dict_rows(
    path: Path,
    *,
    delimiter: str,
    required_columns: set[str],
    artifact_name: str,
) -> list[tuple[int, dict[str, str]]]:
    if not path.exists():
        raise AnalysisError(f"{artifact_name} does not exist: {path}")
    if not path.is_file():
        raise AnalysisError(f"{artifact_name} is not a file: {path}")
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if reader.fieldnames is None:
                raise AnalysisError(f"{artifact_name} has no header row: {path}")
            normalized_fields = [as_text(name).strip() for name in reader.fieldnames]
            if len(normalized_fields) != len(set(normalized_fields)):
                raise AnalysisError(
                    f"{artifact_name} has duplicate columns after header normalization: {path}"
                )
            reader.fieldnames = normalized_fields
            missing = sorted(required_columns - set(normalized_fields))
            if missing:
                raise AnalysisError(
                    f"{artifact_name} is missing required column(s) "
                    f"{', '.join(missing)}: {path}"
                )
            return [(line_number, row) for line_number, row in enumerate(reader, start=2)]
    except AnalysisError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise AnalysisError(f"Could not read {artifact_name} {path}: {exc}") from exc


def size_from_values(
    width_value: Any,
    height_value: Any,
    *,
    source: str,
    line_number: int,
    diagnostics: Diagnostics,
) -> SlideSize | None:
    width_text = as_text(width_value).strip()
    height_text = as_text(height_value).strip()
    if not width_text and not height_text:
        return None
    if not width_text or not height_text:
        diagnostics.warn(
            "incomplete_slide_dimensions",
            f"line {line_number}: {source} must provide both width and height",
        )
        return None
    width = parse_finite_float(
        width_text,
        field_name=f"{source} width",
        line_number=line_number,
        diagnostics=diagnostics,
    )
    height = parse_finite_float(
        height_text,
        field_name=f"{source} height",
        line_number=line_number,
        diagnostics=diagnostics,
    )
    if width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        diagnostics.warn(
            "invalid_slide_dimensions",
            f"line {line_number}: {source} dimensions must be positive, got {width}x{height}",
        )
        return None
    return SlideSize(width, height)


def extract_slide_size(
    row: dict[str, str],
    extra: dict[str, str],
    *,
    line_number: int,
    diagnostics: Diagnostics,
) -> SlideSize | None:
    for width_key, height_key in DIMENSION_KEY_PAIRS:
        size = size_from_values(
            row.get(width_key),
            row.get(height_key),
            source=f"TSV columns {width_key}/{height_key}",
            line_number=line_number,
            diagnostics=diagnostics,
        )
        if size is not None:
            return size
    for width_key, height_key in DIMENSION_KEY_PAIRS:
        size = size_from_values(
            extra.get(width_key),
            extra.get(height_key),
            source=f"slide extra keys {width_key}/{height_key}",
            line_number=line_number,
            diagnostics=diagnostics,
        )
        if size is not None:
            return size
    return None


def load_transitions(path: Path, diagnostics: Diagnostics) -> list[dict[str, Any]]:
    rows = read_dict_rows(
        path,
        delimiter=",",
        required_columns={"slide_number", "archive_name", "transition"},
        artifact_name="transitions CSV",
    )
    transitions: list[dict[str, Any]] = []
    seen_slides: Counter[int] = Counter()
    for line_number, row in rows:
        slide_number = parse_positive_int(
            row.get("slide_number"),
            field_name="slide_number",
            line_number=line_number,
            diagnostics=diagnostics,
        )
        if slide_number is None:
            diagnostics.counts["skipped_transition_rows"] += 1
            continue
        archive_name = normalize_archive_name(row.get("archive_name"))
        if not archive_name:
            diagnostics.warn(
                "missing_archive_name",
                f"line {line_number}: transition row has no archive_name; skipping row",
            )
            diagnostics.counts["skipped_transition_rows"] += 1
            continue
        transition = clean_display_text(row.get("transition"))
        if not transition:
            diagnostics.warn(
                "missing_transition",
                f"line {line_number}: slide {slide_number} has an empty transition value",
            )
        parsed = dict(row)
        parsed["slide_number"] = slide_number
        parsed["archive_name"] = archive_name
        parsed["transition"] = transition
        parsed["_line_number"] = line_number
        transitions.append(parsed)
        seen_slides[slide_number] += 1
    for slide_number, count in sorted(seen_slides.items()):
        if count > 1:
            diagnostics.warn(
                "duplicate_transition_slide",
                f"slide {slide_number} appears {count} times in the transitions CSV",
            )
    transitions.sort(
        key=lambda row: (row["slide_number"], row["archive_name"], row["_line_number"])
    )
    if not transitions:
        raise AnalysisError(f"No valid transition rows were found in {path}")
    return transitions


def normalize_string_list(
    value: Any,
    *,
    field_name: str,
    archive_name: str,
    diagnostics: Diagnostics,
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        diagnostics.warn(
            "coerced_motion_list",
            f"{archive_name}: {field_name} was a string; treating it as one item",
        )
        return [clean_display_text(value)] if value.strip() else []
    if not isinstance(value, list):
        diagnostics.warn(
            "invalid_motion_list",
            f"{archive_name}: {field_name} is not a list; ignoring it",
        )
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            diagnostics.warn(
                "invalid_motion_effect",
                f"{archive_name}: ignored non-string item in {field_name}",
            )
            continue
        cleaned = clean_display_text(item)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def load_motion_classes(path: Path, diagnostics: Diagnostics) -> MotionIndex:
    if not path.exists():
        raise AnalysisError(f"motion JSON does not exist: {path}")
    if not path.is_file():
        raise AnalysisError(f"motion JSON is not a file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Could not read motion JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AnalysisError(f"motion JSON root must be an object: {path}")
    slides = data.get("slides_archive_sorted")
    if not isinstance(slides, list):
        raise AnalysisError(
            f"motion JSON must contain a slides_archive_sorted list: {path}"
        )

    by_archive: dict[str, dict[str, Any]] = {}
    by_stem_candidates: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, raw_slide in enumerate(slides):
        if not isinstance(raw_slide, dict):
            diagnostics.warn(
                "invalid_motion_row",
                f"slides_archive_sorted[{index}] is not an object; skipping it",
            )
            continue
        archive_name = normalize_archive_name(raw_slide.get("archive_name"))
        if not archive_name:
            diagnostics.warn(
                "invalid_motion_row",
                f"slides_archive_sorted[{index}] has no archive_name; skipping it",
            )
            continue
        slide = dict(raw_slide)
        for field_name in ("build_effects", "action_effects", "media_triggers"):
            slide[field_name] = normalize_string_list(
                slide.get(field_name),
                field_name=field_name,
                archive_name=archive_name,
                diagnostics=diagnostics,
            )
        if archive_name in by_archive:
            diagnostics.warn(
                "duplicate_motion_archive",
                f"motion JSON contains duplicate archive_name {archive_name!r}; keeping the first",
            )
            continue
        by_archive[archive_name] = slide
        by_stem_candidates[Path(archive_name).stem].append(slide)

    by_stem: dict[str, dict[str, Any]] = {}
    for stem, matches in sorted(by_stem_candidates.items()):
        if len(matches) == 1:
            by_stem[stem] = matches[0]
        else:
            diagnostics.warn(
                "ambiguous_motion_stem",
                f"motion JSON has {len(matches)} archives with stem {stem!r}; stem fallback disabled",
            )
    if not by_archive:
        raise AnalysisError(f"No valid slide records were found in motion JSON {path}")
    return MotionIndex(by_archive=by_archive, by_stem=by_stem)


def load_objects(
    path: Path,
    *,
    size_override: SlideSize | None,
    diagnostics: Diagnostics,
) -> ObjectDataset:
    rows = read_dict_rows(
        path,
        delimiter="\t",
        required_columns={
            "record",
            "slide_number",
            "object_type",
            "object_index",
            "identity_text",
            "x",
            "y",
            "width",
            "height",
            "rotation",
            "opacity",
            "extra",
        },
        artifact_name="object TSV",
    )
    objects: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    slide_settings: dict[int, dict[str, str]] = {}
    embedded_sizes: dict[int, SlideSize] = {}
    document_size: SlideSize | None = None
    object_count = 0

    for line_number, row in rows:
        record = clean_display_text(row.get("record")).lower()
        if not record:
            diagnostics.warn(
                "missing_record_type",
                f"line {line_number}: object TSV row has no record type; skipping row",
            )
            diagnostics.counts["skipped_object_tsv_rows"] += 1
            continue
        if record == "document":
            document_size = extract_slide_size(
                row,
                {},
                line_number=line_number,
                diagnostics=diagnostics,
            )
            continue
        slide_number = parse_positive_int(
            row.get("slide_number"),
            field_name="slide_number",
            line_number=line_number,
            diagnostics=diagnostics,
        )
        if slide_number is None:
            diagnostics.counts["skipped_object_tsv_rows"] += 1
            continue

        if record == "slide":
            extra = parse_slide_extra(
                row.get("extra"),
                line_number=line_number,
                diagnostics=diagnostics,
            )
            if slide_number in slide_settings:
                diagnostics.warn(
                    "duplicate_slide_record",
                    f"line {line_number}: duplicate slide record for slide {slide_number}; keeping the first",
                )
            else:
                slide_settings[slide_number] = extra
            embedded_size = extract_slide_size(
                row,
                extra,
                line_number=line_number,
                diagnostics=diagnostics,
            )
            if embedded_size is not None:
                previous = embedded_sizes.get(slide_number)
                if previous is not None and previous != embedded_size:
                    diagnostics.warn(
                        "conflicting_slide_dimensions",
                        f"line {line_number}: slide {slide_number} has conflicting dimensions; keeping {previous.width}x{previous.height}",
                    )
                else:
                    embedded_sizes[slide_number] = embedded_size
            continue

        if record != "object":
            diagnostics.warn(
                "unknown_record_type",
                f"line {line_number}: unknown record type {record!r}; skipping row",
            )
            diagnostics.counts["skipped_object_tsv_rows"] += 1
            continue

        object_type = clean_display_text(row.get("object_type")).lower()
        if not object_type:
            diagnostics.warn(
                "missing_object_type",
                f"line {line_number}: slide {slide_number} object has no object_type; skipping row",
            )
            diagnostics.counts["skipped_object_tsv_rows"] += 1
            continue
        object_index = parse_positive_int(
            row.get("object_index"),
            field_name="object_index",
            line_number=line_number,
            diagnostics=diagnostics,
        )
        if object_index is None:
            diagnostics.counts["skipped_object_tsv_rows"] += 1
            continue

        obj: dict[str, Any] = dict(row)
        obj.update(
            {
                "slide_number": slide_number,
                "object_type": object_type,
                "object_index": object_index,
                "object_name": clean_display_text(row.get("object_name")),
                "object_name_key": identity_key(row.get("object_name")),
                "identity_text": clean_display_text(row.get("identity_text")),
                "identity_key": identity_key(row.get("identity_text")),
                "_line_number": line_number,
            }
        )
        for field_name in ("x", "y", "width", "height", "rotation", "opacity"):
            obj[field_name] = parse_finite_float(
                row.get(field_name),
                field_name=field_name,
                line_number=line_number,
                diagnostics=diagnostics,
            )
        for field_name in ("width", "height"):
            if obj[field_name] is not None and obj[field_name] < 0:
                diagnostics.warn(
                    "negative_object_dimension",
                    f"line {line_number}: {field_name}={obj[field_name]} treated as missing",
                )
                obj[field_name] = None
        objects[slide_number].append(obj)
        object_count += 1

    if object_count == 0:
        raise AnalysisError(f"No valid object rows were found in {path}")

    if size_override is not None:
        conflicting = sorted(
            slide_number
            for slide_number, embedded_size in embedded_sizes.items()
            if embedded_size != size_override
        )
        if conflicting:
            diagnostics.warn(
                "slide_dimensions_overridden",
                f"CLI dimensions override embedded dimensions on {len(conflicting)} slide(s)",
            )
        slide_sizes: dict[int, SlideSize] = {}
        default_size = size_override
    else:
        slide_sizes = embedded_sizes
        unique_sizes = sorted(
            set(embedded_sizes.values()), key=lambda size: (size.width, size.height)
        )
        default_size = document_size
        if default_size is None and len(unique_sizes) == 1:
            default_size = unique_sizes[0]

    for slide_objects in objects.values():
        slide_objects.sort(key=object_sort_key)
    return ObjectDataset(
        objects=dict(objects),
        slide_settings=slide_settings,
        slide_sizes=slide_sizes,
        default_size=default_size,
        object_count=object_count,
    )


def object_sort_key(obj: dict[str, Any]) -> tuple[Any, ...]:
    return (
        obj.get("object_type", ""),
        obj.get("identity_key", ""),
        obj.get("object_name_key", ""),
        obj.get("object_index", 0),
        obj.get("_line_number", 0),
    )


def center(obj: dict[str, Any]) -> tuple[float, float] | None:
    x = obj.get("x")
    y = obj.get("y")
    if x is None or y is None:
        return None
    return x + (obj.get("width") or 0.0) / 2.0, y + (obj.get("height") or 0.0) / 2.0


def pair_distance(
    source: dict[str, Any],
    dest: dict[str, Any],
    source_size: SlideSize,
    dest_size: SlideSize,
) -> float | None:
    source_center = center(source)
    dest_center = center(dest)
    if source_center is None or dest_center is None:
        return None
    average_width = (source_size.width + dest_size.width) / 2.0
    average_height = (source_size.height + dest_size.height) / 2.0
    dx = (
        dest_center[0] / dest_size.width - source_center[0] / source_size.width
    ) * average_width
    dy = (
        dest_center[1] / dest_size.height - source_center[1] / source_size.height
    ) * average_height
    return math.hypot(dx, dy)


def normalized_size_delta(
    source: dict[str, Any],
    dest: dict[str, Any],
    source_size: SlideSize,
    dest_size: SlideSize,
) -> float:
    deltas: list[float] = []
    if source.get("width") is not None and dest.get("width") is not None:
        deltas.append(
            abs(source["width"] / source_size.width - dest["width"] / dest_size.width)
        )
    if source.get("height") is not None and dest.get("height") is not None:
        deltas.append(
            abs(source["height"] / source_size.height - dest["height"] / dest_size.height)
        )
    return sum(deltas)


def circular_rotation_delta(source: float, dest: float) -> float:
    raw_delta = abs(dest - source) % 360.0
    return min(raw_delta, 360.0 - raw_delta)


def match_cost(
    source: dict[str, Any],
    dest: dict[str, Any],
    source_size: SlideSize,
    dest_size: SlideSize,
) -> float:
    average_diagonal = (source_size.diagonal + dest_size.diagonal) / 2.0
    distance = pair_distance(source, dest, source_size, dest_size)
    distance_cost = 1.0 if distance is None else distance / average_diagonal
    size_cost = normalized_size_delta(source, dest, source_size, dest_size)
    rotation_cost = 0.0
    if source.get("rotation") is not None and dest.get("rotation") is not None:
        rotation_cost = circular_rotation_delta(source["rotation"], dest["rotation"]) / 360.0
    opacity_cost = 0.0
    if source.get("opacity") is not None and dest.get("opacity") is not None:
        opacity_cost = min(abs(dest["opacity"] - source["opacity"]), 100.0) / 100.0
    index_gap = abs(source.get("object_index", 0) - dest.get("object_index", 0))
    index_cost = min(index_gap, 10) * 0.01
    return distance_cost + size_cost * 0.5 + rotation_cost * 0.1 + opacity_cost * 0.05 + index_cost


def minimum_cost_pairs(
    source: list[dict[str, Any]],
    dest: list[dict[str, Any]],
    cost: Callable[[dict[str, Any], dict[str, Any]], float],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return a deterministic minimum-cost assignment for the smaller side."""
    if not source or not dest:
        return []
    left = sorted(source, key=object_sort_key)
    right = sorted(dest, key=object_sort_key)
    swapped = False
    if len(left) > len(right):
        left, right = right, left
        swapped = True

    row_count = len(left)
    column_count = len(right)
    potentials_rows = [0.0] * (row_count + 1)
    potentials_columns = [0.0] * (column_count + 1)
    assignment = [0] * (column_count + 1)
    previous_column = [0] * (column_count + 1)

    def oriented_cost(left_obj: dict[str, Any], right_obj: dict[str, Any]) -> float:
        return cost(right_obj, left_obj) if swapped else cost(left_obj, right_obj)

    for row_index in range(1, row_count + 1):
        assignment[0] = row_index
        current_column = 0
        minimum_values = [math.inf] * (column_count + 1)
        used = [False] * (column_count + 1)
        while True:
            used[current_column] = True
            current_row = assignment[current_column]
            delta = math.inf
            next_column = 0
            for column_index in range(1, column_count + 1):
                if used[column_index]:
                    continue
                reduced_cost = (
                    oriented_cost(left[current_row - 1], right[column_index - 1])
                    - potentials_rows[current_row]
                    - potentials_columns[column_index]
                )
                if reduced_cost < minimum_values[column_index]:
                    minimum_values[column_index] = reduced_cost
                    previous_column[column_index] = current_column
                if minimum_values[column_index] < delta:
                    delta = minimum_values[column_index]
                    next_column = column_index
            if not math.isfinite(delta):
                raise AnalysisError("Could not compute a finite object matching assignment")
            for column_index in range(column_count + 1):
                if used[column_index]:
                    potentials_rows[assignment[column_index]] += delta
                    potentials_columns[column_index] -= delta
                else:
                    minimum_values[column_index] -= delta
            current_column = next_column
            if assignment[current_column] == 0:
                break
        while True:
            next_column = previous_column[current_column]
            assignment[current_column] = assignment[next_column]
            current_column = next_column
            if current_column == 0:
                break

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for column_index in range(1, column_count + 1):
        row_index = assignment[column_index]
        if not row_index:
            continue
        left_obj = left[row_index - 1]
        right_obj = right[column_index - 1]
        pairs.append((right_obj, left_obj) if swapped else (left_obj, right_obj))
    return sorted(pairs, key=lambda pair: (object_sort_key(pair[0]), object_sort_key(pair[1])))


def minimum_cost_eligible_pairs(
    source: list[dict[str, Any]],
    dest: list[dict[str, Any]],
    cost: Callable[[dict[str, Any], dict[str, Any]], float],
    eligible: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Maximize eligible pair count, then minimize total cost globally."""
    if not source or not dest:
        return []
    left = sorted(source, key=object_sort_key)
    right = sorted(dest, key=object_sort_key)
    swapped = False
    if len(left) > len(right):
        left, right = right, left
        swapped = True

    def oriented_cost(left_obj: dict[str, Any], right_obj: dict[str, Any]) -> float:
        return cost(right_obj, left_obj) if swapped else cost(left_obj, right_obj)

    def oriented_eligible(left_obj: dict[str, Any], right_obj: dict[str, Any]) -> bool:
        return eligible(right_obj, left_obj) if swapped else eligible(left_obj, right_obj)

    edge_costs = {
        (row, column): oriented_cost(left_obj, right_obj)
        for row, left_obj in enumerate(left)
        for column, right_obj in enumerate(right)
        if oriented_eligible(left_obj, right_obj)
    }
    if not edge_costs:
        return []

    row_count = len(left)
    real_column_count = len(right)
    column_count = real_column_count + row_count
    max_edge_magnitude = max(abs(value) for value in edge_costs.values())
    unmatched_penalty = (max_edge_magnitude + 1.0) * (
        row_count + real_column_count + 1
    )
    forbidden_penalty = unmatched_penalty * (row_count + 1)

    def matrix_cost(row: int, column: int) -> float:
        if column >= real_column_count:
            return unmatched_penalty
        return edge_costs.get((row, column), forbidden_penalty)

    potentials_rows = [0.0] * (row_count + 1)
    potentials_columns = [0.0] * (column_count + 1)
    assignment = [0] * (column_count + 1)
    previous_column = [0] * (column_count + 1)

    for row_index in range(1, row_count + 1):
        assignment[0] = row_index
        current_column = 0
        minimum_values = [math.inf] * (column_count + 1)
        used = [False] * (column_count + 1)
        while True:
            used[current_column] = True
            current_row = assignment[current_column]
            delta = math.inf
            next_column = 0
            for column_index in range(1, column_count + 1):
                if used[column_index]:
                    continue
                reduced_cost = (
                    matrix_cost(current_row - 1, column_index - 1)
                    - potentials_rows[current_row]
                    - potentials_columns[column_index]
                )
                if reduced_cost < minimum_values[column_index]:
                    minimum_values[column_index] = reduced_cost
                    previous_column[column_index] = current_column
                if minimum_values[column_index] < delta:
                    delta = minimum_values[column_index]
                    next_column = column_index
            if not math.isfinite(delta):
                raise AnalysisError("Could not compute an eligible matching assignment")
            for column_index in range(column_count + 1):
                if used[column_index]:
                    potentials_rows[assignment[column_index]] += delta
                    potentials_columns[column_index] -= delta
                else:
                    minimum_values[column_index] -= delta
            current_column = next_column
            if assignment[current_column] == 0:
                break
        while True:
            next_column = previous_column[current_column]
            assignment[current_column] = assignment[next_column]
            current_column = next_column
            if current_column == 0:
                break

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for column_index in range(1, real_column_count + 1):
        row_index = assignment[column_index]
        if row_index and (row_index - 1, column_index - 1) in edge_costs:
            left_obj = left[row_index - 1]
            right_obj = right[column_index - 1]
            pairs.append((right_obj, left_obj) if swapped else (left_obj, right_obj))
    return sorted(pairs, key=lambda pair: (object_sort_key(pair[0]), object_sort_key(pair[1])))


def remove_pairs(
    source: list[dict[str, Any]],
    dest: list[dict[str, Any]],
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matched_source = {id(pair[0]) for pair in pairs}
    matched_dest = {id(pair[1]) for pair in pairs}
    return (
        [obj for obj in source if id(obj) not in matched_source],
        [obj for obj in dest if id(obj) not in matched_dest],
    )


def match_exact_buckets(
    source: list[dict[str, Any]],
    dest: list[dict[str, Any]],
    *,
    key_function: Callable[[dict[str, Any]], tuple[str, str] | None],
    source_size: SlideSize,
    dest_size: SlideSize,
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    source_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    dest_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for obj in source:
        key = key_function(obj)
        if key is not None:
            source_groups[key].append(obj)
    for obj in dest:
        key = key_function(obj)
        if key is not None:
            dest_groups[key].append(obj)

    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    cost = lambda a, b: match_cost(a, b, source_size, dest_size)
    for key in sorted(set(source_groups) & set(dest_groups)):
        matches.extend(minimum_cost_pairs(source_groups[key], dest_groups[key], cost))
    remaining_source, remaining_dest = remove_pairs(source, dest, matches)
    return matches, remaining_source, remaining_dest


def match_objects(
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

    identity_matches, remaining_source, remaining_dest = match_exact_buckets(
        remaining_source,
        remaining_dest,
        key_function=lambda obj: (
            (obj["object_type"], obj["identity_key"]) if obj["identity_key"] else None
        ),
        source_size=source_size,
        dest_size=dest_size,
    )
    matches.extend(identity_matches)
    if identity_matches:
        methods["identity_text"] += len(identity_matches)

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

    index_matches, remaining_source, remaining_dest = match_exact_buckets(
        remaining_source,
        remaining_dest,
        key_function=lambda obj: (
            (obj["object_type"], str(obj["object_index"]))
            if obj["object_type"] in ANONYMOUS_MATCH_TYPES
            and not obj["identity_key"]
            and not obj["object_name_key"]
            else None
        ),
        source_size=source_size,
        dest_size=dest_size,
    )
    matches.extend(index_matches)
    if index_matches:
        methods["anonymous_index"] += len(index_matches)

    average_diagonal = (source_size.diagonal + dest_size.diagonal) / 2.0

    def eligible_anonymous_geometry(
        source_obj: dict[str, Any], dest_obj: dict[str, Any]
    ) -> bool:
        if (
            source_obj["object_type"] not in ANONYMOUS_MATCH_TYPES
            or source_obj["identity_key"]
            or source_obj["object_name_key"]
        ):
            return False
        if (
            dest_obj["object_type"] != source_obj["object_type"]
            or dest_obj["identity_key"]
            or dest_obj["object_name_key"]
        ):
            return False
        distance = pair_distance(source_obj, dest_obj, source_size, dest_size)
        distance_ratio = math.inf if distance is None else distance / average_diagonal
        size_delta = normalized_size_delta(source_obj, dest_obj, source_size, dest_size)
        return distance_ratio <= 0.12 and size_delta <= 0.20

    heuristic_matches = minimum_cost_eligible_pairs(
        remaining_source,
        remaining_dest,
        lambda source_obj, dest_obj: match_cost(
            source_obj, dest_obj, source_size, dest_size
        ),
        eligible_anonymous_geometry,
    )
    if heuristic_matches:
        methods["anonymous_geometry"] += len(heuristic_matches)
    matches.extend(heuristic_matches)
    remaining_source, remaining_dest = remove_pairs(
        remaining_source, remaining_dest, heuristic_matches
    )
    matches.sort(key=lambda pair: (object_sort_key(pair[0]), object_sort_key(pair[1])))
    return matches, remaining_source, remaining_dest, methods


def off_canvas(obj: dict[str, Any], slide_size: SlideSize) -> bool:
    x = obj.get("x")
    y = obj.get("y")
    if x is None or y is None:
        return False
    width = obj.get("width") or 0.0
    height = obj.get("height") or 0.0
    horizontal_padding = slide_size.width * HORIZONTAL_CANVAS_PADDING_RATIO
    vertical_padding = slide_size.height * VERTICAL_CANVAS_PADDING_RATIO
    return (
        x < -horizontal_padding
        or y < -vertical_padding
        or x + width > slide_size.width + horizontal_padding
        or y + height > slide_size.height + vertical_padding
    )


def summarize_pair(
    slide_number: int,
    transition: dict[str, Any],
    source: list[dict[str, Any]],
    dest: list[dict[str, Any]],
    motion: dict[str, Any],
    settings: dict[str, str],
    source_size: SlideSize,
    dest_size: SlideSize,
) -> tuple[dict[str, Any], Counter[str]]:
    matches, disappeared, appeared, match_methods = match_objects(
        source, dest, source_size, dest_size
    )
    moved: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    scaled: list[tuple[float | None, float | None, dict[str, Any], dict[str, Any]]] = []
    opacity_changed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    rotation_changed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    large_moves: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    average_width = (source_size.width + dest_size.width) / 2.0
    average_height = (source_size.height + dest_size.height) / 2.0
    movement_threshold = average_width * POSITION_TOLERANCE_RATIO
    large_move_threshold = average_width * LARGE_MOVE_RATIO
    width_tolerance = average_width * HORIZONTAL_SIZE_TOLERANCE_RATIO
    height_tolerance = average_height * VERTICAL_SIZE_TOLERANCE_RATIO

    for source_obj, dest_obj in matches:
        distance = pair_distance(source_obj, dest_obj, source_size, dest_size)
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
        scale_x = (
            None
            if source_width in (None, 0) or dest_width is None
            else (dest_width / dest_size.width) / (source_width / source_size.width)
        )
        scale_y = (
            None
            if source_height in (None, 0) or dest_height is None
            else (dest_height / dest_size.height) / (source_height / source_size.height)
        )
        if distance is not None and distance > movement_threshold:
            moved.append((distance, source_obj, dest_obj))
        if distance is not None and distance > large_move_threshold:
            large_moves.append((distance, source_obj, dest_obj))
        if (
            width_delta is not None
            and abs(width_delta) > width_tolerance
            or height_delta is not None
            and abs(height_delta) > height_tolerance
        ):
            scaled.append((scale_x, scale_y, source_obj, dest_obj))
        if (
            source_obj.get("opacity") is not None
            and dest_obj.get("opacity") is not None
            and abs(dest_obj["opacity"] - source_obj["opacity"]) > 1
        ):
            opacity_changed.append((source_obj, dest_obj))
        if (
            source_obj.get("rotation") is not None
            and dest_obj.get("rotation") is not None
            and abs(dest_obj["rotation"] - source_obj["rotation"]) > 1
        ):
            rotation_changed.append((source_obj, dest_obj))

    type_counts_source = Counter(obj["object_type"] for obj in source)
    type_counts_dest = Counter(obj["object_type"] for obj in dest)
    image_identities = Counter(
        obj["identity_text"]
        for obj in source + dest
        if obj["object_type"] == "image" and obj["identity_text"]
    )
    repeated_images = sum(1 for count in image_identities.values() if count > 2)
    off_canvas_count = sum(
        1 for obj in source if off_canvas(obj, source_size)
    ) + sum(1 for obj in dest if off_canvas(obj, dest_size))

    complexity = (
        len(matches)
        + len(moved) * 2
        + len(scaled) * 3
        + len(appeared)
        + len(disappeared)
        + len(large_moves) * 2
        + repeated_images * 2
        + off_canvas_count
    )

    labels: list[str] = []
    if type_counts_source["image"] + type_counts_dest["image"] > 50:
        labels.append("dense image/icon grid")
    if len(scaled) >= 5:
        labels.append("multi-object scale morph")
    elif scaled:
        labels.append("scale morph")
    if len(large_moves) >= 5:
        labels.append("large spatial rearrangement")
    elif large_moves:
        labels.append("hero move")
    if off_canvas_count >= 3:
        labels.append("off-canvas staging")
    if len(appeared) + len(disappeared) >= 10:
        labels.append("many fade-in/out unmatched objects")
    if type_counts_source["text item"] + type_counts_dest["text item"] > 20:
        labels.append("text-heavy choreography")
    if motion.get("build_effects"):
        labels.append("transition plus native builds")
    if motion.get("action_effects"):
        labels.append("transition plus action effects")
    if not labels:
        labels.append("simple continuity")

    top_moves = [
        f"{source_obj['object_type']}:{source_obj['identity_text'] or source_obj['object_name'] or source_obj['object_index']} {distance:.0f}px"
        for distance, source_obj, _ in sorted(
            moved,
            key=lambda item: (-item[0], object_sort_key(item[1]), object_sort_key(item[2])),
        )[:8]
    ]

    return (
        {
            "slide_number": slide_number,
            "to_slide": slide_number + 1,
            "archive_name": transition["archive_name"],
            "transition": transition["transition"],
            "motion_class": clean_display_text(motion.get("motion_class")),
            "duration": settings.get("duration", ""),
            "effect": settings.get("effect", ""),
            "source_objects": len(source),
            "dest_objects": len(dest),
            "matched_objects": len(matches),
            "moved_objects": len(moved),
            "large_moves": len(large_moves),
            "scaled_objects": len(scaled),
            "appeared_objects": len(appeared),
            "disappeared_objects": len(disappeared),
            "off_canvas_objects": off_canvas_count,
            "source_type_counts": dict(type_counts_source),
            "dest_type_counts": dict(type_counts_dest),
            "complexity_score": complexity,
            "labels": "; ".join(labels),
            "top_moves": "; ".join(top_moves),
            "build_effects": "; ".join(motion.get("build_effects", [])),
            "action_effects": "; ".join(motion.get("action_effects", [])),
            "media_triggers": "; ".join(motion.get("media_triggers", [])),
        },
        match_methods,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    spreadsheet_safe_row(
                        {field: row.get(field, "") for field in OUTPUT_FIELDS}
                    )
                )
    except OSError as exc:
        raise AnalysisError(f"Could not write CSV {path}: {exc}") from exc


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> list[Path]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AnalysisError(f"Could not create output directory {output_dir}: {exc}") from exc
    if not output_dir.is_dir():
        raise AnalysisError(f"Output path is not a directory: {output_dir}")

    csv_path = output_dir / "transition-object-diffs.csv"
    ranked_path = output_dir / "magic-move-complexity-ranked.csv"
    summary_path = output_dir / "transition-object-diff-summary.md"
    write_csv(csv_path, rows)

    ranked = sorted(
        rows,
        key=lambda row: (
            -int(row["complexity_score"]),
            int(row["slide_number"]),
            row["archive_name"],
        ),
    )
    write_csv(ranked_path, [row for row in ranked if row["transition"] == MAGIC_MOVE])

    lines = [
        "# Transition Object Diff Summary",
        "",
        f"Transition rows analyzed: {len(rows)}",
        f"Magic Move rows: {sum(1 for row in rows if row['transition'] == MAGIC_MOVE)}",
        "",
        "## Transition Counts",
        "",
    ]
    transition_counts = Counter(row["transition"] for row in rows)
    for transition, count in sorted(
        transition_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"- `{transition or 'unknown'}`: {count}")
    lines.extend(["", "## Highest-Complexity Magic Move Sequences", ""])
    for row in [item for item in ranked if item["transition"] == MAGIC_MOVE][:30]:
        lines.append(
            f"- Slide {row['slide_number']} -> {row['to_slide']}: score {row['complexity_score']}, "
            f"{row['labels']}. Objects {row['source_objects']} -> {row['dest_objects']}; "
            f"matched {row['matched_objects']}, moved {row['moved_objects']}, scaled {row['scaled_objects']}, "
            f"appeared {row['appeared_objects']}, disappeared {row['disappeared_objects']}. "
            f"Top moves: {row['top_moves'] or 'n/a'}"
        )
    lines.extend(["", "## Pattern Takeaways", ""])
    lines.append(
        "- High-complexity Magic Move sequences in this dataset often contain dense image/icon grids and repeated media names."
    )
    lines.append(
        "- Off-canvas objects can stage entrances and exits before the destination layout settles."
    )
    lines.append(
        "- Sequences that combine slide transitions with builds or actions should be evaluated as full-scene choreography."
    )
    lines.append(
        "- Matching is inferred from exported text, names, geometry, and object order; no private Keynote object identifiers are synthesized."
    )
    try:
        summary_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(f"Could not write report {summary_path}: {exc}") from exc
    return [csv_path, ranked_path, summary_path]


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
        source_size = dataset.size_for(slide_number)
        dest_size = dataset.size_for(slide_number + 1)
        motion = motions.find(transition["archive_name"])
        if motion is None:
            diagnostics.warn(
                "missing_motion_record",
                f"slide {slide_number}: no motion JSON record matches {transition['archive_name']!r}",
            )
            motion = {}
        settings = dataset.slide_settings.get(slide_number)
        if settings is None:
            diagnostics.warn(
                "missing_slide_settings",
                f"slide {slide_number}: no slide record was found in the object TSV",
            )
            settings = {}
        row, row_match_methods = summarize_pair(
            slide_number,
            transition,
            dataset.objects.get(slide_number, []),
            dataset.objects.get(slide_number + 1, []),
            motion,
            settings,
            source_size,
            dest_size,
        )
        rows.append(row)
        match_methods.update(row_match_methods)
    return rows, match_methods


def positive_float_argument(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze object continuity across adjacent Keynote slides using exported "
            "transition, motion, and native-state artifacts."
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
        help="directory for the three compatibility output artifacts",
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


def resolved_path(path: Path) -> Path:
    return path.expanduser().resolve()


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
        "object_rows": dataset.object_count,
        "match_methods": dict(sorted(match_methods.items())),
        "diagnostics": diagnostics.as_dict(),
        "outputs": [str(path) for path in outputs],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
