#!/usr/bin/env python3
"""Extract exact native Keynote build and action timelines from slide IWA records.

This script reads only the requested slide members. It does not extract media or
modify the deck. Native protobuf fields are kept alongside decoded inspector
labels so downstream audits can preserve the evidence boundary.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from keynote_archive import KeynoteArchive


STRUCTURAL_STAGE_KINDS = {"build", "build-plus-action", "action"}

PHASE_LABELS = {
    "In": "build-in",
    "Action": "action",
    "Out": "build-out",
}

EFFECT_LABELS = {
    "apple:appear": "Appear",
    "apple:audio-start": "Start Audio",
    "apple:bc-appear": "Appear",
    "apple:bc-zoom-big": "Scale Big",
    "apple:bc-zoom-big character": "Scale Big",
    "apple:dissolve": "Dissolve",
    "apple:dissolve character": "Dissolve",
    "apple:fade and move": "Fade and Move",
    "apple:fade and move character": "Fade and Move",
    "apple:keyboard": "Keyboard",
    "apple:move in": "Move In",
    "apple:move in character": "Move In",
    "apple:movie-start": "Start Movie",
    "apple:pop": "Pop",
    "apple:wipe": "Wipe",
    "apple:zoom": "Scale",
    "apple:zoom character": "Scale",
    "apple:action-blink": "Blink",
    "apple:action-jiggle": "Jiggle",
    "apple:action-motion-path": "Move",
    "apple:action-opacity": "Opacity",
    "apple:action-rotation": "Rotate",
    "apple:action-scale": "Scale",
    "com.apple.iWork.Keynote.BUKAnvil": "Anvil",
    "com.apple.iWork.Keynote.FromDarkness": "From Darkness",
    "com.apple.iWork.Keynote.LineDraw": "Line Draw",
    "com.apple.iWork.Keynote.LineDrawForLine": "Line Draw",
}

# Direction 14 was independently confirmed in the native Keynote inspector.
# The remaining integer values stay raw until each is UI-validated.
DIRECTION_LABELS = {
    14: "Bottom to Top",
}

CSV_FIELDS = (
    "playback_slide",
    "document_slide",
    "stage_kind",
    "motion_class",
    "archive_name",
    "order",
    "start_relationship",
    "start_relative_to_order",
    "start_decode_confidence",
    "automatic",
    "referent",
    "delay",
    "duration",
    "build_identifier",
    "build_chunk_identifier",
    "build_uuid",
    "chunk_id",
    "target_identifier",
    "target_type",
    "target_pbtype",
    "target_text",
    "phase",
    "animation_type_raw",
    "effect",
    "effect_raw",
    "effect_duration",
    "effect_delay",
    "direction",
    "direction_code",
    "delivery",
    "text_delivery",
    "delivery_option",
    "bounce",
    "event_trigger",
    "acceleration",
    "rotation_angle",
    "rotation_direction",
    "scale_size",
    "opacity_alpha",
    "repeat_count",
    "custom_scale",
    "custom_scale_amount",
    "travel_distance",
    "motion_blur",
    "geometry_x",
    "geometry_y",
    "geometry_width",
    "geometry_height",
)


def require_keynote_parser():
    try:
        # PyPI 1.14.4 ships the generated GroupNode proto but omits its type-ID
        # registration. Register it when using that legacy flat package so the
        # CalculationEngine member containing table drawables remains readable.
        try:
            import keynote_parser.mapping as legacy_mapping
            from keynote_parser.generated import TSTArchives_pb2

            group_node = TSTArchives_pb2.GroupByArchive.GroupNodeArchive
            legacy_mapping.ID_NAME_MAP.setdefault(6383, group_node)
            legacy_mapping.NAME_CLASS_MAP.setdefault(
                group_node.DESCRIPTOR.full_name, group_node
            )
        except (ImportError, AttributeError):
            pass
        from keynote_parser.codec import IWAFile, message_to_dict
    except ImportError as exc:
        raise RuntimeError(
            "keynote-parser is required for exact IWA decoding. Install it in an "
            "isolated environment with: python -m pip install keynote-parser"
        ) from exc
    return IWAFile, message_to_dict


def reference_identifier(value: Any) -> str | None:
    if isinstance(value, dict) and "identifier" in value:
        return str(value["identifier"])
    return None


def iter_references(value: Any, key: str | None = None) -> Iterable[tuple[str | None, str]]:
    if isinstance(value, dict):
        identifier = reference_identifier(value)
        if identifier is not None:
            yield key, identifier
        for child_key, child_value in value.items():
            yield from iter_references(child_value, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from iter_references(child, key)


def first_nested(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = first_nested(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_nested(child, key)
            if found is not None:
                return found
    return None


def friendly_target_type(pbtype: str, data: dict[str, Any]) -> str:
    if pbtype == "TSWP.ShapeInfoArchive":
        return "text" if data.get("isTextBox") else "shape"
    if "Group" in pbtype:
        return "group"
    if "Image" in pbtype:
        return "image"
    if "Movie" in pbtype:
        return "movie"
    if "Audio" in pbtype:
        return "audio"
    if "Chart" in pbtype:
        return "chart"
    if "Table" in pbtype:
        return "table"
    if "Line" in pbtype:
        return "line"
    if "Shape" in pbtype or "Placeholder" in pbtype:
        return "shape"
    return pbtype.rsplit(".", 1)[-1].removesuffix("Archive") or "unknown"


def clean_text(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        text = " ".join(value.replace("\ufffc", " ").split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def target_text(
    identifier: str,
    records: dict[str, dict[str, Any]],
    depth: int = 0,
    visited: set[str] | None = None,
) -> list[str]:
    if depth > 5:
        return []
    if visited is None:
        visited = set()
    if identifier in visited or identifier not in records:
        return []
    visited.add(identifier)
    record = records[identifier]
    data = record["data"]

    values: list[Any] = []
    if record["pbtype"] == "TSWP.StorageArchive":
        raw_text = data.get("text", [])
        values.extend(raw_text if isinstance(raw_text, list) else [raw_text])

    follow_keys = {
        "children",
        "deprecatedStorage",
        "ownedStorage",
        "storage",
        "containedStorage",
    }
    for key, ref in iter_references(data):
        if key in follow_keys:
            values.extend(target_text(ref, records, depth + 1, visited))
    return clean_text(values)


def target_geometry(data: dict[str, Any]) -> dict[str, float | None]:
    geometry = first_nested(data, "geometry") or {}
    position = geometry.get("position", {}) if isinstance(geometry, dict) else {}
    size = geometry.get("size", {}) if isinstance(geometry, dict) else {}
    return {
        "x": position.get("x"),
        "y": position.get("y"),
        "width": size.get("width"),
        "height": size.get("height"),
    }


def describe_target(identifier: str | None, records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not identifier or identifier not in records:
        return {
            "identifier": identifier,
            "type": "unresolved",
            "pbtype": None,
            "text": None,
            "geometry": {"x": None, "y": None, "width": None, "height": None},
        }
    record = records[identifier]
    text_values = target_text(identifier, records)
    return {
        "identifier": identifier,
        "type": friendly_target_type(record["pbtype"], record["data"]),
        "pbtype": record["pbtype"],
        "text": " / ".join(text_values) if text_values else None,
        "geometry": target_geometry(record["data"]),
    }


def decode_start_relationship(
    *,
    order: int,
    automatic: bool,
    referent: bool,
    current_reference_order: int | None,
) -> dict[str, Any]:
    """Decode Keynote's compact BuildChunk trigger flags.

    The boolean fields themselves are native-observed. The relationship label
    is schema-derived and remains explicitly tagged until all combinations are
    round-trip validated against the Build Order inspector.
    """
    if not automatic:
        return {
            "label": "On Click",
            "mode": "on-click",
            "relative_to_order": None,
            "confidence": "schema-derived",
            "becomes_reference": True,
        }
    if order == 1 or current_reference_order is None:
        return {
            "label": "After Transition",
            "mode": "after-transition",
            "relative_to_order": None,
            "confidence": "schema-derived",
            "becomes_reference": True,
        }
    if referent:
        return {
            "label": f"After Build {order - 1}",
            "mode": "after-build",
            "relative_to_order": order - 1,
            "confidence": "schema-derived",
            "becomes_reference": True,
        }
    return {
        "label": f"With Build {current_reference_order}",
        "mode": "with-build",
        "relative_to_order": current_reference_order,
        "confidence": "schema-derived",
        "becomes_reference": False,
    }


def uuid_string(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    lower = value.get("lower")
    upper = value.get("upper")
    if lower is None and upper is None:
        return None
    return f"{upper or 0}:{lower or 0}"


def merge_patch_dict(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if key == "_pbtype":
            continue
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_patch_dict(target[key], value)
        else:
            target[key] = value


def apply_protobuf_patch(
    base_object: Any,
    base_data: dict[str, Any],
    patch_data: dict[str, Any],
    field_path: list[int],
) -> None:
    destination = base_data
    descriptor = type(base_object).DESCRIPTOR
    for field_number in field_path:
        field = descriptor.fields_by_number[field_number]
        destination = destination.setdefault(field.json_name, {})
        descriptor = field.message_type
    merge_patch_dict(destination, patch_data)


def record_index(iwa: Any, message_to_dict: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for chunk in iwa.chunks:
        for archive in chunk.archives:
            identifier = str(archive.header.identifier)
            base_records: dict[int, dict[str, Any]] = {}
            patch_count = 0
            for index, (obj, message_info) in enumerate(
                zip(archive.objects, archive.header.message_infos)
            ):
                data = message_to_dict(obj)
                if message_info.type == 0 and hasattr(obj, "data"):
                    base_index = int(message_info.base_message_index)
                    base_record = base_records.get(base_index)
                    if base_record is not None:
                        path = [int(number) for number in message_info.diff_field_path.path]
                        apply_protobuf_patch(
                            archive.objects[base_index],
                            base_record["data"],
                            data,
                            path,
                        )
                        base_record["applied_patch_count"] += 1
                        patch_count += 1
                    continue
                pbtype = data.get("_pbtype", type(obj).__name__)
                record = {
                    "identifier": identifier,
                    "pbtype": pbtype,
                    "data": data,
                    "applied_patch_count": 0,
                }
                base_records[index] = record
                if identifier not in records:
                    records[identifier] = record
            if identifier in records and patch_count:
                records[identifier]["segment_patch_count"] = patch_count
            if identifier not in order:
                order.append(identifier)
    return records, order


class CrossFileRecordResolver:
    """Resolve records shared from duplicated slides without loading all payloads."""

    def __init__(self, archive: KeynoteArchive) -> None:
        self.archive = archive
        self.IWAFile, self.message_to_dict = require_keynote_parser()
        self.member_by_identifier: dict[str, str] = {}
        self.records_by_member: dict[str, tuple[dict[str, dict[str, Any]], list[str]]] = {}
        self.failed_index_members: dict[str, str] = {}

    def build_index(self) -> None:
        members = sorted(
            name
            for name in self.archive.namelist()
            if name.startswith("Index/") and name.endswith(".iwa")
        )
        for member in members:
            try:
                iwa = self.IWAFile.from_buffer(self.archive.read(member), member)
            except Exception as exc:
                self.failed_index_members[member] = str(exc)
                continue
            for chunk in iwa.chunks:
                for segment in chunk.archives:
                    self.member_by_identifier[str(segment.header.identifier)] = member

    def records_for_member(self, member: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
        if member not in self.records_by_member:
            iwa = self.IWAFile.from_buffer(self.archive.read(member), member)
            self.records_by_member[member] = record_index(iwa, self.message_to_dict)
        return self.records_by_member[member]

    def hydrate(self, identifier: str | None, records: dict[str, dict[str, Any]]) -> bool:
        if not identifier:
            return False
        if identifier in records:
            return True
        member = self.member_by_identifier.get(identifier)
        if not member:
            return False
        external_records, _ = self.records_for_member(member)
        records.update(external_records)
        return identifier in records


def extract_slide_timeline(
    raw: bytes,
    member: str,
    metadata_row: dict[str, Any],
    resolver: CrossFileRecordResolver | None = None,
) -> dict[str, Any]:
    IWAFile, message_to_dict = require_keynote_parser()
    if resolver is not None:
        cached_records, cached_order = resolver.records_for_member(member)
        records = dict(cached_records)
        record_order = list(cached_order)
    else:
        iwa = IWAFile.from_buffer(raw, member)
        records, record_order = record_index(iwa, message_to_dict)

    slide_record = next(
        (record for record in records.values() if record["pbtype"] == "KN.SlideArchive"),
        None,
    )
    if slide_record is None:
        raise ValueError(f"No KN.SlideArchive found in {member}")
    slide = slide_record["data"]

    build_ids = [
        identifier
        for identifier in (reference_identifier(value) for value in slide.get("builds", []))
        if identifier
    ]
    chunk_ids = [
        identifier
        for identifier in (reference_identifier(value) for value in slide.get("buildChunks", []))
        if identifier
    ]
    if not chunk_ids:
        chunk_ids = [
            identifier
            for identifier in record_order
            if records[identifier]["pbtype"] == "KN.BuildChunkArchive"
        ]

    events: list[dict[str, Any]] = []
    current_reference_order: int | None = None
    unresolved_chunks: list[str] = []
    unresolved_builds: list[str] = []

    for order, chunk_identifier in enumerate(chunk_ids, start=1):
        chunk_record = records.get(chunk_identifier)
        if not chunk_record or chunk_record["pbtype"] != "KN.BuildChunkArchive":
            unresolved_chunks.append(chunk_identifier)
            continue
        chunk = chunk_record["data"]
        build_identifier = reference_identifier(chunk.get("build"))
        build_record = records.get(build_identifier or "")
        if resolver is not None and not build_record:
            resolver.hydrate(build_identifier, records)
            build_record = records.get(build_identifier or "")
        if not build_record or build_record["pbtype"] != "KN.BuildArchive":
            unresolved_builds.append(build_identifier or "(missing)")
            continue
        build = build_record["data"]

        automatic = bool(chunk.get("automatic", False))
        referent = bool(chunk.get("referent", False))
        start = decode_start_relationship(
            order=order,
            automatic=automatic,
            referent=referent,
            current_reference_order=current_reference_order,
        )
        if start["becomes_reference"]:
            current_reference_order = order

        attributes = build.get("attributes", {})
        animation = attributes.get("animationAttributes", {})
        target_identifier = reference_identifier(build.get("drawable"))
        if resolver is not None:
            resolver.hydrate(target_identifier, records)
        target = describe_target(target_identifier, records)
        direction_code = animation.get("direction")

        event = {
            "order": order,
            "build_identifier": build_identifier,
            "build_chunk_identifier": chunk_identifier,
            "build_uuid": uuid_string(chunk.get("buildId")),
            "chunk_id": (chunk.get("buildChunkIdentifier") or {}).get("buildChunkId"),
            "start": {
                "label": start["label"],
                "mode": start["mode"],
                "relative_to_order": start["relative_to_order"],
                "decode_confidence": start["confidence"],
                "automatic": automatic,
                "referent": referent,
                "delay": chunk.get("delay", 0.0),
            },
            "duration": chunk.get("duration"),
            "target": target,
            "phase": PHASE_LABELS.get(animation.get("animationType"), animation.get("animationType")),
            "animation_type_raw": animation.get("animationType"),
            "effect": EFFECT_LABELS.get(animation.get("effect"), animation.get("effect")),
            "effect_raw": animation.get("effect"),
            "effect_duration": animation.get("duration"),
            "effect_delay": animation.get("delay"),
            "direction": DIRECTION_LABELS.get(direction_code),
            "direction_code": direction_code,
            "delivery": build.get("delivery"),
            "text_delivery": attributes.get("customTextDelivery"),
            "delivery_option": attributes.get("customDeliveryOption"),
            "bounce": attributes.get("customBounce"),
            "event_trigger": attributes.get("eventTrigger"),
            "acceleration": attributes.get("actionAcceleration"),
            "action": {
                "rotation_angle": attributes.get("actionRotationAngle"),
                "rotation_direction": attributes.get("actionRotationDirection"),
                "scale_size": attributes.get("actionScaleSize"),
                "opacity_alpha": attributes.get("actionColorAlpha"),
                "repeat_count": attributes.get("customActionRepeatCount"),
                "custom_scale": attributes.get("customActionScale"),
                "custom_scale_amount": attributes.get("customScaleAmount"),
                "travel_distance": attributes.get("customTravelDistance"),
                "motion_blur": attributes.get("customMotionBlur"),
                "include_endpoints": attributes.get("customIncludeEndpoints"),
                "align_to_path": attributes.get("customAlignToPath"),
                "cursor": attributes.get("customCursor"),
                "decay": attributes.get("customActionDecay"),
                "jiggle_intensity": attributes.get("customActionJiggleIntensity"),
                "motion_path_source": attributes.get("actionMotionPathSource"),
            },
            "native_attributes": attributes,
        }
        events.append(event)

    transition = ((slide.get("transition") or {}).get("attributes") or {}).get(
        "animationAttributes", {}
    )
    return {
        "playback_slide": metadata_row.get("playback_slide"),
        "document_slide": metadata_row.get("document_slide"),
        "archive_name": member,
        "slide_identifier": slide_record["identifier"],
        "stage_kind": metadata_row.get("stage_kind"),
        "motion_class": metadata_row.get("motion_class"),
        "native_transition": transition,
        "native_build_reference_count": len(build_ids),
        "native_build_chunk_reference_count": len(chunk_ids),
        "events": events,
        "unresolved_chunk_references": unresolved_chunks,
        "unresolved_build_references": unresolved_builds,
    }


def load_stage_rows(path: Path, kinds: set[str]) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [row for row in data.get("slides", []) if row.get("stage_kind") in kinds]
    return sorted(rows, key=lambda row: int(row.get("playback_slide", 0)))


def load_slide_order_rows(path: Path, slide_numbers: set[int]) -> list[dict[str, Any]]:
    """Select document slides from recover_slide_order.py CSV output."""
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            slide_number = int(row["slide_number"])
            if slide_number not in slide_numbers:
                continue
            transition = row.get("transition") or "none"
            rows.append(
                {
                    "playback_slide": slide_number,
                    "document_slide": slide_number,
                    "archive_name": row["archive_name"],
                    "stage_kind": "selected",
                    "motion_class": "transition" if transition != "none" else "selected",
                    "transition": transition,
                    "topic": row.get("topic"),
                }
            )
    found = {int(row["document_slide"]) for row in rows}
    missing = sorted(slide_numbers - found)
    if missing:
        raise ValueError(f"slides not found in {path}: {', '.join(map(str, missing))}")
    return sorted(rows, key=lambda row: int(row["document_slide"]))


def flatten_event(slide: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    start = event["start"]
    target = event["target"]
    action = event["action"]
    geometry = target["geometry"]
    return {
        "playback_slide": slide.get("playback_slide"),
        "document_slide": slide.get("document_slide"),
        "stage_kind": slide.get("stage_kind"),
        "motion_class": slide.get("motion_class"),
        "archive_name": slide.get("archive_name"),
        "order": event.get("order"),
        "start_relationship": start.get("label"),
        "start_relative_to_order": start.get("relative_to_order"),
        "start_decode_confidence": start.get("decode_confidence"),
        "automatic": start.get("automatic"),
        "referent": start.get("referent"),
        "delay": start.get("delay"),
        "duration": event.get("duration"),
        "build_identifier": event.get("build_identifier"),
        "build_chunk_identifier": event.get("build_chunk_identifier"),
        "build_uuid": event.get("build_uuid"),
        "chunk_id": event.get("chunk_id"),
        "target_identifier": target.get("identifier"),
        "target_type": target.get("type"),
        "target_pbtype": target.get("pbtype"),
        "target_text": target.get("text"),
        "phase": event.get("phase"),
        "animation_type_raw": event.get("animation_type_raw"),
        "effect": event.get("effect"),
        "effect_raw": event.get("effect_raw"),
        "effect_duration": event.get("effect_duration"),
        "effect_delay": event.get("effect_delay"),
        "direction": event.get("direction"),
        "direction_code": event.get("direction_code"),
        "delivery": event.get("delivery"),
        "text_delivery": event.get("text_delivery"),
        "delivery_option": event.get("delivery_option"),
        "bounce": event.get("bounce"),
        "event_trigger": event.get("event_trigger"),
        "acceleration": event.get("acceleration"),
        "rotation_angle": action.get("rotation_angle"),
        "rotation_direction": action.get("rotation_direction"),
        "scale_size": action.get("scale_size"),
        "opacity_alpha": action.get("opacity_alpha"),
        "repeat_count": action.get("repeat_count"),
        "custom_scale": action.get("custom_scale"),
        "custom_scale_amount": action.get("custom_scale_amount"),
        "travel_distance": action.get("travel_distance"),
        "motion_blur": action.get("motion_blur"),
        "geometry_x": geometry.get("x"),
        "geometry_y": geometry.get("y"),
        "geometry_width": geometry.get("width"),
        "geometry_height": geometry.get("height"),
    }


def summarize(slides: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [flatten_event(slide, event) for slide in slides for event in slide["events"]]
    durations = [float(row["duration"]) for row in rows if row.get("duration") is not None]
    delays = [float(row["delay"]) for row in rows if row.get("delay") is not None]
    return {
        "slide_count": len(slides),
        "event_count": len(rows),
        "phase_counts": dict(Counter(row.get("phase") or "(unset)" for row in rows)),
        "effect_counts": dict(Counter(row.get("effect_raw") or "(unset)" for row in rows)),
        "start_mode_counts": dict(
            Counter(event["start"]["mode"] for slide in slides for event in slide["events"])
        ),
        "start_relationship_counts": dict(
            Counter(row.get("start_relationship") or "(unset)" for row in rows)
        ),
        "trigger_flag_counts": dict(
            Counter(
                f"automatic={str(bool(event['start']['automatic'])).lower()}, "
                f"referent={str(bool(event['start']['referent'])).lower()}"
                for slide in slides
                for event in slide["events"]
            )
        ),
        "target_type_counts": dict(Counter(row.get("target_type") or "(unset)" for row in rows)),
        "direction_code_counts": dict(
            Counter(str(row.get("direction_code", "(unset)")) for row in rows)
        ),
        "slides_with_unresolved_references": sum(
            bool(slide["unresolved_chunk_references"] or slide["unresolved_build_references"])
            for slide in slides
        ),
        "duration_seconds": {
            "min": min(durations) if durations else None,
            "median": statistics.median(durations) if durations else None,
            "max": max(durations) if durations else None,
        },
        "delay_seconds": {
            "min": min(delays) if delays else None,
            "median": statistics.median(delays) if delays else None,
            "max": max(delays) if delays else None,
            "nonzero_count": sum(delay > 0 for delay in delays),
        },
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    slides = payload["slides"]
    lines = [
        f"# {payload['report_title']}",
        "",
        "## Evidence Boundary",
        "",
        "- Build, chunk, target, phase, effect, duration, delay, delivery, and action fields are `native-observed` from typed Keynote protobuf records.",
        "- Start labels are `schema-derived` from the native `automatic` and `referent` flags and remain paired with those raw flags.",
        "- Direction `14` is `native-observed` as Bottom to Top. Other direction integers remain unlabeled until UI-validated.",
        "- Apple-owned media and slide renders are not included.",
        "",
        "## Coverage",
        "",
        f"- Structural slides decoded: **{summary['slide_count']}**",
        f"- Native timeline events decoded: **{summary['event_count']}**",
        f"- Slides with unresolved build/chunk references: **{summary['slides_with_unresolved_references']}**",
        f"- Duration range: **{summary['duration_seconds']['min']}s to {summary['duration_seconds']['max']}s**; median **{summary['duration_seconds']['median']}s**",
        f"- Nonzero delays: **{summary['delay_seconds']['nonzero_count']}**; maximum **{summary['delay_seconds']['max']}s**",
        "",
        "## Phases",
        "",
        "| Phase | Events |",
        "| --- | ---: |",
    ]
    for key, value in sorted(summary["phase_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {key} | {value} |")

    lines.extend(["", "## Effects", "", "| Native effect | Events |", "| --- | ---: |"])
    for key, value in sorted(summary["effect_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{key}` | {value} |")

    lines.extend(
        ["", "## Start Relationships", "", "| Decoded relationship | Events |", "| --- | ---: |"]
    )
    for key, value in sorted(summary["start_mode_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Structural Slides",
            "",
            "| Playback | Document | Kind | Events | Phases | Native effects |",
            "| ---: | ---: | --- | ---: | --- | --- |",
        ]
    )
    for slide in slides:
        phases = ", ".join(dict.fromkeys(str(event.get("phase")) for event in slide["events"]))
        effects = ", ".join(
            dict.fromkeys(f"`{event.get('effect_raw')}`" for event in slide["events"])
        )
        lines.append(
            f"| {slide.get('playback_slide')} | {slide.get('document_slide')} | "
            f"{slide.get('stage_kind')} | {len(slide['events'])} | {phases} | {effects} |"
        )
    lines.append("")
    return "\n".join(lines)


def parser_version() -> str:
    for package in ("keynote-parser", "keynote_parser"):
        try:
            return metadata.version(package)
        except metadata.PackageNotFoundError:
            continue
    return "unknown"


def write_outputs(output_dir: Path, payload: dict[str, Any], output_prefix: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{output_prefix}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    with (output_dir / f"{output_prefix}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for slide in payload["slides"]:
            for event in slide["events"]:
                writer.writerow(flatten_event(slide, event))
    (output_dir / f"{output_prefix}.md").write_text(
        markdown_report(payload), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path, help="Read-only Keynote reference archive")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--stage-map", type=Path, help="Build-stage map JSON")
    selection.add_argument(
        "--slide-order",
        type=Path,
        help="Slide-order CSV produced by recover_slide_order.py",
    )
    parser.add_argument(
        "--slide",
        action="append",
        dest="slides",
        type=int,
        help="Document slide to extract; repeat as needed with --slide-order",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--output-prefix",
        help="Output filename prefix without extension",
    )
    parser.add_argument("--title", help="Markdown report title")
    parser.add_argument(
        "--stage-kind",
        action="append",
        dest="stage_kinds",
        help="Stage kind to include; repeat as needed. Defaults to structural kinds.",
    )
    args = parser.parse_args()

    kinds = set(args.stage_kinds or STRUCTURAL_STAGE_KINDS)
    if args.stage_map:
        stage_rows = load_stage_rows(args.stage_map, kinds)
        selection_metadata = {
            "type": "stage-map",
            "path": str(args.stage_map.resolve()),
            "stage_kinds": sorted(kinds),
        }
        output_prefix = args.output_prefix or "wwdc20-build-order"
        report_title = args.title or "WWDC20 Native Build Timeline"
    else:
        if not args.slides:
            parser.error("--slide-order requires at least one --slide")
        selected_slides = set(args.slides)
        stage_rows = load_slide_order_rows(args.slide_order, selected_slides)
        selection_metadata = {
            "type": "slide-order",
            "path": str(args.slide_order.resolve()),
            "document_slides": sorted(selected_slides),
        }
        output_prefix = args.output_prefix or "native-build-timeline"
        report_title = args.title or "Native Keynote Build Timeline"
    slides: list[dict[str, Any]] = []
    with KeynoteArchive(args.deck) as archive:
        resolver = CrossFileRecordResolver(archive)
        resolver.build_index()
        for row in stage_rows:
            member = row["archive_name"]
            slides.append(
                extract_slide_timeline(archive.read(member), member, row, resolver=resolver)
            )

    payload = {
        "schema_version": "1.0",
        "source_deck": str(args.deck.resolve()),
        "source_selection": selection_metadata,
        "report_title": report_title,
        "decoder": {
            "name": "keynote-parser",
            "version": parser_version(),
            "protobuf_schema": "Keynote 14.4 reverse-engineered schema",
            "indexed_iwa_members_with_parse_errors": resolver.failed_index_members,
        },
        "truth_standard": {
            "native_observed": [
                "build and chunk identifiers",
                "target references",
                "phase and effect identifiers",
                "durations and delays",
                "automatic and referent flags",
                "delivery and action attributes",
            ],
            "schema_derived": [
                "After Transition, On Click, With Build N, and After Build N labels"
            ],
            "ui_validated": [
                "direction code 14 = Bottom to Top",
                "apple:zoom = Scale",
                "apple:move in character = Move In",
            ],
        },
        "summary": summarize(slides),
        "slides": slides,
    }
    write_outputs(args.output_dir, payload, output_prefix)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
