#!/usr/bin/env python3
"""Validate an Apple Keynote motion-spec JSON file.

The validator checks structure and choreography invariants. It does not claim
that Keynote applied a setting; round-trip extraction and rendered QA are still
required for that.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ALLOWED_TRANSITIONS = {
    "none",
    "magic-move",
    "dissolve",
    "push",
    "object-flip",
}
ALLOWED_ADVANCE = {"on-click", "automatic"}
ALLOWED_EVIDENCE = {
    "native-observed",
    "visual-observed",
    "inferred",
    "recommended",
}
ALLOWED_BUILD_START = {
    "after-transition",
    "on-click",
    "with-build",
    "after-build",
}
ALLOWED_INTENTS = {
    "reveal",
    "refocus",
    "transform",
    "compare",
    "sequence",
    "expand",
    "collapse",
    "reset",
    "payoff",
}
ALLOWED_ROLES = {"continuity", "entry", "exit", "static", "off-canvas"}
ALLOWED_PHASES = {"build-in", "action", "build-out"}
ALLOWED_MAGIC_MOVE_MATCH = {"by-object", "by-word", "by-character"}
ALLOWED_ACCELERATION = {"none", "ease-in", "ease-out", "ease-in-out"}


@dataclass
class Issue:
    severity: str
    path: str
    message: str


def require(condition: bool, severity: str, path: str, message: str, issues: list[Issue]) -> None:
    if not condition:
        issues.append(Issue(severity, path, message))


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def object_ids(state: dict[str, Any]) -> set[str]:
    return {
        obj.get("id")
        for obj in as_list(state.get("objects"))
        if isinstance(obj, dict) and isinstance(obj.get("id"), str) and obj.get("id")
    }


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate(spec: Any) -> list[Issue]:
    issues: list[Issue] = []
    require(isinstance(spec, dict), "error", "$", "The root must be a JSON object.", issues)
    if not isinstance(spec, dict):
        return issues

    require(spec.get("version") == "2.0", "error", "$.version", "Expected motion-spec version 2.0.", issues)
    scenes = as_list(spec.get("scenes"))
    require(bool(scenes), "error", "$.scenes", "Add at least one scene.", issues)

    seen_scene_ids: set[str] = set()
    for scene_index, scene in enumerate(scenes):
        path = f"$.scenes[{scene_index}]"
        require(isinstance(scene, dict), "error", path, "Scene must be an object.", issues)
        if not isinstance(scene, dict):
            continue

        scene_id = scene.get("id")
        require(isinstance(scene_id, str) and bool(scene_id), "error", f"{path}.id", "Scene id is required.", issues)
        if isinstance(scene_id, str):
            require(scene_id not in seen_scene_ids, "error", f"{path}.id", "Scene id must be unique.", issues)
            seen_scene_ids.add(scene_id)

        evidence = scene.get("evidence", "recommended")
        require(evidence in ALLOWED_EVIDENCE, "error", f"{path}.evidence", "Use a supported evidence label.", issues)
        intent = scene.get("intent")
        require(intent in ALLOWED_INTENTS, "error", f"{path}.intent", "Use one supported dominant motion intent.", issues)

        states = as_list(scene.get("states"))
        require(bool(states), "error", f"{path}.states", "Scene needs one or more slide states.", issues)
        state_by_slide: dict[int, dict[str, Any]] = {}
        all_object_ids: set[str] = set()
        for state_index, state in enumerate(states):
            state_path = f"{path}.states[{state_index}]"
            require(isinstance(state, dict), "error", state_path, "State must be an object.", issues)
            if not isinstance(state, dict):
                continue
            slide = state.get("slide")
            require(positive_integer(slide), "error", f"{state_path}.slide", "Slide must be a positive integer.", issues)
            if positive_integer(slide):
                require(slide not in state_by_slide, "error", f"{state_path}.slide", "A scene cannot define the same slide twice.", issues)
                state_by_slide[slide] = state
            ids = object_ids(state)
            require(len(ids) == len(as_list(state.get("objects"))), "warning", f"{state_path}.objects", "Every object should have a unique non-empty id.", issues)
            all_object_ids.update(ids)
            for object_index, obj in enumerate(as_list(state.get("objects"))):
                object_path = f"{state_path}.objects[{object_index}]"
                if not isinstance(obj, dict):
                    require(False, "error", object_path, "Object must be a JSON object.", issues)
                    continue
                require(obj.get("role") in ALLOWED_ROLES, "error", f"{object_path}.role", "Use a supported object role.", issues)
                frame = obj.get("frame")
                require(isinstance(frame, dict), "error", f"{object_path}.frame", "Record x, y, width, and height.", issues)
                if isinstance(frame, dict):
                    for key in ("x", "y", "width", "height"):
                        require(numeric(frame.get(key)), "error", f"{object_path}.frame.{key}", "Frame values must be numeric.", issues)
                    if numeric(frame.get("width")):
                        require(frame["width"] > 0, "error", f"{object_path}.frame.width", "Width must be positive.", issues)
                    if numeric(frame.get("height")):
                        require(frame["height"] > 0, "error", f"{object_path}.frame.height", "Height must be positive.", issues)
                opacity = obj.get("opacity", 100)
                require(numeric(opacity) and 0 <= opacity <= 100, "error", f"{object_path}.opacity", "Opacity must be between 0 and 100.", issues)

        transition = scene.get("transition")
        if transition is not None:
            transition_path = f"{path}.transition"
            require(isinstance(transition, dict), "error", transition_path, "Transition must be an object.", issues)
            if isinstance(transition, dict):
                effect = transition.get("effect")
                require(isinstance(effect, str) and effect in ALLOWED_TRANSITIONS, "error", f"{transition_path}.effect", "Unsupported transition effect.", issues)
                duration = transition.get("duration")
                require(numeric(duration) and 0.1 <= duration <= 20, "error", f"{transition_path}.duration", "Duration must be between 0.1 and 20 seconds.", issues)
                advance = transition.get("advance", "on-click")
                require(advance in ALLOWED_ADVANCE, "error", f"{transition_path}.advance", "Advance must be on-click or automatic.", issues)
                delay = transition.get("delay", 0)
                require(numeric(delay) and delay >= 0, "error", f"{transition_path}.delay", "Delay must be zero or positive.", issues)
                if advance == "on-click" and numeric(delay) and delay != 0:
                    require(False, "warning", f"{transition_path}.delay", "On-click transitions normally use zero delay.", issues)
                from_slide = transition.get("from_slide")
                to_slide = transition.get("to_slide")
                has_from_state = positive_integer(from_slide) and from_slide in state_by_slide
                has_to_state = positive_integer(to_slide) and to_slide in state_by_slide
                require(has_from_state, "error", f"{transition_path}.from_slide", "from_slide must name a scene state.", issues)
                require(has_to_state, "error", f"{transition_path}.to_slide", "to_slide must name a scene state.", issues)
                if has_from_state and has_to_state:
                    require(
                        to_slide == from_slide + 1,
                        "error",
                        f"{transition_path}.to_slide",
                        "to_slide must immediately follow from_slide in the deck.",
                        issues,
                    )

                if effect == "magic-move" and has_from_state and has_to_state:
                    continuity = object_ids(state_by_slide[from_slide]) & object_ids(state_by_slide[to_slide])
                    require(bool(continuity), "error", transition_path, "Magic Move requires at least one stable object id across both states.", issues)
                    mm = transition.get("magic_move")
                    require(isinstance(mm, dict), "error", f"{transition_path}.magic_move", "Record match, fade_unmatched, and acceleration settings.", issues)
                    if isinstance(mm, dict):
                        require(mm.get("match") in ALLOWED_MAGIC_MOVE_MATCH, "error", f"{transition_path}.magic_move.match", "Use by-object, by-word, or by-character.", issues)
                        require(isinstance(mm.get("fade_unmatched"), bool), "error", f"{transition_path}.magic_move.fade_unmatched", "Record an explicit boolean.", issues)
                        require(mm.get("acceleration") in ALLOWED_ACCELERATION, "error", f"{transition_path}.magic_move.acceleration", "Record a supported acceleration.", issues)
                elif isinstance(transition, dict) and "magic_move" in transition:
                    require(False, "warning", f"{transition_path}.magic_move", "Remove Magic Move-only settings from another transition type.", issues)
                if effect == "push":
                    require(isinstance(transition.get("direction"), str), "warning", f"{transition_path}.direction", "Record Push direction from the Keynote UI.", issues)

        builds = as_list(scene.get("builds"))
        seen_build_ids: set[str] = set()
        seen_orders: set[tuple[int, int]] = set()
        for build_index, build in enumerate(builds):
            build_path = f"{path}.builds[{build_index}]"
            require(isinstance(build, dict), "error", build_path, "Build must be an object.", issues)
            if not isinstance(build, dict):
                continue
            build_id = build.get("id")
            require(isinstance(build_id, str) and bool(build_id), "error", f"{build_path}.id", "Build id is required.", issues)
            if isinstance(build_id, str):
                require(build_id not in seen_build_ids, "error", f"{build_path}.id", "Build id must be unique inside the scene.", issues)
                seen_build_ids.add(build_id)
            slide = build.get("slide")
            has_build_state = positive_integer(slide) and slide in state_by_slide
            require(has_build_state, "error", f"{build_path}.slide", "Build slide must name a scene state.", issues)
            target = build.get("target")
            target_ids = object_ids(state_by_slide[slide]) if has_build_state else set()
            require(target in target_ids, "error", f"{build_path}.target", "Build target must name an object on that build slide.", issues)
            require(build.get("phase") in ALLOWED_PHASES, "error", f"{build_path}.phase", "Use build-in, action, or build-out.", issues)
            require(isinstance(build.get("effect"), str) and bool(build.get("effect")), "error", f"{build_path}.effect", "Build effect is required.", issues)
            duration = build.get("duration")
            require(numeric(duration) and 0.05 <= duration <= 20, "error", f"{build_path}.duration", "Build duration must be between 0.05 and 20 seconds.", issues)
            delay = build.get("delay", 0)
            require(numeric(delay) and delay >= 0, "error", f"{build_path}.delay", "Build delay must be zero or positive.", issues)
            start = build.get("start")
            require(start in ALLOWED_BUILD_START, "error", f"{build_path}.start", "Use a supported build start relationship.", issues)
            order = build.get("order")
            require(positive_integer(order), "error", f"{build_path}.order", "Build order must be a positive integer.", issues)
            if has_build_state and positive_integer(order):
                require((slide, order) not in seen_orders, "error", f"{build_path}.order", "Build order must be unique per slide.", issues)
                seen_orders.add((slide, order))
            if start in {"with-build", "after-build"}:
                require(isinstance(build.get("relative_to"), str), "error", f"{build_path}.relative_to", "Relative builds must name another build id.", issues)

        build_by_id = {
            build.get("id"): build
            for build in builds
            if isinstance(build, dict) and isinstance(build.get("id"), str)
        }
        for build_index, build in enumerate(builds):
            if not isinstance(build, dict) or build.get("start") not in {"with-build", "after-build"}:
                continue
            build_path = f"{path}.builds[{build_index}]"
            relative_to = build.get("relative_to")
            has_relative_build = (
                isinstance(relative_to, str) and relative_to in build_by_id
            )
            require(has_relative_build, "error", f"{build_path}.relative_to", "Relative build id does not exist.", issues)
            require(relative_to != build.get("id"), "error", f"{build_path}.relative_to", "A build cannot be relative to itself.", issues)
            relative_build = build_by_id.get(relative_to) if has_relative_build else None
            if isinstance(relative_build, dict):
                require(
                    relative_build.get("slide") == build.get("slide"),
                    "error",
                    f"{build_path}.relative_to",
                    "Relative builds must be on the same slide.",
                    issues,
                )
                relative_order = relative_build.get("order")
                current_order = build.get("order")
                if positive_integer(relative_order) and positive_integer(current_order):
                    require(
                        relative_order < current_order,
                        "error",
                        f"{build_path}.relative_to",
                        "Relative builds must point to an earlier build order.",
                        issues,
                    )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    issues = validate(spec)
    if args.json_output:
        print(json.dumps([asdict(issue) for issue in issues], indent=2))
    elif issues:
        for issue in issues:
            print(f"{issue.severity.upper():7} {issue.path}: {issue.message}")
    else:
        print("Motion spec is structurally valid.")

    return 1 if any(issue.severity == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
