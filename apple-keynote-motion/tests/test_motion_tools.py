from __future__ import annotations

import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_slide_transitions import (  # noqa: E402
    build_script,
    copy_deck,
    ui_controls_still_required,
)
from analyze_keynote_reference import main as analyze_keynote_reference_main  # noqa: E402
from build_private_asset_library import (  # noqa: E402
    Detection,
    classify_asset_name,
    deck_id,
    detect_file_kind,
    index_package_metadata,
    media_metadata,
    recover_utf8_zip_name,
    write_summary,
)
from analyze_transition_object_diffs import (  # noqa: E402
    Diagnostics,
    SlideSize,
    load_objects,
    match_cost,
)
from analyze_playback_video import (  # noqa: E402
    boolean_runs,
    bridge_short_gaps,
    choose_keyframes,
    detect_active_segments,
    probe_video,
    visual_energy_fit,
)
from analyze_text_motion_layers import text_objects_for_slide  # noqa: E402
from audit_magic_move_export_risks import (  # noqa: E402
    is_zero_geometry,
    paired_zero_paths,
)
from compare_playback_motion import compare_payloads  # noqa: E402
from extract_native_build_timeline import (  # noqa: E402
    decode_start_relationship,
    describe_target,
    load_slide_order_rows,
    merge_patch_dict,
)
from keynote_archive import KeynoteArchive  # noqa: E402
from make_build_stage_storyboards import discover_pages  # noqa: E402
from make_transition_storyboards import load_pairs  # noqa: E402
from map_build_stages import monotonic_alignment, stage_kind  # noqa: E402
from patch_build_start_relationship import START_FLAGS, patch_deck  # noqa: E402
from recover_slide_order import first_ref_field, slide_transition_and_topic  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
