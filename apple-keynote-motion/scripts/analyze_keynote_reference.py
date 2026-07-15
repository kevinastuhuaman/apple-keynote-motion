#!/usr/bin/env python3
"""Analyze a Keynote .key archive for media-heavy presentation patterns.

This intentionally treats the .key file as read-only. It extracts only selected
metadata and small samples into the study workspace.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from csv_safety import spreadsheet_safe_row
from keynote_archive import ArchiveMember, KeynoteArchive


VIDEO_EXTS = {".mov", ".mp4", ".m4v"}
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".mp3", ".m4a", ".m4r", ".caf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".icns"}


def ext_for(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return suffix[1:] if suffix else "[none]"


def run_json(args: list[str]) -> dict:
    proc = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def safe_name(name: str) -> str:
    cleaned = []
    for ch in Path(name).name:
        if ch.isalnum() or ch in "._- ":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return "".join(cleaned)[:180]


def ffprobe(path: Path) -> dict:
    args = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        return run_json(args)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return {}


def extract_member(archive: KeynoteArchive, info: ArchiveMember, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    return dest


def make_contact_sheet(image_paths: list[Path], out_path: Path, columns: int = 5) -> None:
    if not image_paths:
        return
    from PIL import Image, ImageDraw, ImageFont

    thumb_w, thumb_h = 320, 180
    label_h = 42
    rows = (len(image_paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + label_h)), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()

    for idx, path in enumerate(image_paths):
        row = idx // columns
        col = idx % columns
        x = col * thumb_w
        y = row * (thumb_h + label_h)
        try:
            im = Image.open(path).convert("RGB")
        except OSError:
            continue
        im.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
        px = x + (thumb_w - im.width) // 2
        py = y + (thumb_h - im.height) // 2
        sheet.paste(im, (px, py))
        label = path.stem[:42]
        draw.text((x + 8, y + thumb_h + 8), label, fill=(230, 230, 230), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=92)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deck", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument(
        "--media-mode",
        choices=("none", "images", "full"),
        default="none",
        help="none: metadata only; images: preview/image samples; full: include bounded video samples",
    )
    parser.add_argument("--max-video-samples", type=int, default=5)
    parser.add_argument("--max-image-samples", type=int, default=10)
    parser.add_argument(
        "--max-extracted-bytes",
        type=int,
        default=500_000_000,
        help="hard cap for extracted media samples",
    )
    args = parser.parse_args()

    deck = args.deck.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    if not deck.is_file():
        parser.error(f"deck does not exist: {deck}")
    if not zipfile.is_zipfile(deck):
        parser.error(f"deck is not a readable zip-style .key archive: {deck}")
    if args.max_video_samples < 0 or args.max_image_samples < 0:
        parser.error("sample counts must be non-negative")
    if args.max_extracted_bytes < 0:
        parser.error("--max-extracted-bytes must be non-negative")

    out_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = out_dir / "media-samples"
    frames_dir = out_dir / "previews" / "media-frames"
    if args.media_mode != "none":
        samples_dir.mkdir(parents=True, exist_ok=True)
    if args.media_mode == "full":
        frames_dir.mkdir(parents=True, exist_ok=True)

    with KeynoteArchive(deck) as archive:
        infos = archive.infolist()
        entries = [
            {
                "name": info.name,
                "size": info.size,
                "compressed": info.compressed,
                "ext": ext_for(info.name),
                "is_data": info.name.startswith("Data/"),
                "is_slide_iwa": info.name.startswith("Index/Slide")
                and info.name.endswith(".iwa"),
                "is_template_iwa": info.name.startswith("Index/TemplateSlide")
                and info.name.endswith(".iwa"),
            }
            for info in infos
        ]

        ext_counts = Counter(entry["ext"] for entry in entries)
        data_ext_counts = Counter(entry["ext"] for entry in entries if entry["is_data"])
        total_by_ext = defaultdict(int)
        for entry in entries:
            total_by_ext[entry["ext"]] += entry["size"]

        media_infos = [
            info
            for info in infos
            if Path(info.name).suffix.lower() in VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS
            and info.name.startswith("Data/")
        ]
        largest_media = sorted(media_infos, key=lambda i: i.size, reverse=True)[:80]
        largest_videos_all = [
            info
            for info in sorted(media_infos, key=lambda i: i.size, reverse=True)
            if Path(info.name).suffix.lower() in VIDEO_EXTS
        ]
        largest_images_all = [
            info
            for info in sorted(media_infos, key=lambda i: i.size, reverse=True)
            if Path(info.name).suffix.lower() in IMAGE_EXTS
        ]

        extracted_bytes = 0
        preview_names = ["preview.jpg", "preview-web.jpg", "preview-micro.jpg"]
        preview_infos = []
        if args.media_mode != "none":
            for name in preview_names:
                try:
                    info = archive.getinfo(name)
                except KeyError:
                    continue
                if extracted_bytes + info.size > args.max_extracted_bytes:
                    continue
                preview_infos.append((name, info))
                extracted_bytes += info.size

        largest_videos = []
        if args.media_mode == "full":
            for info in largest_videos_all:
                if len(largest_videos) >= args.max_video_samples:
                    break
                if extracted_bytes + info.size > args.max_extracted_bytes:
                    continue
                largest_videos.append(info)
                extracted_bytes += info.size

        largest_images = []
        if args.media_mode in {"images", "full"}:
            for info in largest_images_all:
                if len(largest_images) >= args.max_image_samples:
                    break
                if extracted_bytes + info.size > args.max_extracted_bytes:
                    continue
                largest_images.append(info)
                extracted_bytes += info.size

        extracted_previews = []
        for name, info in preview_infos:
            extracted_previews.append(extract_member(archive, info, out_dir / "previews" / name))

        video_rows = []
        frame_paths: list[Path] = []
        for index, info in enumerate(largest_videos, start=1):
            sample_path = samples_dir / f"{index:02d}-{safe_name(info.name)}"
            extract_member(archive, info, sample_path)
            probe = ffprobe(sample_path)
            duration = None
            try:
                parsed_duration = float(probe.get("format", {}).get("duration"))
                if math.isfinite(parsed_duration) and parsed_duration >= 0:
                    duration = parsed_duration
            except (TypeError, ValueError):
                pass
            video_stream = next(
                (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
                {},
            )
            frame_path = frames_dir / f"{index:02d}-{sample_path.stem}.jpg"
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        "00:00:01.000",
                        "-i",
                        str(sample_path),
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        str(frame_path),
                    ],
                    check=True,
                )
                frame_paths.append(frame_path)
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            video_rows.append(
                {
                    "rank": index,
                    "archive_name": info.name,
                    "size_bytes": info.size,
                    "duration_seconds": duration,
                    "codec": video_stream.get("codec_name"),
                    "width": video_stream.get("width"),
                    "height": video_stream.get("height"),
                    "frame_rate": video_stream.get("r_frame_rate"),
                    "sample_path": str(sample_path),
                    "frame_path": str(frame_path) if frame_path.exists() else "",
                }
            )

        image_sample_paths: list[Path] = []
        for index, info in enumerate(largest_images, start=1):
            dest = samples_dir / "images" / f"{index:02d}-{safe_name(info.name)}"
            extract_member(archive, info, dest)
            if dest.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
                image_sample_paths.append(dest)

    summary = {
        "deck": str(deck),
        "deck_size_bytes": deck.stat().st_size,
        "archive_layout": archive.layout,
        "package_prefix": archive.package_prefix,
        "outer_entry_count": archive.outer_entry_count,
        "index_entry_count": archive.index_entry_count,
        "entry_count": len(entries),
        "slide_iwa_count": sum(1 for entry in entries if entry["is_slide_iwa"]),
        "template_iwa_count": sum(1 for entry in entries if entry["is_template_iwa"]),
        "extension_counts": dict(ext_counts.most_common()),
        "data_extension_counts": dict(data_ext_counts.most_common()),
        "total_size_by_extension": dict(
            sorted(total_by_ext.items(), key=lambda item: item[1], reverse=True)
        ),
        "largest_media": [
            {"name": info.name, "size_bytes": info.size} for info in largest_media
        ],
        "media_extraction": {
            "mode": args.media_mode,
            "extracted_bytes": extracted_bytes,
            "preview_samples": len(extracted_previews),
            "video_samples": len(largest_videos),
            "image_samples": len(largest_images),
            "max_extracted_bytes": args.max_extracted_bytes,
        },
        "top_video_samples": video_rows,
    }

    (out_dir / "archive-summary.json").write_text(json.dumps(summary, indent=2))

    with (out_dir / "largest-media.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "size_bytes"])
        writer.writeheader()
        for info in largest_media:
            writer.writerow(
                spreadsheet_safe_row({"name": info.name, "size_bytes": info.size})
            )

    with (out_dir / "top-video-samples.csv").open("w", newline="") as f:
        fieldnames = [
            "rank",
            "archive_name",
            "size_bytes",
            "duration_seconds",
            "codec",
            "width",
            "height",
            "frame_rate",
            "sample_path",
            "frame_path",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(spreadsheet_safe_row(row) for row in video_rows)

    if frame_paths:
        make_contact_sheet(frame_paths, out_dir / "previews" / "top-video-frames.jpg", columns=5)
    if image_sample_paths:
        make_contact_sheet(image_sample_paths, out_dir / "previews" / "top-image-samples.jpg", columns=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
