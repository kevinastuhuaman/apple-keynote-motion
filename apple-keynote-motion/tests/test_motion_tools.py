from __future__ import annotations

import csv
import io
import json
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

from apply_slide_transitions import build_script, copy_deck  # noqa: E402
from build_private_asset_library import (  # noqa: E402
    classify_asset_name,
    detect_file_kind,
    index_package_metadata,
    recover_utf8_zip_name,
)
from analyze_playback_video import (  # noqa: E402
    boolean_runs,
    bridge_short_gaps,
    choose_keyframes,
    detect_active_segments,
    visual_energy_fit,
)
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
                                "media_triggers": [],
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
            self.assertEqual(rows[0]["motion_density"], 0.5)


class PrivateAssetLibraryTests(unittest.TestCase):
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
