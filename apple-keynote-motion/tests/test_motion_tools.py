from __future__ import annotations

import csv
import io
import inspect
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_magic_move_export_risks as magic_move_audit  # noqa: E402
from apply_slide_transitions import (  # noqa: E402
    build_script,
    copy_deck,
    ui_controls_still_required,
)
from analyze_keynote_reference import main as analyze_keynote_reference_main  # noqa: E402
from analyze_native_motion import (  # noqa: E402
    Snappy as NativeMotionSnappy,
    StringHit,
    analyze as analyze_native_motion_archive,
    decompress_iwa as decompress_native_iwa,
    normalize_effects,
)
from build_private_asset_library import (  # noqa: E402
    Detection,
    classify_asset_name,
    deck_id,
    detect_file_kind,
    index_package_metadata,
    media_metadata,
    process_deck,
    recover_utf8_zip_name,
    write_summary,
)
from analyze_transition_object_diffs import (  # noqa: E402
    Diagnostics,
    MotionIndex,
    ObjectDataset,
    SlideSize,
    analyze as analyze_object_transitions,
    load_objects,
    match_cost,
    minimum_cost_eligible_pairs,
)
from analyze_playback_video import (  # noqa: E402
    boolean_runs,
    bridge_short_gaps,
    choose_keyframes,
    detect_active_segments,
    probe_video,
    visual_energy_fit,
)
from analyze_text_motion_layers import (  # noqa: E402
    analyze as analyze_text_transitions,
    text_objects_for_slide,
)
from audit_magic_move_export_risks import (  # noqa: E402
    classify_risk,
    is_zero_geometry,
    paired_zero_paths,
    report_summary,
)
from compare_playback_motion import compare_payloads  # noqa: E402
from extract_native_build_timeline import (  # noqa: E402
    decode_start_relationship,
    describe_target,
    load_slide_order_rows,
    merge_patch_dict,
    summarize as summarize_build_timeline,
)
from csv_safety import spreadsheet_safe, spreadsheet_safe_row  # noqa: E402
from keynote_archive import KeynoteArchive  # noqa: E402
from make_build_stage_storyboards import discover_pages  # noqa: E402
from make_transition_storyboards import load_pairs  # noqa: E402
from map_build_stages import (  # noqa: E402
    confidence,
    discover_numbered_images,
    monotonic_alignment,
    render_pdf_pages,
    stage_kind,
)
from patch_build_start_relationship import START_FLAGS, patch_deck  # noqa: E402
from recover_slide_order import (  # noqa: E402
    decompress_iwa as decompress_order_iwa,
    first_ref_field,
    slide_transition_and_topic,
)
from summarize_keynote_corpus import build_rows  # noqa: E402
from validate_motion_spec import validate  # noqa: E402


def valid_spec() -> dict:
    return {
        "version": "2.0",
        "scenes": [
            {
                "id": "hero-detail",
                "intent": "refocus",
                "evidence": "recommended",
                "states": [
                    {
                        "slide": 1,
                        "objects": [
                            {
                                "id": "hero",
                                "role": "continuity",
                                "frame": {"x": 100, "y": 100, "width": 500, "height": 500},
                                "opacity": 100,
                            }
                        ],
                    },
                    {
                        "slide": 2,
                        "objects": [
                            {
                                "id": "hero",
                                "role": "continuity",
                                "frame": {"x": 50, "y": 50, "width": 800, "height": 800},
                                "opacity": 100,
                            },
                            {
                                "id": "label",
                                "role": "entry",
                                "frame": {"x": 1000, "y": 400, "width": 600, "height": 120},
                                "opacity": 100,
                            },
                        ],
                    },
                ],
                "transition": {
                    "from_slide": 1,
                    "to_slide": 2,
                    "effect": "magic-move",
                    "duration": 0.8,
                    "advance": "on-click",
                    "delay": 0,
                    "magic_move": {
                        "match": "by-object",
                        "fade_unmatched": True,
                        "acceleration": "ease-in-out",
                    },
                },
                "builds": [
                    {
                        "id": "label-in",
                        "slide": 2,
                        "target": "label",
                        "phase": "build-in",
                        "effect": "dissolve",
                        "duration": 0.4,
                        "start": "after-transition",
                        "delay": 0,
                        "order": 1,
                    }
                ],
            }
        ],
    }


class MotionSpecTests(unittest.TestCase):
    def test_valid_spec_has_no_errors(self) -> None:
        issues = validate(valid_spec())
        self.assertFalse([issue for issue in issues if issue.severity == "error"])

    def test_magic_move_requires_explicit_controls(self) -> None:
        spec = valid_spec()
        spec["scenes"][0]["transition"]["magic_move"] = {}
        paths = {issue.path for issue in validate(spec) if issue.severity == "error"}
        self.assertIn("$.scenes[0].transition.magic_move.match", paths)
        self.assertIn("$.scenes[0].transition.magic_move.fade_unmatched", paths)
        self.assertIn("$.scenes[0].transition.magic_move.acceleration", paths)

    def test_build_target_must_exist_on_that_slide(self) -> None:
        spec = valid_spec()
        spec["scenes"][0]["builds"][0]["target"] = "missing"
        paths = {issue.path for issue in validate(spec) if issue.severity == "error"}
        self.assertIn("$.scenes[0].builds[0].target", paths)

    def test_transition_states_must_be_adjacent_slides(self) -> None:
        spec = valid_spec()
        scene = spec["scenes"][0]
        scene["states"][1]["slide"] = 3
        scene["transition"]["to_slide"] = 3
        scene["builds"][0]["slide"] = 3
        issues = validate(spec)
        self.assertTrue(
            any(
                issue.path == "$.scenes[0].transition.to_slide"
                and "immediately follow" in issue.message
                for issue in issues
            )
        )

    def test_malformed_transition_slide_value_returns_an_issue(self) -> None:
        spec = valid_spec()
        spec["scenes"][0]["transition"]["to_slide"] = []
        issues = validate(spec)
        self.assertTrue(
            any(issue.path == "$.scenes[0].transition.to_slide" for issue in issues)
        )

    def test_boolean_slide_numbers_are_rejected(self) -> None:
        spec = valid_spec()
        spec["scenes"][0]["states"][0]["slide"] = True
        spec["scenes"][0]["transition"]["from_slide"] = True
        paths = {issue.path for issue in validate(spec) if issue.severity == "error"}
        self.assertIn("$.scenes[0].states[0].slide", paths)
        self.assertIn("$.scenes[0].transition.from_slide", paths)

    def test_boolean_build_slide_and_order_are_rejected(self) -> None:
        spec = valid_spec()
        spec["scenes"][0]["builds"][0]["slide"] = True
        spec["scenes"][0]["builds"][0]["order"] = True
        paths = {issue.path for issue in validate(spec) if issue.severity == "error"}
        self.assertIn("$.scenes[0].builds[0].slide", paths)
        self.assertIn("$.scenes[0].builds[0].order", paths)

    def test_unhashable_build_values_return_structured_issues(self) -> None:
        spec = valid_spec()
        spec["scenes"][0]["builds"][0]["target"] = []
        spec["scenes"][0]["builds"][0]["start"] = []
        paths = {issue.path for issue in validate(spec) if issue.severity == "error"}
        self.assertIn("$.scenes[0].builds[0].target", paths)
        self.assertIn("$.scenes[0].builds[0].start", paths)

    def test_relative_build_must_be_on_the_same_slide(self) -> None:
        spec = valid_spec()
        scene = spec["scenes"][0]
        scene["builds"].extend(
            [
                {
                    "id": "hero-in",
                    "slide": 1,
                    "target": "hero",
                    "phase": "build-in",
                    "effect": "dissolve",
                    "duration": 0.4,
                    "start": "after-transition",
                    "delay": 0,
                    "order": 1,
                },
                {
                    "id": "label-follow",
                    "slide": 2,
                    "target": "label",
                    "phase": "action",
                    "effect": "move",
                    "duration": 0.4,
                    "start": "with-build",
                    "relative_to": "hero-in",
                    "delay": 0,
                    "order": 2,
                },
            ]
        )
        issues = validate(spec)
        self.assertTrue(
            any(
                issue.path == "$.scenes[0].builds[2].relative_to"
                and "same slide" in issue.message
                for issue in issues
            )
        )

    def test_relative_build_must_point_to_an_earlier_order(self) -> None:
        spec = valid_spec()
        scene = spec["scenes"][0]
        scene["builds"][0]["start"] = "with-build"
        scene["builds"][0]["relative_to"] = "label-follow"
        scene["builds"].append(
            {
                "id": "label-follow",
                "slide": 2,
                "target": "label",
                "phase": "action",
                "effect": "move",
                "duration": 0.4,
                "start": "on-click",
                "delay": 0,
                "order": 2,
            }
        )
        issues = validate(spec)
        self.assertTrue(
            any(
                issue.path == "$.scenes[0].builds[0].relative_to"
                and "earlier build order" in issue.message
                for issue in issues
            )
        )

    def test_malformed_relative_build_value_returns_an_issue(self) -> None:
        spec = valid_spec()
        build = spec["scenes"][0]["builds"][0]
        build["start"] = "with-build"
        build["relative_to"] = []
        issues = validate(spec)
        self.assertTrue(
            any(issue.path == "$.scenes[0].builds[0].relative_to" for issue in issues)
        )


