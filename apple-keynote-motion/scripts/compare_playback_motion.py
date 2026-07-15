#!/usr/bin/env python3
"""Compare temporal motion behavior from two playback-analysis JSON reports.

The score measures segment timing, normalized visual-energy progression, peak
timing, and inferred easing-label agreement. It deliberately excludes content,
typography, object identity, composition, and overall Apple design quality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def segment_curve(payload: dict[str, Any], segment: dict[str, Any], samples: int = 101) -> np.ndarray:
    start = int(segment["start_frame"])
    end = int(segment["end_frame"])
    metrics = {
        int(row["frame"]): max(0.0, float(row.get("mean_abs_diff") or 0.0))
        for row in payload.get("frame_metrics", [])
    }
    energy = np.array([metrics.get(frame, 0.0) for frame in range(start, end + 1)])
    if energy.size < 2 or float(energy.sum()) <= 0:
        return np.linspace(0.0, 1.0, samples)
    cumulative = np.cumsum(energy) / float(energy.sum())
    cumulative[0] = 0.0
    cumulative[-1] = 1.0
    source_x = np.linspace(0.0, 1.0, cumulative.size)
    return np.interp(np.linspace(0.0, 1.0, samples), source_x, cumulative)


def ratio_score(first: float, second: float) -> float:
    if first <= 0 or second <= 0:
        return 0.0
    return min(first, second) / max(first, second)


def normalized_peak(segment: dict[str, Any]) -> float:
    start = int(segment["start_frame"])
    end = int(segment["end_frame"])
    if end <= start:
        return 0.5
    return (int(segment["peak_frame"]) - start) / (end - start)


def compare_segments(
    reference_payload: dict[str, Any],
    candidate_payload: dict[str, Any],
    reference_segment: dict[str, Any],
    candidate_segment: dict[str, Any],
) -> dict[str, Any]:
    reference_curve = segment_curve(reference_payload, reference_segment)
    candidate_curve = segment_curve(candidate_payload, candidate_segment)
    curve_mae = float(np.mean(np.abs(reference_curve - candidate_curve)))
    curve_score = max(0.0, 1.0 - curve_mae)
    duration_score = ratio_score(
        float(reference_segment["duration_seconds"]),
        float(candidate_segment["duration_seconds"]),
    )
    reference_easing = reference_segment["visual_energy_easing_proxy"]["best_fit"]
    candidate_easing = candidate_segment["visual_energy_easing_proxy"]["best_fit"]
    easing_score = 1.0 if reference_easing == candidate_easing else 0.0
    peak_delta = abs(normalized_peak(reference_segment) - normalized_peak(candidate_segment))
    peak_score = max(0.0, 1.0 - peak_delta)
    weighted = (
        0.40 * duration_score
        + 0.40 * curve_score
        + 0.10 * easing_score
        + 0.10 * peak_score
    )
    return {
        "reference_duration_seconds": reference_segment["duration_seconds"],
        "candidate_duration_seconds": candidate_segment["duration_seconds"],
        "duration_score": round(duration_score * 100, 3),
        "visual_energy_curve_mae": round(curve_mae, 6),
        "visual_energy_curve_score": round(curve_score * 100, 3),
        "reference_easing_proxy": reference_easing,
        "candidate_easing_proxy": candidate_easing,
        "easing_label_score": round(easing_score * 100, 3),
        "normalized_peak_delta": round(peak_delta, 6),
        "peak_timing_score": round(peak_score * 100, 3),
        "segment_motion_fidelity_score": round(weighted * 100, 3),
    }


def select_segments(payload: dict[str, Any], index: int | None) -> list[dict[str, Any]]:
    segments = payload.get("active_segments", [])
    if index is None:
        return segments
    if index < 1 or index > len(segments):
        raise ValueError(f"segment {index} is outside 1..{len(segments)}")
    return [segments[index - 1]]


def compare_payloads(
    reference_payload: dict[str, Any],
    candidate_payload: dict[str, Any],
    reference_segment_index: int | None = None,
    candidate_segment_index: int | None = None,
) -> dict[str, Any]:
    reference_segments = select_segments(reference_payload, reference_segment_index)
    candidate_segments = select_segments(candidate_payload, candidate_segment_index)
    matched_count = min(len(reference_segments), len(candidate_segments))
    maximum_count = max(len(reference_segments), len(candidate_segments))
    structure_score = matched_count / maximum_count if maximum_count else 1.0
    comparisons = [
        compare_segments(reference_payload, candidate_payload, reference_segments[index], candidate_segments[index])
        for index in range(matched_count)
    ]
    segment_average = (
        sum(row["segment_motion_fidelity_score"] for row in comparisons) / len(comparisons)
        if comparisons
        else 0.0
    )
    overall = 0.85 * segment_average + 0.15 * structure_score * 100
    return {
        "schema_version": "1.0",
        "score_name": "temporal_motion_fidelity",
        "truth_standard": {
            "frame_measurements": "visual-observed",
            "curve_and_easing_comparison": "inferred",
            "score_weights": "recommended",
        },
        "scope": [
            "active segment count",
            "rendered duration",
            "normalized visual-energy progression",
            "peak timing",
            "inferred easing-label agreement",
        ],
        "excluded_from_score": [
            "content and imagery",
            "typography",
            "object identity",
            "layout and composition",
            "semantic attention quality",
            "overall Apple design similarity",
        ],
        "reference_label": reference_payload.get("label"),
        "candidate_label": candidate_payload.get("label"),
        "reference_segment_index": reference_segment_index,
        "candidate_segment_index": candidate_segment_index,
        "reference_segment_count": len(reference_segments),
        "candidate_segment_count": len(candidate_segments),
        "matched_segment_count": matched_count,
        "segment_structure_score": round(structure_score * 100, 3),
        "segments": comparisons,
        "temporal_motion_fidelity_score": round(overall, 3),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Temporal Motion Fidelity",
        "",
        f"- Reference: **{payload.get('reference_label')}**",
        f"- Candidate: **{payload.get('candidate_label')}**",
        f"- Score: **{payload['temporal_motion_fidelity_score']:.3f}/100**",
        f"- Segment structure: **{payload['segment_structure_score']:.3f}/100**",
        "",
        "This is a rendered temporal-motion score, not an overall Apple-design similarity score.",
        "",
        "## Segment Comparison",
        "",
        "| # | Reference duration | Candidate duration | Duration | Energy curve | Peak | Easing | Segment score |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for index, row in enumerate(payload["segments"], start=1):
        lines.append(
            f"| {index} | {row['reference_duration_seconds']:.3f}s | "
            f"{row['candidate_duration_seconds']:.3f}s | {row['duration_score']:.1f} | "
            f"{row['visual_energy_curve_score']:.1f} | {row['peak_timing_score']:.1f} | "
            f"{row['easing_label_score']:.1f} | {row['segment_motion_fidelity_score']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Excluded",
            "",
            *[f"- {item}" for item in payload["excluded_from_score"]],
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--reference-segment", type=int)
    parser.add_argument("--candidate-segment", type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    reference_payload = json.loads(args.reference.read_text(encoding="utf-8"))
    candidate_payload = json.loads(args.candidate.read_text(encoding="utf-8"))
    result = compare_payloads(
        reference_payload,
        candidate_payload,
        args.reference_segment,
        args.candidate_segment,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "motion-fidelity.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "motion-fidelity.md").write_text(
        markdown_report(result), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
