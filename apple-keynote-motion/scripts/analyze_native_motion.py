#!/usr/bin/env python3
"""Read-only native motion inventory for a Keynote .key archive.

The goal is not to fully implement Apple's iWork schema. It decompresses iWork
`.iwa` Snappy chunks, extracts visible transition/build identifiers, and builds
motion-focused summaries useful for studying Apple-style Keynote decks.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.util
import json
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from csv_safety import spreadsheet_safe_row
from keynote_archive import KeynoteArchive
from keynote_effects import TRANSITION_EFFECTS


PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{4,}")
UUID_RE = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$")
MAX_DECODED_CHUNK_BYTES = 256 * 1024 * 1024
MAX_DECODED_IWA_BYTES = 512 * 1024 * 1024


BUILD_PREFIXES = (
    "apple:move in",
    "apple:zoom",
    "apple:fade and move",
    "apple:dissolve",
    "apple:pop",
    "apple:appear",
)

ACTION_PREFIXES = (
    "apple:action-",
    "apple:bc-",
    "apple:keyboard",
    "apple:revolve",
    "apple:wipe",
)

MEDIA_TRIGGERS = {
    "apple:movie-start",
    "apple:audio-start",
}


@dataclass(frozen=True)
class StringHit:
    value: str
    offset: int


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


def extract_strings(data: bytes) -> list[StringHit]:
    hits: list[StringHit] = []
    for match in PRINTABLE_RE.finditer(data):
        raw = match.group(0)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="ignore")
        text = normalize_string_value(text.strip())
        if text:
            hits.append(StringHit(text, match.start()))
    return hits


def normalize_string_value(text: str) -> str:
    apple_index = text.find("apple:")
    if apple_index > 0:
        prefix = text[:apple_index]
        # iWork strings often have a binary marker that becomes printable as `$`
        # before the effect identifier. Preserve ordinary text, normalize IDs.
        if not any(ch.isalnum() for ch in prefix):
            return text[apple_index:]
    if text.endswith("<") or text.endswith("$"):
        if text.startswith("apple:"):
            return text[:-1]
    return text


def clean_text_candidate(text: str) -> bool:
    if text in {"Transition", "All at Once", "Action", "decimal", "zh-Hans", "zh_CN"}:
        return False
    if is_effect_identifier(text):
        return False
    if UUID_RE.match(text.lstrip("$")):
        return False
    if len(text) < 2:
        return False
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    if letters == 0 and digits <= 2:
        return False
    if sum(ch in "{}[]<>\\|~`" for ch in text) >= 2:
        return False
    return True


def normalize_effects(strings: list[StringHit]) -> tuple[str, dict[str, list[str]], list[str]]:
    values = [s.value for s in strings]
    effect_values = [v for v in values if is_effect_identifier(v)]

    transition = "unknown"
    for idx, value in enumerate(values):
        if value != "Transition":
            continue
        for follow in values[idx + 1 : idx + 8]:
            if follow == "none" or follow in TRANSITION_EFFECTS or follow.startswith("apple:magic-move"):
                transition = follow
                break
        if transition != "unknown":
            break

    build_effects: list[str] = []
    action_effects: list[str] = []
    media_triggers: list[str] = []
    transition_effects: list[str] = []
    unclassified_effects: list[str] = []
    for value in effect_values:
        if value == transition:
            transition_effects.append(value)
        elif value in MEDIA_TRIGGERS:
            media_triggers.append(value)
        elif any(value.startswith(prefix) for prefix in ACTION_PREFIXES):
            action_effects.append(value)
        elif any(value.startswith(prefix) for prefix in BUILD_PREFIXES):
            build_effects.append(value)
        else:
            unclassified_effects.append(value)

    build_effects = dedupe(build_effects)
    effect_groups = {
        "transition_effects": dedupe(transition_effects),
        "build_effects": build_effects,
        "action_effects": dedupe(action_effects),
        "media_triggers": dedupe(media_triggers),
        "unclassified_apple_effects": dedupe(unclassified_effects),
    }
    visible_text = [s.value for s in strings if clean_text_candidate(s.value)]
    visible_text = dedupe(visible_text)
    return transition, effect_groups, visible_text


def is_effect_identifier(value: str) -> bool:
    return value.startswith("apple:") or value.startswith("com.apple.iWork.Keynote.")


def motion_class(transition: str, effect_groups: dict[str, list[str]]) -> str:
    has_build = bool(effect_groups["build_effects"])
    has_action = bool(effect_groups["action_effects"])
    has_media = bool(effect_groups["media_triggers"])
    if transition == "apple:magic-move-implied-motion-path":
        extras = []
        if has_build:
            extras.append("BUILD")
        if has_action:
            extras.append("ACTION")
        if has_media:
            extras.append("MEDIA")
        return "MM_PURE" if not extras else "MM_PLUS_" + "_".join(extras)
    if transition not in {"none", "unknown"}:
        extras = []
        if has_build:
            extras.append("BUILD")
        if has_action:
            extras.append("ACTION")
        if has_media:
            extras.append("MEDIA")
        return "TRANSITION_" + transition.removeprefix("apple:").upper().replace("-", "_").replace(" ", "_") + (
            "_PLUS_" + "_".join(extras) if extras else ""
        )
    if has_build:
        extras = []
        if has_action:
            extras.append("ACTION")
        if has_media:
            extras.append("MEDIA")
        return "BUILD_ONLY" + ("_PLUS_" + "_".join(extras) if extras else "")
    if has_action:
        return "ACTION_ONLY_PLUS_MEDIA" if has_media else "ACTION_ONLY"
    if has_media:
        return "MEDIA_ONLY"
    return "STATIC"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def effect_counts(values: list[str]) -> dict[str, int]:
    return dict(Counter(values))


def slide_sort_key(name: str) -> tuple[int, str]:
    stem = Path(name).stem
    if stem == "Slide":
        return (0, stem)
    match = re.search(r"Slide-(\d+)", stem)
    if not match:
        return (0, stem)
    return (int(match.group(1)), stem)


def likely_topic(texts: list[str]) -> str:
    useful = []
    for text in texts:
        clean = text.strip("* ")
        if clean and clean not in useful:
            useful.append(clean)
    return " | ".join(useful[:5])


def analyze(deck: Path) -> dict:
    if not deck.is_file():
        raise FileNotFoundError(f"Deck does not exist: {deck}")
    if not zipfile.is_zipfile(deck):
        raise ValueError(f"Deck is not a readable zip-style .key archive: {deck}")
    snappy = Snappy()
    slides: list[dict] = []
    with KeynoteArchive(deck) as archive:
        slide_names = [
            name
            for name in archive.namelist()
            if name.startswith("Index/Slide") and name.endswith(".iwa")
        ]
        for name in slide_names:
            raw = archive.read(name)
            decoded = decompress_iwa(raw, snappy)
            strings = extract_strings(decoded)
            transition, effect_groups, visible_text = normalize_effects(strings)
            effect_values = [s.value for s in strings if is_effect_identifier(s.value)]
            slides.append(
                {
                    "archive_name": name,
                    "archive_sort_key": slide_sort_key(name)[0],
                    "raw_bytes": len(raw),
                    "decoded_bytes": len(decoded),
                    "transition": transition,
                    "motion_class": motion_class(transition, effect_groups),
                    **effect_groups,
                    "transition_related_effects": (
                        effect_groups["transition_effects"]
                        + effect_groups["action_effects"]
                        + effect_groups["media_triggers"]
                        + effect_groups["unclassified_apple_effects"]
                    ),
                    "build_effect_counts": effect_counts(effect_groups["build_effects"]),
                    "raw_effect_counts": effect_counts(effect_values),
                    # Backward-compatible alias. These are raw printable-string
                    # occurrences, not verified build instances.
                    "apple_effect_counts": effect_counts(effect_values),
                    "visible_text": visible_text[:30],
                    "topic": likely_topic(visible_text),
                    "string_count": len(strings),
                }
            )
    slides.sort(key=lambda item: slide_sort_key(item["archive_name"]))
    transition_slides = [s for s in slides if s["transition"] not in {"unknown", "none"}]
    archive_layout = archive.layout
    package_prefix = archive.package_prefix
    return {
        "deck": deck.name,
        "archive_layout": archive_layout,
        "package_prefix": package_prefix,
        "slide_count": len(slides),
        "transition_slide_count": len(transition_slides),
        "transition_counts": dict(Counter(s["transition"] for s in slides)),
        "motion_class_counts": dict(Counter(s["motion_class"] for s in slides)),
        "build_effect_slide_counts": dict(
            Counter(effect for s in slides for effect in s["build_effects"])
        ),
        "action_effect_slide_counts": dict(
            Counter(effect for s in slides for effect in s["action_effects"])
        ),
        "media_trigger_slide_counts": dict(
            Counter(effect for s in slides for effect in s["media_triggers"])
        ),
        "raw_effect_occurrence_counts": dict(
            Counter(
                effect
                for slide in slides
                for effect, count in slide["raw_effect_counts"].items()
                for _ in range(count)
            )
        ),
        # Backward-compatible aliases. Values count slides containing an effect,
        # not the number of build instances.
        "build_effect_counts": dict(
            Counter(effect for s in slides for effect in s["build_effects"])
        ),
        "action_effect_counts": dict(
            Counter(effect for s in slides for effect in s["action_effects"])
        ),
        "media_trigger_counts": dict(
            Counter(effect for s in slides for effect in s["media_triggers"])
        ),
        "classification_notes": [
            "Effect slide counts report presence on a slide, not verified build-instance counts.",
            "Raw effect occurrence counts come from schema-less printable strings and may include duplicate metadata.",
            "Build target, order, timing, delivery, and parameters require UI or rendered-stage verification.",
        ],
        "slides_archive_sorted": slides,
        "transition_slides_archive_sorted": transition_slides,
    }


def write_outputs(summary: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "native-motion-summary.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = out_dir / "native-transition-slides.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "archive_name",
            "archive_sort_key",
            "transition",
            "motion_class",
            "transition_effects",
            "action_effects",
            "media_triggers",
            "unclassified_apple_effects",
            "transition_related_effects",
            "build_effects",
            "build_effect_counts",
            "topic",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for slide in summary["transition_slides_archive_sorted"]:
            writer.writerow(
                spreadsheet_safe_row({
                    "archive_name": slide["archive_name"],
                    "archive_sort_key": slide["archive_sort_key"],
                    "transition": slide["transition"],
                    "motion_class": slide["motion_class"],
                    "transition_effects": "; ".join(slide["transition_effects"]),
                    "action_effects": "; ".join(slide["action_effects"]),
                    "media_triggers": "; ".join(slide["media_triggers"]),
                    "unclassified_apple_effects": "; ".join(slide["unclassified_apple_effects"]),
                    "transition_related_effects": "; ".join(slide["transition_related_effects"]),
                    "build_effects": "; ".join(slide["build_effects"]),
                    "build_effect_counts": json.dumps(slide["build_effect_counts"], sort_keys=True),
                    "topic": slide["topic"],
                })
            )

    md_path = out_dir / "native-motion-inventory.md"
    lines = [
        "# Native Motion Inventory",
        "",
        f"Deck: `{summary['deck']}`",
        "",
        f"- Slide records: {summary['slide_count']}",
        f"- Slides with native transition effect: {summary['transition_slide_count']}",
        "",
        "## Transition Counts",
        "",
    ]
    for name, count in sorted(summary["transition_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{name}`: {count} slides")
    lines.extend(["", "## Build Effect Counts", ""])
    for name, count in sorted(summary["build_effect_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Action Effect Counts", ""])
    for name, count in sorted(summary["action_effect_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Motion Class Counts", ""])
    for name, count in sorted(summary["motion_class_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Transition Slides", ""])
    for slide in summary["transition_slides_archive_sorted"]:
        lines.append(f"### {slide['archive_name']}")
        lines.append("")
        lines.append(f"- Transition: `{slide['transition']}`")
        lines.append(f"- Motion class: `{slide['motion_class']}`")
        if slide["build_effects"]:
            lines.append(
                "- Native builds/actions on slide: "
                + ", ".join(f"`{effect}`" for effect in slide["build_effects"])
            )
        if slide["action_effects"]:
            lines.append(
                "- Action effects on slide: "
                + ", ".join(f"`{effect}`" for effect in slide["action_effects"])
            )
        if slide["media_triggers"]:
            lines.append(
                "- Media triggers on slide: "
                + ", ".join(f"`{effect}`" for effect in slide["media_triggers"])
            )
        if slide["topic"]:
            lines.append(f"- Visible text/topic clues: {slide['topic']}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deck", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    args.deck = args.deck.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    summary = analyze(args.deck)
    write_outputs(summary, args.out_dir)
    print(json.dumps(
        {
            "slide_count": summary["slide_count"],
            "transition_slide_count": summary["transition_slide_count"],
            "transition_counts": summary["transition_counts"],
            "motion_class_counts": summary["motion_class_counts"],
            "build_effect_counts": summary["build_effect_counts"],
            "action_effect_counts": summary["action_effect_counts"],
            "media_trigger_counts": summary["media_trigger_counts"],
            "raw_effect_occurrence_counts": summary["raw_effect_occurrence_counts"],
            "classification_notes": summary["classification_notes"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