class StageAlignmentTests(unittest.TestCase):
    def test_monotonic_alignment_keeps_order_and_final_page(self) -> None:
        distances = np.array(
            [
                [0.01, 0.8, 0.9, 0.9, 0.9],
                [0.8, 0.02, 0.01, 0.8, 0.9],
                [0.9, 0.9, 0.8, 0.7, 0.01],
            ],
            dtype=np.float32,
        )
        assignments, _ = monotonic_alignment(distances)
        self.assertEqual(assignments, [0, 2, 4])

    def test_stage_kind_separates_media_from_structural_motion(self) -> None:
        self.assertEqual(stage_kind(2, {"build_effects": ["appear"]}), "build")
        self.assertEqual(stage_kind(2, {"action_effects": ["move"]}), "action")
        self.assertEqual(stage_kind(2, {"media_triggers": ["movie-start"]}), "media-only")
        self.assertEqual(stage_kind(2, {}), "unattributed")


class PlaybackVideoTests(unittest.TestCase):
    def test_gap_bridging_and_runs_keep_short_motion_sequences_together(self) -> None:
        active = np.array([False, True, True, False, False, True, False])
        bridged = bridge_short_gaps(active, maximum_gap=2)
        self.assertEqual(boolean_runs(bridged), [(1, 5)])

    def test_detected_segment_includes_the_prechange_frame(self) -> None:
        metrics = []
        for frame in range(8):
            moving = 2 <= frame <= 5
            metrics.append(
                {
                    "frame": frame,
                    "time_seconds": frame / 60,
                    "mean_abs_diff": 0.01 if moving else 0.0,
                    "changed_fraction": 0.1 if moving else 0.0,
                    "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
                    if moving
                    else None,
                }
            )
        segments, _ = detect_active_segments(metrics, 60.0)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["start_frame"], 1)
        self.assertEqual(segments[0]["end_frame"], 5)

    def test_motion_heavy_clip_does_not_treat_motion_as_noise(self) -> None:
        metrics = [
            {
                "frame": frame,
                "time_seconds": frame / 60,
                "mean_abs_diff": 0.002 + frame * 0.0002 if frame else 0.0,
                "changed_fraction": 0.03 if frame else 0.0,
                "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
                if frame
                else None,
            }
            for frame in range(20)
        ]
        segments, thresholds = detect_active_segments(metrics, 60.0)
        self.assertTrue(segments)
        self.assertLess(thresholds["mean_abs_diff"], metrics[-1]["mean_abs_diff"])

    def test_keyframes_include_endpoints_and_segment_peak(self) -> None:
        segments = [
            {
                "start_frame": 10,
                "end_frame": 30,
                "peak_frame": 24,
            }
        ]
        keyframes = choose_keyframes(50, segments)
        self.assertEqual(keyframes[0], 0)
        self.assertEqual(keyframes[-1], 49)
        self.assertIn(24, keyframes)

    def test_visual_energy_fit_recognizes_linear_progress(self) -> None:
        fit = visual_energy_fit(np.ones(20, dtype=np.float64))
        self.assertEqual(fit["best_fit"], "linear")


class PlaybackComparisonTests(unittest.TestCase):
    @staticmethod
    def payload(duration: float, energy: list[float], easing: str = "ease-in-out") -> dict:
        frame_count = len(energy)
        return {
            "label": "fixture",
            "active_segments": [
                {
                    "start_frame": 0,
                    "end_frame": frame_count - 1,
                    "duration_seconds": duration,
                    "peak_frame": int(np.argmax(energy)),
                    "visual_energy_easing_proxy": {"best_fit": easing},
                }
            ],
            "frame_metrics": [
                {"frame": index, "mean_abs_diff": value}
                for index, value in enumerate(energy)
            ],
        }

    def test_identical_temporal_motion_scores_one_hundred(self) -> None:
        payload = self.payload(1.0, [0.0, 0.1, 0.4, 0.4, 0.1])
        result = compare_payloads(payload, payload, 1, 1)
        self.assertEqual(result["temporal_motion_fidelity_score"], 100.0)

    def test_duration_mismatch_reduces_score(self) -> None:
        reference = self.payload(1.0, [0.0, 0.1, 0.4, 0.4, 0.1])
        candidate = self.payload(2.0, [0.0, 0.1, 0.4, 0.4, 0.1])
        result = compare_payloads(reference, candidate, 1, 1)
        self.assertLess(result["temporal_motion_fidelity_score"], 90.0)

    def test_two_static_intervals_score_full_temporal_fidelity(self) -> None:
        payload = {"label": "static", "active_segments": [], "frame_metrics": []}
        result = compare_payloads(payload, payload)
        self.assertTrue(result["both_intervals_static"])
        self.assertEqual(result["temporal_motion_fidelity_score"], 100.0)


