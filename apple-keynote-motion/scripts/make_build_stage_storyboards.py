#!/usr/bin/env python3
"""Create complete labeled storyboards for every multi-stage Keynote slide."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def numeric_suffix(path: Path) -> int | None:
    groups = re.findall(r"(\d+)", path.stem)
    return int(groups[-1]) if groups else None


def discover_pages(directory: Path) -> dict[int, Path]:
    paths = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )
    suffixes = [numeric_suffix(path) for path in paths]
    if not paths or not all(number is not None for number in suffixes):
        raise ValueError(f"No numbered stage images found in {directory}")
    if len(set(suffixes)) != len(paths):
        raise ValueError(f"Stage image numbers are not unique in {directory}")
    mapping = {int(number): path for number, path in zip(suffixes, paths)}
    if min(mapping) == 0:
        mapping = {number + 1: path for number, path in mapping.items()}
    return dict(sorted(mapping.items()))


def thumbnail(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    return ImageOps.contain(image, size, Image.Resampling.LANCZOS)


def render_storyboard(
    playback_slide: int,
    document_slide: int | None,
    motion_class: str,
    stage_kind: str,
    stage_pages: list[int],
    full_start: int,
    full_end: int,
    page_map: dict[int, Path],
    part: int,
    part_count: int,
) -> Image.Image:
    width = 1800
    margin = 52
    columns = 3
    gap = 28
    thumb_width = (width - margin * 2 - gap * (columns - 1)) // columns
    thumb_height = round(thumb_width * 9 / 16)
    rows = math.ceil(len(stage_pages) / columns)
    header_height = 135
    label_height = 62
    height = header_height + margin + rows * (thumb_height + label_height + gap) + margin
    canvas = Image.new("RGB", (width, height), (15, 15, 17))
    draw = ImageDraw.Draw(canvas)
    title = f"Playback {playback_slide}"
    if document_slide is not None:
        title += f" / Document {document_slide}"
    title += f" | {stage_kind}"
    if part_count > 1:
        title += f" - part {part}/{part_count}"
    draw.text((margin, 26), title, fill=(245, 245, 247), font=font(34, bold=True))
    draw.text((margin, 76), f"Native class: {motion_class or 'unclassified'}", fill=(155, 155, 165), font=font(22))

    for index, pdf_page in enumerate(stage_pages):
        row = index // columns
        column = index % columns
        x = margin + column * (thumb_width + gap)
        y = header_height + margin + row * (thumb_height + label_height + gap)
        image = thumbnail(page_map[pdf_page], (thumb_width, thumb_height))
        px = x + (thumb_width - image.width) // 2
        py = y + (thumb_height - image.height) // 2
        canvas.paste(image, (px, py))
        stage_number = pdf_page - full_start + 1
        label = f"Stage {stage_number}  |  PDF page {pdf_page}"
        if pdf_page == full_end:
            label += "  |  final"
        draw.text((x, y + thumb_height + 12), label, fill=(205, 205, 212), font=font(22, bold=True))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-json", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--stages-per-page", type=int, default=6)
    parser.add_argument(
        "--include-kinds",
        nargs="+",
        help="Optional stage_kind filter, for example: build build-plus-action action",
    )
    args = parser.parse_args()

    if args.stages_per_page < 1:
        raise ValueError("--stages-per-page must be positive")
    manifest = json.loads(args.map_json.read_text(encoding="utf-8"))
    page_map = discover_pages(args.pages_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[dict[str, object]] = []
    included_kinds = set(args.include_kinds or [])
    multi_stage_slides = [
        slide
        for slide in manifest["slides"]
        if int(slide["stage_count"]) > 1
        and (not included_kinds or str(slide.get("stage_kind")) in included_kinds)
    ]
    for slide in multi_stage_slides:
        playback_slide = int(slide["playback_slide"])
        document_slide = int(slide["document_slide"]) if slide.get("document_slide") else None
        motion_class = str(slide.get("motion_class", ""))
        stage_kind = str(slide.get("stage_kind", "unattributed"))
        all_pages = [int(page) for page in slide["stage_pages"]]
        missing = [page for page in all_pages if page not in page_map]
        if missing:
            raise ValueError(f"Missing rendered PDF pages for playback slide {playback_slide}: {missing}")
        part_count = math.ceil(len(all_pages) / args.stages_per_page)
        for part_index in range(part_count):
            start = part_index * args.stages_per_page
            selected_pages = all_pages[start : start + args.stages_per_page]
            storyboard = render_storyboard(
                playback_slide,
                document_slide,
                motion_class,
                stage_kind,
                selected_pages,
                all_pages[0],
                all_pages[-1],
                page_map,
                part_index + 1,
                part_count,
            )
            output_path = args.out_dir / (
                f"build-slide-{playback_slide:03d}-part-{part_index + 1:02d}.jpg"
            )
            storyboard.save(output_path, quality=92, optimize=True)
            outputs.append(
                {
                    "playback_slide": playback_slide,
                    "part": part_index + 1,
                    "part_count": part_count,
                    "stage_pages": selected_pages,
                    "path": str(output_path),
                }
            )

    output_manifest = {
        "map_json": str(args.map_json),
        "pages_dir": str(args.pages_dir),
        "multi_stage_slide_count": len(multi_stage_slides),
        "storyboard_count": len(outputs),
        "included_kinds": sorted(included_kinds),
        "storyboards": outputs,
    }
    manifest_path = args.out_dir / "build-storyboard-manifest.json"
    manifest_path.write_text(json.dumps(output_manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in output_manifest.items() if key != "storyboards"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
