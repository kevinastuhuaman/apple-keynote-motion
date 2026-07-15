#!/usr/bin/env python3
"""Align Keynote all-stages PDF pages to playback slide renders.

The Keynote PDF export emits one or more pages per playback slide. This tool
uses monotonic dynamic programming to find the final rendered page for every
slide, then assigns preceding pages in that segment as intermediate stages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageStat

from csv_safety import spreadsheet_safe_row


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
HIGH_CONFIDENCE_MAX = 0.08
MEDIUM_CONFIDENCE_MAX = 0.16


def numeric_suffix(path: Path) -> int | None:
    groups = re.findall(r"(\d+)", path.stem)
    return int(groups[-1]) if groups else None


def discover_numbered_images(
    directory: Path, *, prefix: str | None = None
) -> dict[int, Path]:
    paths = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTS
        and (prefix is None or path.stem.startswith(prefix + "-"))
    )
    if not paths:
        raise ValueError(f"No images found in {directory}")

    suffixes = [numeric_suffix(path) for path in paths]
    if all(value is not None for value in suffixes) and len(set(suffixes)) == len(paths):
        mapping = {int(value): path for value, path in zip(suffixes, paths)}
        if min(mapping) == 0:
            mapping = {number + 1: path for number, path in mapping.items()}
        if min(mapping) == 1:
            page_numbers = sorted(mapping)
            if page_numbers != list(range(1, len(mapping) + 1)):
                raise ValueError(
                    f"Numbered images in {directory} must form a contiguous sequence"
                )
            return dict(sorted(mapping.items()))
        if prefix is not None:
            raise ValueError(
                f"Numbered images in {directory} must start at page 0 or 1"
            )
    return {index: path for index, path in enumerate(paths, start=1)}


def pdf_page_count(pdf_path: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return None
    completed = subprocess.run([pdfinfo, str(pdf_path)], check=True, capture_output=True, text=True)
    match = re.search(r"^Pages:\s+(\d+)$", completed.stdout, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def render_pdf_pages(pdf_path: Path, pages_dir: Path, width: int, force: bool) -> None:
    pages_dir.mkdir(parents=True, exist_ok=True)
    generated_images = sorted(
        path
        for path in pages_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTS
        and path.stem.startswith("stage-page-")
    )
    pdftoppm = shutil.which("pdftoppm")
    if force and not pdftoppm:
        raise RuntimeError(
            "pdftoppm is required. Install Poppler before mapping build stages."
        )
    expected = pdf_page_count(pdf_path)

    def render_to(prefix: Path) -> None:
        if not pdftoppm:
            raise RuntimeError(
                "pdftoppm is required. Install Poppler before mapping build stages."
            )
        command = [
            pdftoppm,
            "-jpeg",
            "-jpegopt",
            "quality=84",
            "-scale-to-x",
            str(width),
            "-scale-to-y",
            "-1",
            str(pdf_path),
            str(prefix),
        ]
        subprocess.run(command, check=True)

    if force:
        with tempfile.TemporaryDirectory(
            prefix="keynote-stage-render-", dir=pages_dir.parent
        ) as temporary:
            staging_dir = Path(temporary)
            render_to(staging_dir / "stage-page")
            staged_map = discover_numbered_images(staging_dir, prefix="stage-page")
            staged_images = list(staged_map.values())
            if expected is not None and len(staged_images) != expected:
                raise ValueError(
                    f"Replacement render produced {len(staged_images)} pages, "
                    f"but PDF reports {expected}."
                )

            backup_dir = staging_dir / "previous"
            backup_dir.mkdir()
            moved_previous: list[tuple[Path, Path]] = []
            installed: list[Path] = []
            try:
                for previous in generated_images:
                    backup = backup_dir / previous.name
                    previous.replace(backup)
                    moved_previous.append((backup, previous))
                for staged in staged_images:
                    destination = pages_dir / staged.name
                    staged.replace(destination)
                    installed.append(destination)
            except BaseException:
                for destination in installed:
                    destination.unlink(missing_ok=True)
                for backup, previous in moved_previous:
                    if backup.exists():
                        backup.replace(previous)
                raise
        return

    existing = (
        discover_numbered_images(pages_dir, prefix="stage-page")
        if generated_images
        else {}
    )
    if existing:
        if expected is None or len(existing) == expected:
            return
        raise ValueError(
            f"Pages directory has {len(existing)} files but PDF reports {expected} pages. "
            "Use a new empty --pages-dir rather than aligning a partial render."
        )
    render_to(pages_dir / "stage-page")


def visual_feature(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert("RGB"), (64, 36), method=Image.Resampling.LANCZOS)
    color = image.resize((16, 9), Image.Resampling.LANCZOS)
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES).resize((16, 9), Image.Resampling.LANCZOS)
    color_values = np.asarray(color, dtype=np.float32).reshape(-1) / 255.0
    edge_values = np.asarray(edges, dtype=np.float32).reshape(-1) / 255.0
    return np.concatenate((color_values, edge_values * 1.5))


def distance_matrix(slides: list[Path], pages: list[Path]) -> np.ndarray:
    page_features = np.vstack([visual_feature(path) for path in pages])
    result = np.empty((len(slides), len(pages)), dtype=np.float32)
    for index, slide_path in enumerate(slides):
        slide_feature = visual_feature(slide_path)
        result[index] = np.mean(np.abs(page_features - slide_feature), axis=1)
    return result


def monotonic_alignment(distances: np.ndarray) -> tuple[list[int], float]:
    slide_count, page_count = distances.shape
    if page_count < slide_count:
        raise ValueError(f"PDF has {page_count} pages for {slide_count} slides")

    infinity = np.float32(np.inf)
    back = np.full((slide_count, page_count), -1, dtype=np.int32)
    previous = np.full(page_count, infinity, dtype=np.float32)

    last_for_first = page_count - slide_count
    previous[: last_for_first + 1] = distances[0, : last_for_first + 1]

    for slide_index in range(1, slide_count):
        prefix_cost = np.minimum.accumulate(previous)
        prefix_arg = np.empty(page_count, dtype=np.int32)
        best_index = 0
        best_value = previous[0]
        for page_index, value in enumerate(previous):
            if value <= best_value:
                best_value = value
                best_index = page_index
            prefix_arg[page_index] = best_index

        current = np.full(page_count, infinity, dtype=np.float32)
        first_page = slide_index
        last_page = page_count - (slide_count - slide_index)
        candidates = np.arange(first_page, last_page + 1)
        current[candidates] = distances[slide_index, candidates] + prefix_cost[candidates - 1]
        back[slide_index, candidates] = prefix_arg[candidates - 1]
        previous = current

    final_page = page_count - 1
    if not math.isfinite(float(previous[final_page])):
        raise RuntimeError("Could not align the final slide to the final PDF page")

    assignments = [0] * slide_count
    assignments[-1] = final_page
    for slide_index in range(slide_count - 1, 0, -1):
        previous_page = int(back[slide_index, assignments[slide_index]])
        if previous_page < 0:
            raise RuntimeError(f"Broken alignment backpointer at slide {slide_index + 1}")
        assignments[slide_index - 1] = previous_page
    return assignments, float(previous[final_page])


def confidence(score: float, median: float) -> str:
    high_threshold = min(max(0.025, median * 2.5), HIGH_CONFIDENCE_MAX)
    medium_threshold = min(max(0.08, median * 5.0), MEDIUM_CONFIDENCE_MAX)
    if score <= high_threshold:
        return "high"
    if score <= medium_threshold:
        return "medium"
    return "low"


def load_native_context(
    number_map_path: Path | None,
    order_path: Path | None,
    native_path: Path | None,
) -> dict[int, dict[str, object]]:
    supplied = [number_map_path, order_path, native_path]
    if not any(supplied):
        return {}
    if not all(supplied):
        raise ValueError("Provide --slide-number-map, --slide-order-csv, and --native-json together")

    assert number_map_path and order_path and native_path
    with number_map_path.open(newline="", encoding="utf-8") as stream:
        number_rows = list(csv.DictReader(stream))
    with order_path.open(newline="", encoding="utf-8") as stream:
        order_rows = list(csv.DictReader(stream))
    native = json.loads(native_path.read_text(encoding="utf-8"))

    archive_by_document = {int(row["slide_number"]): row["archive_name"] for row in order_rows}
    native_by_archive = {row["archive_name"]: row for row in native["slides_archive_sorted"]}
    result: dict[int, dict[str, object]] = {}
    for row in number_rows:
        if str(row.get("skipped", "")).lower() == "true":
            continue
        document_slide = int(row["document_slide"])
        playback_slide = int(row["playback_slide_excluding_skipped"])
        archive_name = archive_by_document[document_slide]
        native_slide = native_by_archive[archive_name]
        result[playback_slide] = {
            "document_slide": document_slide,
            "archive_name": archive_name,
            "motion_class": native_slide["motion_class"],
            "native_transition": native_slide["transition"],
            "build_effects": native_slide["build_effects"],
            "action_effects": native_slide["action_effects"],
            "media_triggers": native_slide["media_triggers"],
        }
    return result


def stage_kind(stage_count: int, context: dict[str, object]) -> str:
    if stage_count <= 1:
        return "single-stage"
    builds = bool(context.get("build_effects"))
    actions = bool(context.get("action_effects"))
    media = bool(context.get("media_triggers"))
    if builds and actions:
        return "build-plus-action"
    if builds:
        return "build"
    if actions:
        return "action"
    if media:
        return "media-only"
    return "unattributed"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def visually_blank(path: Path) -> bool:
    with Image.open(path) as source:
        image = source.convert("L").resize((64, 36), Image.Resampling.LANCZOS)
    stats = ImageStat.Stat(image)
    return stats.mean[0] <= 2.0 and stats.stddev[0] <= 2.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--slides-dir", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--render-width", type=int, default=640)
    parser.add_argument("--force-render", action="store_true")
    parser.add_argument("--slide-number-map", type=Path)
    parser.add_argument("--slide-order-csv", type=Path)
    parser.add_argument("--native-json", type=Path)
    args = parser.parse_args()

    if not args.pdf.is_file():
        raise ValueError(f"PDF not found: {args.pdf}")
    if not args.slides_dir.is_dir():
        raise ValueError(f"Slide image directory not found: {args.slides_dir}")

    render_pdf_pages(args.pdf, args.pages_dir, args.render_width, args.force_render)
    slide_map = discover_numbered_images(args.slides_dir)
    page_map = discover_numbered_images(args.pages_dir, prefix="stage-page")
    slide_paths = [slide_map[number] for number in sorted(slide_map)]
    page_paths = [page_map[number] for number in sorted(page_map)]

    distances = distance_matrix(slide_paths, page_paths)
    assignments, total_cost = monotonic_alignment(distances)
    chosen_scores = [float(distances[index, page]) for index, page in enumerate(assignments)]
    median_score = float(np.median(chosen_scores))
    native_context = load_native_context(args.slide_number_map, args.slide_order_csv, args.native_json)
    page_hashes = {number: file_sha256(path) for number, path in page_map.items()}
    blank_pages = {number for number, path in page_map.items() if visually_blank(path)}

    slides: list[dict[str, object]] = []
    previous_final = -1
    for slide_index, final_page_index in enumerate(assignments):
        page_start = previous_final + 2
        page_end = final_page_index + 1
        score = chosen_scores[slide_index]
        context = native_context.get(slide_index + 1, {})
        stage_pages = list(range(page_start, page_end + 1))
        hash_groups: dict[str, list[int]] = {}
        for page_number in stage_pages:
            hash_groups.setdefault(page_hashes[page_number], []).append(page_number)
        duplicate_groups = [pages for pages in hash_groups.values() if len(pages) > 1]
        slide_record = {
                "playback_slide": slide_index + 1,
                "page_start": page_start,
                "page_end": page_end,
                "stage_count": page_end - page_start + 1,
                "final_page": page_end,
                "final_match_score": round(score, 6),
                "confidence": confidence(score, median_score),
                "slide_image": str(slide_paths[slide_index]),
                "stage_pages": stage_pages,
                "unique_stage_count": len(hash_groups),
                "duplicate_stage_groups": duplicate_groups,
                "blank_stage_pages": [page for page in stage_pages if page in blank_pages],
            }
        slide_record.update(context)
        slide_record["stage_kind"] = stage_kind(int(slide_record["stage_count"]), context)
        review_flags: list[str] = []
        if slide_record["confidence"] == "low":
            review_flags.append("low-final-match")
        if int(slide_record["stage_count"]) > 1 and slide_record["stage_kind"] == "unattributed":
            review_flags.append("unattributed-multi-stage")
        if duplicate_groups:
            review_flags.append("duplicate-stage-render")
        if page_end in blank_pages:
            review_flags.append("blank-final-stage")
        slide_record["review_flags"] = review_flags
        slides.append(slide_record)
        previous_final = final_page_index

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "pdf": str(args.pdf),
        "slides_dir": str(args.slides_dir),
        "pages_dir": str(args.pages_dir),
        "alignment_method": "monotonic visual final-state alignment",
        "playback_slide_count": len(slide_paths),
        "pdf_page_count": len(page_paths),
        "extra_stage_pages": len(page_paths) - len(slide_paths),
        "slides_with_multiple_stages": sum(int(slide["stage_count"]) > 1 for slide in slides),
        "multi_stage_kind_counts": dict(
            sorted(
                (kind, count)
                for kind in {str(slide["stage_kind"]) for slide in slides}
                if (
                    count := sum(
                        slide["stage_kind"] == kind
                        for slide in slides
                        if int(slide["stage_count"]) > 1
                    )
                )
                > 0
            )
        ),
        "total_alignment_cost": round(total_cost, 6),
        "median_final_match_score": round(median_score, 6),
        "low_confidence_slides": [
            int(slide["playback_slide"]) for slide in slides if slide["confidence"] == "low"
        ],
        "review_flag_counts": dict(
            sorted(
                (flag, sum(flag in slide["review_flags"] for slide in slides))
                for flag in {
                    flag
                    for slide in slides
                    for flag in slide["review_flags"]
                }
            )
        ),
        "slides": slides,
    }
    manifest_path = args.out_dir / "build-stage-map.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    csv_path = args.out_dir / "build-stage-map.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "playback_slide",
                "page_start",
                "page_end",
                "stage_count",
                "final_page",
                "final_match_score",
                "confidence",
                "document_slide",
                "motion_class",
                "stage_kind",
                "unique_stage_count",
                "review_flags",
            ),
        )
        writer.writeheader()
        for slide in slides:
            row = {field: slide.get(field, "") for field in writer.fieldnames}
            row["review_flags"] = ",".join(slide["review_flags"])
            writer.writerow(spreadsheet_safe_row(row))

    summary = {key: value for key, value in manifest.items() if key != "slides"}
    summary["manifest"] = str(manifest_path)
    summary["csv"] = str(csv_path)
    print(json.dumps(summary, indent=2))
    return 0 if not manifest["low_confidence_slides"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
