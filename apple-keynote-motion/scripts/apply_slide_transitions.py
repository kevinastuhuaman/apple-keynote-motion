#!/usr/bin/env python3
"""Apply the slide-transition shell from a motion spec to a deck copy.

This intentionally handles only public AppleScript transition properties. Magic
Move match mode, fade-unmatched, acceleration, and all build details still need
the Keynote UI plus rendered verification.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from validate_motion_spec import validate


EFFECT_LITERAL = {
    "none": "no transition effect",
    "magic-move": "magic move",
    "dissolve": "dissolve",
    "push": "push",
    "object-flip": "object flip",
}


def applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def transition_rows(spec: dict) -> list[dict]:
    rows = []
    for scene in spec.get("scenes", []):
        transition = scene.get("transition")
        if transition:
            rows.append(transition)
    return rows


def ui_controls_still_required(rows: list[dict]) -> list[str]:
    controls = ["Build In/Action/Build Out details and Build Order"]
    if any(row.get("effect") == "magic-move" for row in rows):
        controls[0:0] = [
            "Magic Move match mode",
            "Magic Move fade unmatched objects",
            "Magic Move acceleration",
        ]
    for row in rows:
        if row.get("effect") != "push":
            continue
        direction = " ".join(str(row.get("direction", "unspecified")).splitlines()).strip()
        controls.append(
            f"Push direction on slide {int(row['from_slide'])}: {direction or 'unspecified'}"
        )
    return controls


def build_script(deck: Path, rows: list[dict], keep_open: bool) -> str:
    commands = []
    for row in rows:
        effect = EFFECT_LITERAL[row["effect"]]
        duration = float(row["duration"])
        delay = float(row.get("delay", 0))
        automatic = "true" if row.get("advance", "on-click") == "automatic" else "false"
        if row["effect"] == "push":
            direction = " ".join(str(row.get("direction", "unspecified")).splitlines()).strip()
            commands.append(
                f"-- Manual Keynote UI required: set Push direction on slide "
                f"{int(row['from_slide'])} to {direction or 'unspecified'}"
            )
        commands.append(
            f"set transition properties of slide {int(row['from_slide'])} of docRef to "
            f"{{transition effect:{effect}, transition duration:{duration}, "
            f"transition delay:{delay}, automatic transition:{automatic}}}"
        )

    close_lines = "" if keep_open else "close docRef saving yes\n            set docRef to missing value"
    return f'''set deckPath to {applescript_string(str(deck))}
using terms from application id "com.apple.Keynote"
    tell application id "com.apple.Keynote"
        with timeout of 1800 seconds
            set docRef to missing value
            try
                open (POSIX file deckPath)
                repeat with waitCount from 1 to 1800
                    repeat with candidate in documents
                        try
                            if POSIX path of (file of candidate) is deckPath then set docRef to candidate
                        end try
                    end repeat
                    if docRef is not missing value then exit repeat
                    delay 1
                end repeat
                if docRef is missing value then error "Could not bind the requested Keynote document: " & deckPath
                {chr(10).join(commands)}
                save docRef
                {close_lines}
            on error errorMessage number errorNumber
                if docRef is not missing value then
                    try
                        close docRef saving no
                    end try
                end if
                error errorMessage number errorNumber
            end try
        end timeout
    end tell
end using terms from
'''


def copy_deck(source: Path, output: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, output, copy_function=shutil.copy2)
    else:
        shutil.copy2(source, output)


def output_is_inside_source_package(source: Path, output: Path) -> bool:
    if not source.is_dir():
        return False
    try:
        output.relative_to(source)
    except ValueError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source-deck", type=Path, required=True)
    parser.add_argument("--output-deck", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()

    spec_path = args.spec.expanduser().resolve()
    source = args.source_deck.expanduser().resolve()
    output = args.output_deck.expanduser().resolve()
    if not source.exists():
        parser.error(f"source deck does not exist: {source}")
    if output == source:
        parser.error("source and output must differ; this tool never edits the source deck")
    if output_is_inside_source_package(source, output):
        parser.error("output cannot be inside a package-style source deck")
    if output.exists():
        parser.error(f"output already exists: {output}")

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    issues = validate(spec)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        for issue in errors:
            print(f"ERROR {issue.path}: {issue.message}", file=sys.stderr)
        return 2

    rows = transition_rows(spec)
    script = build_script(output, rows, args.keep_open)
    if args.dry_run:
        print(script)
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    copy_deck(source, output)
    completed = subprocess.run(
        ["osascript", "-"],
        input=script,
        text=True,
        capture_output=True,
    )
    report = {
        "source_deck": str(source),
        "output_deck": str(output),
        "transition_count": len(rows),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "ui_controls_still_required": ui_controls_still_required(rows),
    }
    print(json.dumps(report, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
