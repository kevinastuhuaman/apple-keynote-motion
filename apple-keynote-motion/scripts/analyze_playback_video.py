#!/usr/bin/env python3
"""Measure rendered Keynote motion from a native movie export.

The report is visual-observed evidence. Frame differences describe rendered
change, not object identity, and the easing fit is only a visual-energy proxy.
Use native archive or inspector evidence for exact effect controls.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def optional_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def frame_rate(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        numerator_text, denominator_text = str(value).split("/", 1)
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except (TypeError, ValueError):
        return None
    if denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) and result > 0 else None


def probe_video(video: Path) -> dict[str, Any]:
    payload = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,duration,nb_frames",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(video),
        ]
    )
    stream = payload["streams"][0]
    fps = frame_rate(stream.get("avg_frame_rate")) or frame_rate(
        stream.get("r_frame_rate")
    )
    if fps is None:
        raise ValueError("ffprobe did not report a usable video frame rate")
    duration = optional_float(stream.get("duration")) or optional_float(
        payload.get("format", {}).get("duration")
    )
    if duration is None:
        raise ValueError("ffprobe did not report a usable video duration")
    reported_frames = optional_float(stream.get("nb_frames"))
    frame_count = (
        int(reported_frames)
        if reported_frames is not None and reported_frames > 0
        else round(duration * fps)
    )
    return {
        "codec": stream.get("codec_name"),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": duration,
        "size_bytes": int(payload["format"]["size"]),
    }


def scaled_size(width: int, height: int, target_width: int) -> tuple[int, int]:
    target_height = max(2, round(height * target_width / width))
    if target_height % 2:
        target_height += 1
    return target_width, target_height


def decode_gray_frames(video: Path, metadata: dict[str, Any], width: int) -> np.ndarray:
    target_width, target_height = scaled_size(metadata["width"], metadata["height"], width)
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"scale={target_width}:{target_height},format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    frame_size = target_width * target_height
    values = np.frombuffer(completed.stdout, dtype=np.uint8)
    if values.size % frame_size:
        raise RuntimeError("ffmpeg returned an incomplete grayscale frame")
    return values.reshape((-1, target_height, target_width))


def _change_geometry(mask: np.ndarray, weights: np.ndarray) -> dict[str, Any]:
    height, width = mask.shape
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return {"bbox": None, "centroid": None}
    selected_weights = weights[ys, xs].astype(np.float64)
    total = float(selected_weights.sum())
    if total:
        centroid_x = float((xs * selected_weights).sum() / total / width)
        centroid_y = float((ys * selected_weights).sum() / total / height)
    else:
        centroid_x = float(xs.mean() / width)
        centroid_y = float(ys.mean() / height)
    return {
        "bbox": {
            "x": float(xs.min() / width),
            "y": float(ys.min() / height),
            "width": float((xs.max() - xs.min() + 1) / width),
            "height": float((ys.max() - ys.min() + 1) / height),
        },
        "centroid": {"x": centroid_x, "y": centroid_y},
    }


def compute_frame_metrics(
    frames: np.ndarray, fps: float, pixel_threshold: int = 8
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = [
        {
            "frame": 0,
            "time_seconds": 0.0,
            "mean_abs_diff": 0.0,
            "p95_abs_diff": 0.0,
            "changed_fraction": 0.0,
            "bbox": None,
            "centroid": None,
        }
    ]
    for frame_index in range(1, len(frames)):
        difference = np.abs(
            frames[frame_index].astype(np.int16) - frames[frame_index - 1].astype(np.int16)
        ).astype(np.uint8)
        changed = difference >= pixel_threshold
        geometry = _change_geometry(changed, difference)
        metrics.append(
            {
                "frame": frame_index,
                "time_seconds": frame_index / fps,
                "mean_abs_diff": float(difference.mean() / 255.0),
                "p95_abs_diff": float(np.percentile(difference, 95) / 255.0),
                "changed_fraction": float(changed.mean()),
                **geometry,
            }
        )
    return metrics


def bridge_short_gaps(active: np.ndarray, maximum_gap: int) -> np.ndarray:
    result = active.copy()
    index = 0
    while index < len(result):
        if result[index]:
            index += 1
            continue
        gap_start = index
        while index < len(result) and not result[index]:
            index += 1
        gap_end = index - 1
        if (
            gap_start > 0
            and index < len(result)
            and result[gap_start - 1]
            and result[index]
            and gap_end - gap_start + 1 <= maximum_gap
        ):
            result[gap_start:index] = True
    return result


def boolean_runs(values: Iterable[bool]) -> list[tuple[int, int]]:
    array = list(values)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(array):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index - 1))
            start = None
    if start is not None:
        runs.append((start, len(array) - 1))
    return runs


def visual_energy_fit(values: np.ndarray) -> dict[str, Any]:
    if len(values) < 2 or float(values.sum()) <= 0:
        return {"best_fit": None, "rmse": {}}
    progress = np.concatenate(([0.0], np.cumsum(values.astype(np.float64))))
    progress /= progress[-1]
    time = np.linspace(0.0, 1.0, len(progress))
    curves = {
        "linear": time,
        "ease-in": time**2,
        "ease-out": 1.0 - (1.0 - time) ** 2,
        "ease-in-out": 3.0 * time**2 - 2.0 * time**3,
    }
    errors = {
        name: float(np.sqrt(np.mean((progress - curve) ** 2)))
        for name, curve in curves.items()
    }
    return {"best_fit": min(errors, key=errors.get), "rmse": errors}


def detect_active_segments(
    metrics: list[dict[str, Any]],
    fps: float,
    *,
    minimum_mean_diff: float = 0.00015,
    minimum_changed_fraction: float = 0.0001,
    bridge_gap_frames: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    differences = np.array([row["mean_abs_diff"] for row in metrics], dtype=np.float64)
    changed = np.array([row["changed_fraction"] for row in metrics], dtype=np.float64)
    sample = differences[1:] if len(differences) > 1 else differences
    if len(sample):
        quiet_cutoff = float(np.percentile(sample, 25))
        quiet_sample = sample[sample <= quiet_cutoff]
        baseline = float(np.median(quiet_sample))
        mad = float(np.median(np.abs(quiet_sample - baseline)))
    else:
        baseline = 0.0
        mad = 0.0
    # Motion-heavy clips may contain no long static section. Estimating codec
    # noise from the quietest quartile avoids raising the threshold above a
    # smooth action that spans most of the movie.
    mean_threshold = max(minimum_mean_diff, baseline + 6.0 * mad)
    active = (differences >= mean_threshold) & (changed >= minimum_changed_fraction)
    if len(active):
        active[0] = False
    active = bridge_short_gaps(active, bridge_gap_frames)

    segments: list[dict[str, Any]] = []
    for run_start, run_end in boolean_runs(active):
        start_frame = max(0, run_start - 1)
        peak_frame = max(
            range(run_start, run_end + 1),
            key=lambda index: metrics[index]["mean_abs_diff"],
        )
        boxes = [metrics[index]["bbox"] for index in range(run_start, run_end + 1)]
        boxes = [box for box in boxes if box]
        union_box = None
        if boxes:
            left = min(box["x"] for box in boxes)
            top = min(box["y"] for box in boxes)
            right = max(box["x"] + box["width"] for box in boxes)
            bottom = max(box["y"] + box["height"] for box in boxes)
            union_box = {
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
            }
        fit = visual_energy_fit(differences[run_start : run_end + 1])
        segments.append(
            {
                "start_frame": start_frame,
                "end_frame": run_end,
                "start_seconds": start_frame / fps,
                "end_seconds": run_end / fps,
                "duration_seconds": (run_end - start_frame) / fps,
                "peak_frame": peak_frame,
                "peak_seconds": peak_frame / fps,
                "peak_mean_abs_diff": metrics[peak_frame]["mean_abs_diff"],
                "changed_bbox": union_box,
                "visual_energy_easing_proxy": fit,
            }
        )
    thresholds = {
        "mean_abs_diff": mean_threshold,
        "changed_fraction": minimum_changed_fraction,
    }
    return segments, thresholds


def choose_keyframes(
    frame_count: int, segments: list[dict[str, Any]], maximum: int = 32
) -> list[int]:
    if frame_count <= 0:
        return []
    selected = {0, frame_count - 1}
    for segment in segments:
        start = int(segment["start_frame"])
        end = int(segment["end_frame"])
        selected.update(
            {
                start,
                round(start + (end - start) * 0.25),
                int(segment["peak_frame"]),
                round(start + (end - start) * 0.75),
                end,
            }
        )
    ordered = sorted(index for index in selected if 0 <= index < frame_count)
    if len(ordered) <= maximum:
        return ordered
    positions = np.linspace(0, len(ordered) - 1, maximum).round().astype(int)
    return [ordered[index] for index in sorted(set(positions))]


def decode_color_keyframes(
    video: Path,
    metadata: dict[str, Any],
    frame_indices: list[int],
    target_width: int,
) -> list[Image.Image]:
    if not frame_indices:
        return []
    width, height = scaled_size(metadata["width"], metadata["height"], target_width)
    expression = "+".join(f"eq(n\\,{index})" for index in frame_indices)
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"select={expression},scale={width}:{height},format=rgb24",
            "-fps_mode",
            "vfr",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    frame_size = width * height * 3
    values = np.frombuffer(completed.stdout, dtype=np.uint8)
    if values.size % frame_size:
        raise RuntimeError("ffmpeg returned an incomplete RGB keyframe")
    arrays = values.reshape((-1, height, width, 3))
    return [Image.fromarray(array.copy(), mode="RGB") for array in arrays]


def contact_sheet(
    frames: list[Image.Image],
    indices: list[int],
    fps: float,
    output: Path,
    columns: int = 4,
) -> None:
    if not frames:
        return
    font = ImageFont.load_default(size=16)
    label_height = 28
    frame_width, frame_height = frames[0].size
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new(
        "RGB",
        (columns * frame_width, rows * (frame_height + label_height)),
        "black",
    )
    draw = ImageDraw.Draw(sheet)
    for slot, (frame, frame_index) in enumerate(zip(frames, indices)):
        x = (slot % columns) * frame_width
        y = (slot // columns) * (frame_height + label_height)
        sheet.paste(frame, (x, y))
        draw.text(
            (x + 8, y + frame_height + 5),
            f"frame {frame_index}  |  {frame_index / fps:.3f}s",
            fill="white",
            font=font,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def load_native_timeline(path: Path | None, playback_slide: int | None) -> dict[str, Any] | None:
    if path is None or playback_slide is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    slide = next(
        (row for row in payload.get("slides", []) if row.get("playback_slide") == playback_slide),
        None,
    )
    if slide is None:
        return None
    return {
        "playback_slide": slide.get("playback_slide"),
        "document_slide": slide.get("document_slide"),
        "native_transition": slide.get("native_transition"),
        "events": [
            {
                "order": event.get("order"),
                "start": event.get("start"),
                "duration": event.get("duration"),
                "phase": event.get("phase"),
                "effect": event.get("effect"),
                "effect_raw": event.get("effect_raw"),
                "acceleration": event.get("acceleration"),
                "target": event.get("target"),
            }
            for event in slide.get("events", [])
        ],
    }


def write_metrics_csv(path: Path, metrics: list[dict[str, Any]]) -> None:
    fields = (
        "frame",
        "time_seconds",
        "mean_abs_diff",
        "p95_abs_diff",
        "changed_fraction",
        "bbox_x",
        "bbox_y",
        "bbox_width",
        "bbox_height",
        "centroid_x",
        "centroid_y",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in metrics:
            box = row.get("bbox") or {}
            centroid = row.get("centroid") or {}
            writer.writerow(
                {
                    "frame": row["frame"],
                    "time_seconds": row["time_seconds"],
                    "mean_abs_diff": row["mean_abs_diff"],
                    "p95_abs_diff": row["p95_abs_diff"],
                    "changed_fraction": row["changed_fraction"],
                    "bbox_x": box.get("x"),
                    "bbox_y": box.get("y"),
                    "bbox_width": box.get("width"),
                    "bbox_height": box.get("height"),
                    "centroid_x": centroid.get("x"),
                    "centroid_y": centroid.get("y"),
                }
            )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    metadata = report["video"]
    lines = [
        f"# Playback Analysis — {report['label']}",
        "",
        "Truth status: `visual-observed` for frame measurements; easing labels are "
        "`inferred` visual-energy proxies.",
        "",
        "## Capture",
        "",
        f"- Source: `{metadata['source']}`",
        f"- Video: {metadata['width']}×{metadata['height']}, {metadata['fps']:.3f} fps, "
        f"{metadata['frame_count']} frames, {metadata['duration_seconds']:.3f}s",
        f"- Active segments: {len(report['active_segments'])}",
        "",
        "## Active Segments",
        "",
        "| # | Frames | Time | Duration | Peak | Visual-energy proxy |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    for index, segment in enumerate(report["active_segments"], start=1):
        lines.append(
            f"| {index} | {segment['start_frame']}–{segment['end_frame']} | "
            f"{segment['start_seconds']:.3f}–{segment['end_seconds']:.3f}s | "
            f"{segment['duration_seconds']:.3f}s | frame {segment['peak_frame']} | "
            f"{segment['visual_energy_easing_proxy']['best_fit'] or 'n/a'} |"
        )
    lines.extend(
        [
            "",
            "The proxy classifies cumulative rendered pixel change. It does not replace "
            "Keynote's native acceleration value.",
        ]
    )
    native = report.get("native_timeline")
    if native:
        lines.extend(
            [
                "",
                "## Native Timeline Cross-Reference",
                "",
                f"Playback slide {native['playback_slide']} / document slide "
                f"{native['document_slide']}.",
                "",
                "| Order | Start | Phase | Effect | Duration | Acceleration | Target |",
                "| ---: | --- | --- | --- | ---: | --- | --- |",
            ]
        )
        for event in native["events"]:
            target = event.get("target") or {}
            target_label = target.get("text") or target.get("type") or target.get("identifier")
            lines.append(
                f"| {event['order']} | {event['start']['label']} | {event['phase']} | "
                f"{event['effect']} | {event['duration']}s | "
                f"{event.get('acceleration') or ''} | {str(target_label)[:80]} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label")
    parser.add_argument("--timeline-json", type=Path)
    parser.add_argument("--playback-slide", type=int)
    parser.add_argument("--analysis-width", type=int, default=320)
    parser.add_argument("--contact-width", type=int, default=480)
    parser.add_argument("--max-keyframes", type=int, default=32)
    parser.add_argument("--pixel-threshold", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.video.is_file():
        raise SystemExit(f"Video does not exist: {args.video}")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("ffmpeg and ffprobe are required")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = probe_video(args.video)
    gray_frames = decode_gray_frames(args.video, metadata, args.analysis_width)
    metadata["frame_count"] = len(gray_frames)
    metrics = compute_frame_metrics(gray_frames, metadata["fps"], args.pixel_threshold)
    for row in metrics:
        row["pixel_threshold"] = args.pixel_threshold
    segments, thresholds = detect_active_segments(metrics, metadata["fps"])
    keyframes = choose_keyframes(len(gray_frames), segments, args.max_keyframes)
    color_frames = decode_color_keyframes(
        args.video, metadata, keyframes, args.contact_width
    )
    if len(color_frames) != len(keyframes):
        keyframes = keyframes[: len(color_frames)]
    contact_sheet(
        color_frames,
        keyframes,
        metadata["fps"],
        args.output_dir / "keyframe-contact-sheet.png",
    )

    metadata["source"] = str(args.video.resolve())
    report = {
        "schema_version": "1.0",
        "truth_standard": {
            "frame_measurements": "visual-observed",
            "visual_energy_easing_proxy": "inferred",
            "native_timeline": "native-observed when supplied",
        },
        "label": args.label or args.video.stem,
        "video": metadata,
        "analysis": {
            "width": int(gray_frames.shape[2]),
            "height": int(gray_frames.shape[1]),
            "pixel_threshold_8bit": args.pixel_threshold,
            "active_thresholds": thresholds,
        },
        "active_segments": segments,
        "keyframes": keyframes,
        "native_timeline": load_native_timeline(args.timeline_json, args.playback_slide),
        "frame_metrics": metrics,
    }
    (args.output_dir / "playback-analysis.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_metrics_csv(args.output_dir / "frame-metrics.csv", metrics)
    write_markdown(args.output_dir / "playback-analysis.md", report)
    print(
        json.dumps(
            {
                "video": str(args.video),
                "frames": len(gray_frames),
                "fps": metadata["fps"],
                "active_segments": len(segments),
                "keyframes": len(keyframes),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
