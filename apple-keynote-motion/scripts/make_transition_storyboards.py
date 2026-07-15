#!/usr/bin/env python3
"""Create labeled source/destination storyboards from Keynote slide exports."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps


PAIR_RE = re.compile(r"^(\d+)->(\d+)$")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
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


def discover_images(slides_dir: Path) -> tuple[dict[int, Path], str]:
    paths = sorted(
        path
        for path in slides_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )
    if not paths:
        raise ValueError(f"No slide images found in {slides_dir}")

    suffixes = [numeric_suffix(path) for path in paths]
    if all(value is not None for value in suffixes) and len(set(suffixes)) == len(paths):
        mapping = {int(value): path for value, path in zip(suffixes, paths)}
        if min(mapping) in {0, 1}:
            if min(mapping) == 0:
                mapping = {number + 1: path for number, path in mapping.items()}
            return mapping, "numeric-filename"

    return {index: path for index, path in enumerate(paths, start=1)}, "sorted-order"


def parse_pair(pair_text: str) -> tuple[int, int] | None:
    match = PAIR_RE.match(pair_text.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def positive_pairs_per_page(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("pairs per page must be a positive integer")
    return number


def choose_numbering(rows: list[dict[str, str]], image_map: dict[int, Path], requested: str) -> str:
    if requested != "auto":
        return requested

    document_numbers = {
        number
        for row in rows
        for number in (parse_pair(row.get("document_pair") or row.get("pair") or "") or ())
    }
    playback_numbers = {
        number
        for row in rows
        for number in (parse_pair(row.get("playback_pair_excluding_skipped", "")) or ())
    }
    available = set(image_map)
    document_coverage = len(document_numbers & available) / max(1, len(document_numbers))
    playback_coverage = len(playback_numbers & available) / max(1, len(playback_numbers))
    return "playback" if playback_coverage > document_coverage else "document"


def load_pairs(
    csv_path: Path,
    image_map: dict[int, Path],
    numbering: str,
) -> tuple[list[dict[str, str | int]], list[dict[str, str]]]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    selected_numbering = choose_numbering(rows, image_map, numbering)
    pairs: list[dict[str, str | int]] = []
    unresolved: list[dict[str, str]] = []
    for row in rows:
        document_pair = row.get("document_pair") or row.get("pair") or ""
        playback_pair = row.get("playback_pair_excluding_skipped", "")
        selected_pair = playback_pair if selected_numbering == "playback" else document_pair
        parsed = parse_pair(selected_pair)
        if not parsed:
            unresolved.append(
                {
                    "document_pair": document_pair,
                    "playback_pair": playback_pair,
                    "reason": f"No renderable {selected_numbering} pair",
                }
            )
            continue
        pairs.append(
            {
                "source": parsed[0],
                "dest": parsed[1],
                "document_pair": document_pair,
                "playback_pair": playback_pair,
                "transition": row.get("transition", ""),
                "duration": row.get("duration", ""),
                "motion_class": row.get("motion_class", ""),
                "numbering": selected_numbering,
            }
        )
    return pairs, unresolved


def thumbnail(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    return ImageOps.contain(image, size, Image.Resampling.LANCZOS)


def diff_image(source: Image.Image, dest: Image.Image, size: tuple[int, int]) -> Image.Image:
    left = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    right = ImageOps.fit(dest, size, method=Image.Resampling.LANCZOS)
    diff = ImageChops.difference(left, right)
    diff = ImageEnhance.Contrast(diff).enhance(2.5)
    return diff


def paste_center(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    x, y, width, height = box
    px = x + (width - image.width) // 2
    py = y + (height - image.height) // 2
    canvas.paste(image, (px, py))


def render_page(
    page_pairs: list[dict[str, str | int]],
    image_map: dict[int, Path],
    page_number: int,
    include_diff: bool,
) -> Image.Image:
    page_width = 1800
    margin = 60
    header_height = 100
    gap = 28
    thumb_width = 760 if not include_diff else 520
    thumb_height = round(thumb_width * 9 / 16)
    columns = 2 + int(include_diff)
    row_height = thumb_height + 120
    page_height = header_height + margin + len(page_pairs) * row_height + margin
    canvas = Image.new("RGB", (page_width, page_height), (15, 15, 17))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 38), f"Transition storyboard {page_number}", fill=(245, 245, 247), font=font(38, bold=True))

    x_positions = [margin + index * (thumb_width + gap) for index in range(columns)]
    for row_index, pair in enumerate(page_pairs):
        y = header_height + margin + row_index * row_height
        source_num = int(pair["source"])
        dest_num = int(pair["dest"])
        source = thumbnail(image_map[source_num], (thumb_width, thumb_height))
        dest = thumbnail(image_map[dest_num], (thumb_width, thumb_height))
        paste_center(canvas, source, (x_positions[0], y, thumb_width, thumb_height))
        paste_center(canvas, dest, (x_positions[1], y, thumb_width, thumb_height))
        numbering = str(pair["numbering"]).title()
        draw.text((x_positions[0], y + thumb_height + 12), f"{numbering} {source_num}", fill=(230, 230, 235), font=font(24, bold=True))
        draw.text((x_positions[1], y + thumb_height + 12), f"{numbering} {dest_num}", fill=(230, 230, 235), font=font(24, bold=True))
        if include_diff:
            diff = diff_image(source, dest, (thumb_width, thumb_height))
            paste_center(canvas, diff, (x_positions[2], y, thumb_width, thumb_height))
            draw.text((x_positions[2], y + thumb_height + 12), "Static-state difference", fill=(230, 230, 235), font=font(24, bold=True))

        detail = (
            f"Document {pair['document_pair']}  |  Playback {pair['playback_pair'] or 'n/a'}  |  "
            f"{pair['transition'] or 'unknown'}  |  {pair['duration'] or '?'}s  |  {pair['motion_class'] or 'unclassified'}"
        )
        draw.text((margin, y + thumb_height + 54), detail, fill=(155, 155, 165), font=font(20))

    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slides-dir", type=Path, required=True)
    parser.add_argument("--pairs-csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--pairs-per-page", type=positive_pairs_per_page, default=3)
    parser.add_argument("--include-diff", action="store_true")
    parser.add_argument(
        "--numbering",
        choices=("auto", "document", "playback"),
        default="auto",
        help="Numbering used by rendered files. Auto compares pair coverage.",
    )
    args = parser.parse_args()

    image_map, mapping_method = discover_images(args.slides_dir)
    pairs, unresolved = load_pairs(args.pairs_csv, image_map, args.numbering)
    usable = [pair for pair in pairs if pair["source"] in image_map and pair["dest"] in image_map]
    missing = [pair for pair in pairs if pair not in usable]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    page_count = math.ceil(len(usable) / args.pairs_per_page) if usable else 0
    pages: list[str] = []
    for page_index in range(page_count):
        page_pairs = usable[page_index * args.pairs_per_page : (page_index + 1) * args.pairs_per_page]
        page = render_page(page_pairs, image_map, page_index + 1, args.include_diff)
        page_path = args.out_dir / f"transition-storyboard-{page_index + 1:03d}.jpg"
        page.save(page_path, quality=92, optimize=True)
        pages.append(str(page_path))

    manifest = {
        "slides_dir": str(args.slides_dir),
        "pairs_csv": str(args.pairs_csv),
        "mapping_method": mapping_method,
        "numbering": usable[0]["numbering"] if usable else args.numbering,
        "slide_image_count": len(image_map),
        "pair_count": len(pairs) + len(unresolved),
        "rendered_pair_count": len(usable),
        "unresolved_pairs": unresolved,
        "missing_pairs": missing,
        "pages": pages,
    }
    (args.out_dir / "storyboard-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