class MagicMoveExportRiskTests(unittest.TestCase):
    def test_zero_geometry_detects_either_empty_dimension(self) -> None:
        self.assertTrue(is_zero_geometry({"width": 0, "height": 10}))
        self.assertTrue(is_zero_geometry({"width": 10, "height": 0}))
        self.assertFalse(is_zero_geometry({"width": 10, "height": 10}))

    def test_paired_zero_paths_require_same_tree_role(self) -> None:
        source = [
            {"path": "slideNumberPlaceholder", "zero_size": True},
            {"path": "ownedDrawables[0]", "zero_size": True},
        ]
        destination = [
            {"path": "slideNumberPlaceholder", "zero_size": True},
            {"path": "ownedDrawables[1]", "zero_size": True},
        ]
        self.assertEqual(paired_zero_paths(source, destination), ["slideNumberPlaceholder"])


class NumberingTests(unittest.TestCase):
    def test_reference_parser_ignores_trailing_record_noise(self) -> None:
        self.assertEqual(first_ref_field(b"\x12\x02\x08\x2a\x07", 2), 42)

    def test_slide_order_parser_recognizes_non_wwdc20_transition_effects(self) -> None:
        transition, _ = slide_transition_and_topic(b"Transition\x00apple:3D-cube")
        self.assertEqual(transition, "apple:3D-cube")

    def test_playback_numbering_skips_unrenderable_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "pairs.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "document_pair",
                        "playback_pair_excluding_skipped",
                        "transition",
                        "duration",
                        "motion_class",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "document_pair": "10->11",
                        "playback_pair_excluding_skipped": "10->skipped",
                    }
                )
                writer.writerow(
                    {
                        "document_pair": "12->13",
                        "playback_pair_excluding_skipped": "11->12",
                    }
                )
            image_map = {number: Path(tmp) / f"slide-{number}.png" for number in range(1, 13)}
            pairs, unresolved = load_pairs(csv_path, image_map, "playback")
            self.assertEqual([(pair["source"], pair["dest"]) for pair in pairs], [(11, 12)])
            self.assertEqual(unresolved[0]["document_pair"], "10->11")


class DeckCopyTests(unittest.TestCase):
    def test_copy_deck_supports_archive_and_package_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.key"
            archive.write_text(json.dumps({"fixture": True}), encoding="utf-8")
            archive_copy = root / "archive-copy.key"
            copy_deck(archive, archive_copy)
            self.assertEqual(archive.read_bytes(), archive_copy.read_bytes())

            package = root / "package.key"
            package.mkdir()
            (package / "index.apxl").write_text("fixture", encoding="utf-8")
            package_copy = root / "package-copy.key"
            copy_deck(package, package_copy)
            self.assertEqual((package_copy / "index.apxl").read_text(encoding="utf-8"), "fixture")

    def test_transition_script_binds_only_the_exact_document_path(self) -> None:
        script = build_script(Path("/tmp/output.key"), [], keep_open=False)
        self.assertIn("POSIX path of (file of candidate) is deckPath", script)
        self.assertNotIn("name of candidate", script)
        self.assertNotIn("expectedName", script)

    def test_push_direction_is_reported_as_a_manual_ui_control(self) -> None:
        rows = [
            {
                "from_slide": 4,
                "to_slide": 5,
                "effect": "push",
                "duration": 0.75,
                "advance": "on-click",
                "delay": 0,
                "direction": "left",
            }
        ]
        script = build_script(Path("/tmp/output.key"), rows, keep_open=False)
        controls = ui_controls_still_required(rows)
        self.assertIn("Manual Keynote UI required", script)
        self.assertIn("Push direction on slide 4: left", controls)


class KeynoteReferenceAnalyzerTests(unittest.TestCase):
    def make_archive(self, path: Path, include_video: bool = False) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Index/Document.iwa", b"document")
            archive.writestr("Index/Slide.iwa", b"slide")
            archive.writestr("preview.jpg", b"preview-bytes")
            if include_video:
                archive.writestr("Data/clip.mov", b"video-bytes")

    def test_metadata_only_mode_does_not_extract_previews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deck = root / "reference.key"
            output = root / "analysis"
            self.make_archive(deck)
            with patch.object(sys, "argv", ["analyze_keynote_reference.py", str(deck), str(output)]):
                self.assertEqual(analyze_keynote_reference_main(), 0)
            summary = json.loads((output / "archive-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["media_extraction"]["preview_samples"], 0)
            self.assertEqual(summary["media_extraction"]["extracted_bytes"], 0)
            self.assertFalse((output / "previews" / "preview.jpg").exists())

    def test_full_media_mode_treats_na_duration_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deck = root / "reference.key"
            output = root / "analysis"
            self.make_archive(deck, include_video=True)
            argv = [
                "analyze_keynote_reference.py",
                str(deck),
                str(output),
                "--media-mode",
                "full",
                "--max-video-samples",
                "1",
            ]
            probe = {
                "format": {"duration": "N/A"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with patch.object(sys, "argv", argv):
                with patch("analyze_keynote_reference.ffprobe", return_value=probe):
                    with patch(
                        "analyze_keynote_reference.subprocess.run",
                        side_effect=FileNotFoundError,
                    ):
                        self.assertEqual(analyze_keynote_reference_main(), 0)
            summary = json.loads(
                (output / "archive-summary.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(summary["top_video_samples"][0]["duration_seconds"])

    def test_preview_extraction_obeys_the_shared_byte_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deck = root / "reference.key"
            output = root / "analysis"
            self.make_archive(deck)
            argv = [
                "analyze_keynote_reference.py",
                str(deck),
                str(output),
                "--media-mode",
                "images",
                "--max-extracted-bytes",
                "1",
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(analyze_keynote_reference_main(), 0)
            summary = json.loads((output / "archive-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["media_extraction"]["preview_samples"], 0)
            self.assertEqual(summary["media_extraction"]["extracted_bytes"], 0)
            self.assertFalse((output / "previews" / "preview.jpg").exists())


class KeynoteArchiveTests(unittest.TestCase):
    def test_closes_outer_archive_when_enter_fails_after_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "broken-after-open.key"
            with zipfile.ZipFile(deck, "w") as zf:
                zf.writestr("Index/Document.iwa", b"document")

            outer = Mock()
            outer.namelist.side_effect = RuntimeError("failed to read members")
            archive = KeynoteArchive(deck)

            with patch("keynote_archive.ZipFile", return_value=outer):
                with self.assertRaisesRegex(RuntimeError, "failed to read members"):
                    archive.__enter__()

            outer.close.assert_called_once_with()
            self.assertIsNone(archive.outer)

    def test_reads_direct_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "direct.key"
            with zipfile.ZipFile(deck, "w") as zf:
                zf.writestr("Index/Document.iwa", b"document")
                zf.writestr("Index/Slide.iwa", b"slide")
                zf.writestr("Data/icon.png", b"image")

            with KeynoteArchive(deck) as archive:
                self.assertEqual(archive.layout, "direct")
                self.assertEqual(archive.read("Index/Slide.iwa"), b"slide")
                self.assertIn("Data/icon.png", archive.namelist())

    def test_reads_wrapped_index_zip_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "wrapped.key"
            nested_bytes = io.BytesIO()
            with zipfile.ZipFile(nested_bytes, "w") as nested:
                nested.writestr("Index/Document.iwa", b"document")
                nested.writestr("Index/Slide.iwa", b"slide")

            prefix = "Event.key_backup/"
            with zipfile.ZipFile(deck, "w") as outer:
                outer.writestr(prefix + "Index.zip", nested_bytes.getvalue())
                outer.writestr(prefix + "Data/icon.png", b"image")
                outer.writestr(prefix + "preview.jpg", b"preview")

            with KeynoteArchive(deck) as archive:
                self.assertEqual(archive.layout, "wrapped-index-zip")
                self.assertEqual(archive.package_prefix, prefix)
                self.assertEqual(archive.read("Index/Slide.iwa"), b"slide")
                self.assertEqual(archive.read("Data/icon.png"), b"image")
                self.assertIn("preview.jpg", archive.namelist())


class ObjectDatasetTests(unittest.TestCase):
    def test_rotation_matching_uses_the_shortest_circular_delta(self) -> None:
        size = SlideSize(1920, 1080)
        source = {
            "x": 100.0,
            "y": 100.0,
            "width": 200.0,
            "height": 200.0,
            "rotation": 359.0,
            "opacity": 100.0,
            "object_index": 1,
        }
        near_wraparound = {**source, "rotation": 1.0}
        far_rotation = {**source, "rotation": 181.0}
        self.assertLess(
            match_cost(source, near_wraparound, size, size),
            match_cost(source, far_rotation, size, size),
        )

    def test_uses_document_row_dimensions_as_the_default_slide_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tsv = Path(tmp) / "objects.tsv"
            fieldnames = [
                "record",
                "slide_number",
                "object_type",
                "object_index",
                "object_name",
                "identity_text",
                "x",
                "y",
                "width",
                "height",
                "rotation",
                "opacity",
                "locked",
                "extra",
            ]
            with tsv.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerow({"record": "document", "width": 1920, "height": 1080})
                writer.writerow(
                    {
                        "record": "object",
                        "slide_number": 1,
                        "object_type": "image",
                        "object_index": 1,
                        "identity_text": "hero.png",
                        "x": 0,
                        "y": 0,
                        "width": 100,
                        "height": 100,
                        "rotation": 0,
                        "opacity": 100,
                    }
                )

            dataset = load_objects(tsv, size_override=None, diagnostics=Diagnostics())
            self.assertEqual(dataset.size_for(1).width, 1920)
            self.assertEqual(dataset.size_for(1).height, 1080)


class NativeBuildTimelineTests(unittest.TestCase):
    def test_selects_arbitrary_deck_slides_from_slide_order_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slide_order = Path(tmp) / "slide-order.csv"
            with slide_order.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "slide_number",
                        "navigator_node_id",
                        "slide_object_id",
                        "archive_name",
                        "transition",
                        "topic",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "slide_number": 31,
                        "archive_name": "Index/Slide-31.iwa",
                        "transition": "apple:magic-move-implied-motion-path",
                        "topic": "AirTag",
                    }
                )
                writer.writerow(
                    {
                        "slide_number": 42,
                        "archive_name": "Index/Slide-42.iwa",
                        "transition": "none",
                        "topic": "Action scene",
                    }
                )

            rows = load_slide_order_rows(slide_order, {42})
            self.assertEqual(rows[0]["document_slide"], 42)
            self.assertEqual(rows[0]["archive_name"], "Index/Slide-42.iwa")
            self.assertEqual(rows[0]["motion_class"], "selected")

    def test_merges_diff_payload_without_discarding_base_build_attributes(self) -> None:
        base = {
            "animationAttributes": {
                "animationType": "Out",
                "effect": "apple:bc-appear",
                "duration": 1.0,
            },
            "customTextDelivery": "kTextDeliveryByObject",
        }
        merge_patch_dict(base, {"animationAttributes": {"effect": "apple:appear"}})
        self.assertEqual(base["animationAttributes"]["effect"], "apple:appear")
        self.assertEqual(base["animationAttributes"]["duration"], 1.0)
        self.assertEqual(base["customTextDelivery"], "kTextDeliveryByObject")

    def test_decodes_trigger_flag_combinations_without_hiding_raw_semantics(self) -> None:
        after_transition = decode_start_relationship(
            order=1,
            automatic=True,
            referent=True,
            current_reference_order=None,
        )
        self.assertEqual(after_transition["label"], "After Transition")

        on_click = decode_start_relationship(
            order=2,
            automatic=False,
            referent=True,
            current_reference_order=1,
        )
        self.assertEqual(on_click["label"], "On Click")

        with_build = decode_start_relationship(
            order=3,
            automatic=True,
            referent=False,
            current_reference_order=2,
        )
        self.assertEqual(with_build["label"], "With Build 2")
        self.assertFalse(with_build["becomes_reference"])

        after_build = decode_start_relationship(
            order=4,
            automatic=True,
            referent=True,
            current_reference_order=2,
        )
        self.assertEqual(after_build["label"], "After Build 3")
        self.assertTrue(after_build["becomes_reference"])

    def test_target_description_follows_text_storage_and_group_children(self) -> None:
        records = {
            "group": {
                "pbtype": "TSD.GroupArchive",
                "data": {
                    "children": [{"identifier": "shape"}],
                    "super": {
                        "geometry": {
                            "position": {"x": 10, "y": 20},
                            "size": {"width": 300, "height": 100},
                        }
                    },
                },
            },
            "shape": {
                "pbtype": "TSWP.ShapeInfoArchive",
                "data": {"isTextBox": True, "ownedStorage": {"identifier": "storage"}},
            },
            "storage": {
                "pbtype": "TSWP.StorageArchive",
                "data": {"text": ["Hello", " world"]},
            },
        }
        target = describe_target("group", records)
        self.assertEqual(target["type"], "group")
        self.assertEqual(target["text"], "Hello / world")
        self.assertEqual(target["geometry"]["width"], 300)


class BuildStartPatcherTests(unittest.TestCase):
    def test_start_modes_map_to_native_trigger_flags(self) -> None:
        self.assertEqual(START_FLAGS["on-click"], (False, True))
        self.assertEqual(START_FLAGS["after-build"], (True, True))
        self.assertEqual(START_FLAGS["with-build"], (True, False))

    def test_refuses_in_place_edits_before_opening_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "fixture.key"
            deck.write_bytes(b"not an archive")
            with self.assertRaisesRegex(ValueError, "in-place edits are disabled"):
                patch_deck(
                    deck,
                    deck,
                    member="Index/Slide.iwa",
                    chunk_identifier="42",
                    mode="with-build",
                )

    def test_refuses_to_overwrite_an_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.key"
            output = Path(tmp) / "output.key"
            source.write_bytes(b"not an archive")
            output.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                patch_deck(
                    source,
                    output,
                    member="Index/Slide.iwa",
                    chunk_identifier="42",
                    mode="with-build",
                )

    def test_rejects_non_index_build_members_before_opening_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.key"
            output = Path(tmp) / "output.key"
            source.write_bytes(b"not an archive")
            with self.assertRaisesRegex(ValueError, "normalized Index"):
                patch_deck(
                    source,
                    output,
                    member="Data/icon.png",
                    chunk_identifier="42",
                    mode="with-build",
                )

    def test_patches_a_member_inside_a_direct_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "direct.key"
            output = root / "patched.key"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("Index/Document.iwa", b"document")
                archive.writestr("Index/Slide.iwa", b"original")
                archive.writestr("Data/icon.png", b"image")

            with patch(
                "patch_build_start_relationship.patch_member",
                return_value=(b"patched", {"changed": True}),
            ):
                report = patch_deck(
                    source,
                    output,
                    member="Index/Slide.iwa",
                    chunk_identifier="42",
                    mode="with-build",
                )

            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("Index/Slide.iwa"), b"patched")
                self.assertEqual(archive.read("Index/Document.iwa"), b"document")
                self.assertEqual(archive.read("Data/icon.png"), b"image")
            self.assertEqual(report["archive_layout"], "direct")

    def test_patches_a_normalized_member_inside_wrapped_index_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "wrapped.key"
            output = root / "patched.key"
            prefix = "Event.key_backup/"
            nested_bytes = io.BytesIO()
            with zipfile.ZipFile(nested_bytes, "w") as nested:
                nested.writestr("Index/Document.iwa", b"document")
                nested.writestr("Index/Slide.iwa", b"original")
            with zipfile.ZipFile(source, "w") as outer:
                outer.writestr(prefix + "Index.zip", nested_bytes.getvalue())
                outer.writestr(prefix + "Data/icon.png", b"image")

            change = {"before": {"automatic": False}, "after": {"automatic": True}}
            with patch(
                "patch_build_start_relationship.patch_member",
                return_value=(b"patched", change),
            ):
                report = patch_deck(
                    source,
                    output,
                    member="Index/Slide.iwa",
                    chunk_identifier="42",
                    mode="with-build",
                )

            with zipfile.ZipFile(output) as outer:
                self.assertEqual(outer.read(prefix + "Data/icon.png"), b"image")
                with zipfile.ZipFile(
                    io.BytesIO(outer.read(prefix + "Index.zip"))
                ) as nested:
                    self.assertEqual(nested.read("Index/Slide.iwa"), b"patched")
                    self.assertEqual(nested.read("Index/Document.iwa"), b"document")
            self.assertEqual(report["archive_layout"], "wrapped-index-zip")


class ReferenceConsistencyTests(unittest.TestCase):
    def test_native_transition_control_reference_preserves_rare_counts(self) -> None:
        text = (SKILL_ROOT / "references" / "native-transition-controls.md").read_text(
            encoding="utf-8"
        )

        def data_rows(start: str, end: str) -> list[str]:
            section = text.split(start, 1)[1].split(end, 1)[0]
            return [
                line
                for line in section.splitlines()
                if line.startswith("| ")
                and not line.startswith("| ---")
                and "Document / playback" not in line
                and "Source document / playback" not in line
            ]

        self.assertEqual(len(data_rows("## Automatic Transitions", "Automatic delays often")), 25)
        self.assertEqual(len(data_rows("## Push Controls", "The four horizontal")), 5)
        self.assertEqual(
            len(data_rows("The non-object match exceptions are:", "The non-default acceleration")),
            4,
        )
        self.assertEqual(
            len(data_rows("The non-default acceleration exceptions are:", "By Object with")),
            5,
        )
        self.assertIn("document pair `290->291`", text)
        self.assertIn("playback pair `288->289`", text)


class ShareabilityTests(unittest.TestCase):
    def test_text_resources_do_not_hardcode_a_local_keynote_app_path(self) -> None:
        text_suffixes = {".md", ".py", ".applescript", ".yaml", ".csv"}
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in SKILL_ROOT.rglob("*")
            if path.is_file() and path.suffix in text_suffixes
        )
        local_app_path = "/Applications/" + "Keynote Creator Studio.app"
        local_username = "kevin" + "astuhuamanflores"
        self.assertNotIn(local_app_path, combined)
        self.assertNotIn(local_username, combined)

    def test_transition_applescript_targets_portable_bundle_identifier(self) -> None:
        script = build_script(Path("/tmp/output.key"), [], keep_open=False)
        self.assertIn('application id "com.apple.Keynote"', script)
        self.assertNotIn("/Applications/Keynote", script)

    def test_file_automation_binds_documents_only_by_exact_path(self) -> None:
        for name in (
            "dump_keynote_native_state_bulk.applescript",
            "dump_slide_transition_settings.applescript",
            "export_keynote_visuals.applescript",
        ):
            script = (SKILL_ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("POSIX path of (file of candidate) is deckPath", script)
            self.assertNotIn("name of candidate is expected", script)

    def test_range_dump_always_emits_schema_and_document_metadata(self) -> None:
        script = (
            SKILL_ROOT / "scripts" / "dump_keynote_native_state_bulk.applescript"
        ).read_text(encoding="utf-8")
        self.assertNotIn("if requestedStart is 1 then", script)
        self.assertIn('{"record", "slide_number", "object_type"', script)
        self.assertIn('{"document", "", "", ""', script)

    def test_movie_export_restores_open_document_state(self) -> None:
        script = (
            SKILL_ROOT / "scripts" / "export_keynote_movie_pair.applescript"
        ).read_text(encoding="utf-8")
        self.assertIn("set originalSkippedStates to skipped of every slide", script)
        self.assertIn(
            "my restoreSkippedStates(referenceDocument, originalSkippedStates)", script
        )
        self.assertIn("set documentCountBeforeOpen to count of documents", script)
        self.assertIn(
            "set openedHere to ((count of documents) > documentCountBeforeOpen)",
            script,
        )
        self.assertEqual(script.count("set referenceDocument to open sourceFile"), 1)
        self.assertNotIn("repeat with openAttempt", script)
        self.assertIn("if openedHere then close referenceDocument saving no", script)


class ReviewRegressionTests(unittest.TestCase):
    def test_text_motion_includes_text_bearing_shapes_only(self) -> None:
        dataset = Mock(
            objects={
                1: [
                    {
                        "object_type": "shape",
                        "identity_text": "Callout",
                        "width": 200.0,
                        "height": 80.0,
                    },
                    {
                        "object_type": "shape",
                        "identity_text": "",
                        "width": 200.0,
                        "height": 80.0,
                    },
                    {
                        "object_type": "text item",
                        "identity_text": "Label",
                        "width": 200.0,
                        "height": 80.0,
                    },
                ]
            }
        )
        objects = text_objects_for_slide(dataset, 1)
        self.assertEqual([obj["identity_text"] for obj in objects], ["Callout", "Label"])

    def test_video_probe_falls_back_from_na_metadata(self) -> None:
        payload = {
            "streams": [
                {
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "60/1",
                    "avg_frame_rate": "60/1",
                    "duration": "N/A",
                    "nb_frames": "N/A",
                }
            ],
            "format": {"duration": "2.5", "size": "4096"},
        }
        with patch("analyze_playback_video.run_json", return_value=payload):
            metadata = probe_video(Path("sample.m4v"))
        self.assertEqual(metadata["duration_seconds"], 2.5)
        self.assertEqual(metadata["frame_count"], 150)

    def test_storyboard_pages_normalize_zero_based_render_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = directory / "stage-page-0.png"
            second = directory / "stage-page-1.png"
            first.touch()
            second.touch()
            self.assertEqual(discover_pages(directory), {1: first, 2: second})


class CorpusSummaryTests(unittest.TestCase):
    def test_aggregates_normalized_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "inventory" / "sample"
            native = root / "native-motion" / "sample"
            order = native / "slide-order"
            inventory.mkdir(parents=True)
            order.mkdir(parents=True)
            (inventory / "archive-summary.json").write_text(
                json.dumps(
                    {
                        "deck": "/source/sample.key",
                        "archive_layout": "wrapped-index-zip",
                        "deck_size_bytes": 100,
                    }
                ),
                encoding="utf-8",
            )
            (native / "native-motion-summary.json").write_text(
                json.dumps(
                    {
                        "slide_count": 2,
                        "transition_slide_count": 1,
                        "transition_counts": {
                            "apple:magic-move-implied-motion-path": 1,
                            "none": 1,
                        },
                        "motion_class_counts": {"MM_PLUS_BUILD": 1, "STATIC": 1},
                        "slides_archive_sorted": [
                            {
                                "transition": "apple:magic-move-implied-motion-path",
                                "build_effects": ["apple:dissolve"],
                                "action_effects": [],
                                "media_triggers": [],
                            },
                            {
                                "transition": "none",
                                "build_effects": [],
                                "action_effects": [],
                                "media_triggers": ["movie-start"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (order / "slide-order-summary.json").write_text(
                json.dumps({"ordered_slide_count": 2}), encoding="utf-8"
            )

            rows = build_rows(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["magic_move"], 1)
            self.assertEqual(rows[0]["slides_with_builds"], 1)
            self.assertEqual(rows[0]["slides_with_media"], 1)
            self.assertEqual(rows[0]["motion_density"], 1.0)


class PrivateAssetLibraryTests(unittest.TestCase):
    def test_media_metadata_treats_na_duration_as_missing(self) -> None:
        detection = Detection("video/mp4", "video", ".mp4")
        probe = {
            "format": {"duration": "N/A"},
            "streams": [{"codec_type": "video", "codec_name": "h264"}],
        }
        with patch("build_private_asset_library.ffprobe", return_value=probe):
            metadata = media_metadata(Path("clip.mp4"), detection)
        self.assertIsNone(metadata["duration"])

    def test_deck_ids_disambiguate_same_named_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first" / "Event.key"
            second = root / "second" / "Event.key"
            self.assertNotEqual(deck_id(first), deck_id(second))
            self.assertEqual(deck_id(first), deck_id(first))

    def test_empty_library_summary_reports_zero_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            connection = sqlite3.connect(":memory:")
            try:
                connection.executescript(
                    """
                    CREATE TABLE objects (sha256 TEXT PRIMARY KEY, kind TEXT);
                    CREATE TABLE occurrences (deck_id TEXT, sha256 TEXT, size_bytes INTEGER);
                    """
                )
                write_summary(connection, Path(tmp))
            finally:
                connection.close()
            summary = (Path(tmp) / "LIBRARY.md").read_text(encoding="utf-8")
            self.assertIn("Indexed occurrence bytes: **0**", summary)

    def test_recovers_utf8_names_stored_without_zip_utf8_flag(self) -> None:
        original = "iPhone 紫色.png"
        mojibake = original.encode("utf-8").decode("cp437")
        self.assertEqual(recover_utf8_zip_name(mojibake), original)

    def test_detects_magic_bytes_instead_of_trusting_extension(self) -> None:
        detection = detect_file_kind(b"\x89PNG\r\n\x1a\n" + b"0" * 20, "asset.icns")
        self.assertEqual(detection.mime, "image/png")
        self.assertEqual(detection.extension, ".png")

    def test_classifies_common_apple_asset_roles(self) -> None:
        self.assertEqual(classify_asset_name("iPhone 12 purple.png", "image")[0], "product-render")
        self.assertEqual(classify_asset_name("Control Center screen.png", "image")[0], "ui-screenshot")
        self.assertEqual(classify_asset_name("camera sensor.png", "image")[0], "component-diagram")

    def test_indexes_data_references_by_component(self) -> None:
        metadata = {
            "datas": [
                {
                    "identifier": "12",
                    "fileName": "Hero-12.png",
                    "preferredFileName": "Hero.png",
                }
            ],
            "components": [
                {
                    "identifier": "90",
                    "preferredLocator": "Slide",
                    "locator": "Slide-90",
                    "dataReferences": [
                        {
                            "dataIdentifier": "12",
                            "objectReferenceList": [{"objectIdentifier": "91", "count": 1}],
                        }
                    ],
                }
            ],
        }
        index = index_package_metadata(metadata)
        self.assertEqual(index["data_by_filename"]["hero-12.png"]["identifier"], "12")
        relation = index["relations_by_data_id"]["12"][0]
        self.assertEqual(relation["locator"], "Slide-90")
        self.assertEqual(relation["object_ids"], ["91"])


class FinalReviewRegressionTests(unittest.TestCase):
    def test_iwa_decoders_reject_truncated_headers_and_payloads(self) -> None:
        decoder = Mock()
        decoder.uncompress.side_effect = lambda value: value
        for decompress in (decompress_native_iwa, decompress_order_iwa):
            with self.subTest(decompress=decompress.__module__, case="header"):
                with self.assertRaisesRegex(RuntimeError, "truncated IWA chunk header"):
                    decompress(b"\x01\x00\x00", decoder)
            with self.subTest(decompress=decompress.__module__, case="payload"):
                with self.assertRaisesRegex(RuntimeError, "truncated IWA chunk payload"):
                    decompress(b"\x01\x05\x00\x00ab", decoder)

    def test_iwa_decoders_bound_the_total_decoded_payload(self) -> None:
        decoder = Mock()
        decoder.uncompress.side_effect = lambda value: value
        framed = b"\x01\x02\x00\x00ab" + b"\x01\x02\x00\x00cd"
        for module, decompress in (
            ("analyze_native_motion", decompress_native_iwa),
            ("recover_slide_order", decompress_order_iwa),
        ):
            with self.subTest(module=module):
                with patch(f"{module}.MAX_DECODED_IWA_BYTES", 3):
                    with self.assertRaisesRegex(RuntimeError, "safety limit"):
                        decompress(framed, decoder)

    def test_snappy_rejects_oversized_advertised_output(self) -> None:
        snappy = NativeMotionSnappy.__new__(NativeMotionSnappy)
        library = Mock()

        def advertise_oversized(_data, _length, output_length) -> int:
            output_length._obj.value = 2
            return 0

        library.snappy_uncompressed_length.side_effect = advertise_oversized
        snappy.lib = library
        with patch("analyze_native_motion.MAX_DECODED_CHUNK_BYTES", 1):
            with self.assertRaisesRegex(RuntimeError, "safety limit"):
                snappy.uncompress(b"x")
        library.snappy_uncompress.assert_not_called()

    def test_native_motion_report_uses_only_the_deck_basename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "private-location.key"
            with zipfile.ZipFile(deck, "w") as archive:
                archive.writestr("Index/Document.iwa", b"document")
            with patch("analyze_native_motion.Snappy", return_value=Mock()):
                report = analyze_native_motion_archive(deck)
            self.assertEqual(report["deck"], "private-location.key")
            self.assertNotIn(tmp, report["deck"])

    def test_nested_index_zip_respects_the_decompression_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "wrapped.key"
            nested_bytes = io.BytesIO()
            with zipfile.ZipFile(nested_bytes, "w") as nested:
                nested.writestr("Index/Document.iwa", b"document")
            with zipfile.ZipFile(deck, "w") as outer:
                outer.writestr("Event.key_backup/Index.zip", nested_bytes.getvalue())
            with patch("keynote_archive.MAX_NESTED_INDEX_BYTES", 1):
                with self.assertRaisesRegex(ValueError, "safety limit"):
                    with KeynoteArchive(deck):
                        pass

    def test_nested_index_zip_skips_an_oversized_decoy_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "wrapped.key"
            valid_bytes = io.BytesIO()
            with zipfile.ZipFile(valid_bytes, "w") as nested:
                nested.writestr("Index/Document.iwa", b"document")
            valid_payload = valid_bytes.getvalue()
            with zipfile.ZipFile(deck, "w") as outer:
                outer.writestr("A.key_backup/Index.zip", b"x" * (len(valid_payload) + 1))
                outer.writestr("B.key_backup/Index.zip", valid_payload)
            with patch("keynote_archive.MAX_NESTED_INDEX_BYTES", len(valid_payload)):
                with KeynoteArchive(deck) as archive:
                    self.assertEqual(archive.layout, "wrapped-index-zip")
                    self.assertEqual(archive.package_prefix, "B.key_backup/")

    def test_magic_move_cli_summary_reports_unknown_risks(self) -> None:
        report = {
            "magic_move_pairs": 1,
            "high_risk_pairs": 0,
            "medium_risk_pairs": 0,
            "mitigated_pairs": 0,
            "unknown_risk_pairs": 1,
        }
        self.assertEqual(
            report_summary(report, Path("audit"))["unknown_risk_pairs"],
            1,
        )

    def test_eligible_matching_maximizes_pair_count_before_cost(self) -> None:
        source = [
            {"label": "A", "object_type": "shape", "object_index": 1},
            {"label": "B", "object_type": "shape", "object_index": 2},
        ]
        destination = [
            {"label": "X", "object_type": "shape", "object_index": 1},
            {"label": "Y", "object_type": "shape", "object_index": 2},
        ]
        costs = {("A", "X"): 1.0, ("A", "Y"): 2.0, ("B", "X"): 1.1}
        pairs = minimum_cost_eligible_pairs(
            source,
            destination,
            lambda left, right: costs[(left["label"], right["label"])],
            lambda left, right: (left["label"], right["label"]) in costs,
        )
        self.assertEqual(
            {(left["label"], right["label"]) for left, right in pairs},
            {("A", "Y"), ("B", "X")},
        )

    def test_eligible_matching_orients_lopsided_inputs_around_smaller_side(self) -> None:
        source = [
            {"label": str(index), "object_type": "shape", "object_index": index}
            for index in range(1_000)
        ]
        destination = [{"label": "target", "object_type": "shape", "object_index": 1}]
        started = time.perf_counter()
        pairs = minimum_cost_eligible_pairs(
            source,
            destination,
            lambda left, _right: float(left["object_index"]),
            lambda _left, _right: True,
        )
        elapsed = time.perf_counter() - started
        self.assertEqual(pairs[0][0]["object_index"], 0)
        self.assertIs(pairs[0][1], destination[0])
        self.assertLess(elapsed, 2.0)

    def test_transition_analyzers_skip_pairs_without_a_destination_slide(self) -> None:
        dataset = ObjectDataset(
            objects={1: []},
            slide_settings={1: {}},
            slide_sizes={},
            default_size=SlideSize(1920.0, 1080.0),
            object_count=0,
        )
        transitions = [{"slide_number": 1, "archive_name": "Index/Slide-1.iwa"}]
        for analyzer in (analyze_object_transitions, analyze_text_transitions):
            diagnostics = Diagnostics()
            with self.subTest(analyzer=analyzer.__module__):
                rows, _methods = analyzer(
                    transitions,
                    MotionIndex({}, {}),
                    dataset,
                    diagnostics,
                )
                self.assertEqual(rows, [])
                self.assertEqual(diagnostics.counts["missing_destination_slide"], 1)

    def test_native_motion_preserves_a_build_matching_the_transition_id(self) -> None:
        transition, effect_groups, _visible_text = normalize_effects(
            [
                StringHit("Transition", 0),
                StringHit("apple:dissolve", 10),
                StringHit("apple:dissolve", 20),
            ]
        )
        self.assertEqual(transition, "apple:dissolve")
        self.assertEqual(effect_groups["transition_effects"], ["apple:dissolve"])
        self.assertEqual(effect_groups["build_effects"], ["apple:dissolve"])

    def test_csv_safety_neutralizes_spreadsheet_formulas(self) -> None:
        for value in (
            "=1+1",
            "+cmd",
            "-2+3",
            "@SUM(A:A)",
            "\t=1",
            "\r=1",
            "  =1+1",
            "\n@SUM(A:A)",
            "\x00+cmd",
        ):
            with self.subTest(value=value):
                self.assertEqual(spreadsheet_safe(value), "'" + value)
        self.assertEqual(
            spreadsheet_safe_row({"name": "=payload", "count": 2}),
            {"name": "'=payload", "count": 2},
        )

    def test_every_csv_exporter_uses_the_spreadsheet_guard(self) -> None:
        for path in sorted(SCRIPTS.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "csv.DictWriter" in text:
                with self.subTest(path=path.name):
                    self.assertIn("spreadsheet_safe_row", text)

    def test_asset_index_replacement_has_no_partial_commit(self) -> None:
        self.assertNotIn("connection.commit", inspect.getsource(process_deck))

    def test_incomplete_magic_move_indexing_is_never_risk_free(self) -> None:
        self.assertEqual(classify_risk([], [], [], None, True), "unknown")
        self.assertEqual(classify_risk([], [], [], None, False), "none")
        self.assertEqual(classify_risk(["ownedDrawables[0]"], [], [], True, True), "high")

    def test_unrelated_index_failure_does_not_taint_resolved_magic_move_pair(self) -> None:
        archive = Mock()
        archive_context = Mock()
        archive_context.__enter__ = Mock(return_value=archive)
        archive_context.__exit__ = Mock(return_value=False)
        resolver = Mock()
        resolver.failed_index_members = ["Index/Unrelated.iwa"]
        rows = [
            {
                "slide_number": 1,
                "archive_name": "Index/Slide-1.iwa",
                "transition": "apple:magic-move-implied-motion-path",
            },
            {
                "slide_number": 2,
                "archive_name": "Index/Slide-2.iwa",
                "transition": "none",
            },
        ]
        with (
            patch.object(magic_move_audit, "recover", return_value={"rows": rows}),
            patch.object(magic_move_audit, "KeynoteArchive", return_value=archive_context),
            patch.object(
                magic_move_audit,
                "CrossFileRecordResolver",
                return_value=resolver,
            ),
            patch.object(
                magic_move_audit,
                "slide_drawable_tree",
                side_effect=[([], {}), ([], {})],
            ),
        ):
            report = magic_move_audit.audit(Path("deck.key"))
        self.assertEqual(report["findings"][0]["risk"], "none")
        self.assertFalse(report["findings"][0]["indexing_incomplete"])
        self.assertEqual(report["indexing_failures"], ["Index/Unrelated.iwa"])

    def test_unresolved_targets_contribute_to_timeline_coverage(self) -> None:
        summary = summarize_build_timeline(
            [
                {
                    "events": [],
                    "unresolved_chunk_references": [],
                    "unresolved_build_references": [],
                    "unresolved_target_references": ["target-42"],
                }
            ]
        )
        self.assertEqual(summary["slides_with_unresolved_references"], 1)
        self.assertEqual(summary["unresolved_target_reference_count"], 1)

    def test_force_render_ignores_metadata_and_removes_stale_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "stages.pdf"
            pdf.touch()
            pages = root / "pages"
            pages.mkdir()
            metadata = pages / ".DS_Store"
            metadata.write_bytes(b"metadata")
            stale = pages / "stage-page-1.jpg"
            stale.write_bytes(b"stale")

            def render_page(command: list[str], **_kwargs: object) -> None:
                Path(command[-1] + "-1.jpg").write_bytes(b"replacement")

            with (
                patch("map_build_stages.pdf_page_count", return_value=1),
                patch("map_build_stages.shutil.which", return_value="/usr/bin/pdftoppm"),
                patch("map_build_stages.subprocess.run", side_effect=render_page) as run,
            ):
                render_pdf_pages(pdf, pages, 640, force=True)
            self.assertEqual(stale.read_bytes(), b"replacement")
            self.assertTrue(metadata.exists())
            run.assert_called_once()

    def test_force_render_preserves_cache_when_renderer_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "stages.pdf"
            pdf.touch()
            pages = root / "pages"
            pages.mkdir()
            stale = pages / "stage-page-1.jpg"
            stale.write_bytes(b"stale")
            with patch("map_build_stages.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "pdftoppm is required"):
                    render_pdf_pages(pdf, pages, 640, force=True)
            self.assertTrue(stale.exists())

    def test_force_render_preserves_cache_when_replacement_render_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "stages.pdf"
            pdf.touch()
            pages = root / "pages"
            pages.mkdir()
            stale = pages / "stage-page-1.jpg"
            stale.write_bytes(b"known-good")
            with (
                patch("map_build_stages.pdf_page_count", return_value=1),
                patch("map_build_stages.shutil.which", return_value="/usr/bin/pdftoppm"),
                patch(
                    "map_build_stages.subprocess.run",
                    side_effect=subprocess.CalledProcessError(1, "pdftoppm"),
                ),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    render_pdf_pages(pdf, pages, 640, force=True)
            self.assertEqual(stale.read_bytes(), b"known-good")

    def test_stage_page_cache_rejects_gapped_numbering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pages = Path(tmp)
            (pages / "stage-page-1.jpg").touch()
            (pages / "stage-page-3.jpg").touch()
            with self.assertRaisesRegex(ValueError, "contiguous sequence"):
                discover_numbered_images(pages, prefix="stage-page")

    def test_confidence_retains_absolute_quality_limits(self) -> None:
        self.assertEqual(confidence(0.50, 0.50), "low")
        self.assertEqual(confidence(0.10, 0.50), "medium")
        self.assertEqual(confidence(0.07, 0.50), "high")

    def test_dump_scripts_normalize_paths_and_cleanup_on_errors(self) -> None:
        for name in (
            "dump_slide_transition_settings.applescript",
            "dump_keynote_native_state_bulk.applescript",
        ):
            script = (SCRIPTS / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("on canonicalPath(pathText)", script)
                self.assertIn("set deckPath to my canonicalPath(deckPath)", script)
                self.assertIn("on error errorMessage number errorNumber", script)
                self.assertGreaterEqual(
                    script.count("if openedHere and docRef is not missing value then"),
                    2,
                )

    def test_visual_export_normalizes_paths_and_cleanup_on_errors(self) -> None:
        script = (SCRIPTS / "export_keynote_visuals.applescript").read_text(
            encoding="utf-8"
        )
        self.assertIn("on canonicalPath(pathText)", script)
        self.assertIn("set deckPath to my canonicalPath(item 1 of argv)", script)
        self.assertIn("on error errorMessage number errorNumber", script)
        self.assertGreaterEqual(
            script.count("if openedHere and docRef is not missing value then"),
            2,
        )

    def test_combined_motion_class_counts_cover_all_document_slides(self) -> None:
        text = (
            SKILL_ROOT / "references" / "combined-motion-taxonomy.md"
        ).read_text(encoding="utf-8")
        section = text.split("## Combined Motion Classes", 1)[1].split(
            "## Canonical Study Sequences", 1
        )[0]
        counts = [
            int(value)
            for value in re.findall(r"^\| `[^`]+` \| (\d+) \|", section, re.MULTILINE)
        ]
        self.assertEqual(sum(counts), 472)

    def test_visual_archetype_pairs_match_the_canonical_number_map(self) -> None:
        with (
            SKILL_ROOT / "references" / "transition-number-map.csv"
        ).open(newline="", encoding="utf-8") as stream:
            canonical = {
                (row["document_pair"], row["playback_pair_excluding_skipped"])
                for row in csv.DictReader(stream)
                if row["playback_pair_excluding_skipped"] != "skipped"
            }
        text = (
            SKILL_ROOT / "references" / "visual-transition-archetypes.md"
        ).read_text(encoding="utf-8")
        cited = set(re.findall(r"`(\d+->\d+)/(\d+->\d+)`", text))
        self.assertFalse(cited - canonical, sorted(cited - canonical))

    def test_reference_corpus_labels_its_archive_population(self) -> None:
        text = (SKILL_ROOT / "references" / "reference-corpus.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("465 unique `Index/Slide*.iwa` records", text)
        self.assertIn("472 document slides and 106 Magic Move transitions", text)


if __name__ == "__main__":
    unittest.main()
