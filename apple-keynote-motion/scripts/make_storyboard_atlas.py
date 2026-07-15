#!/usr/bin/env python3
"""Tile storyboard images deterministically without dropping variable-size inputs."""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

from PIL import Image, ImageOps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--cell-width", type=int, default=900)
    parser.add_argument("--cell-height", type=int, default=600)
    parser.add_argument("--padding", type=int, default=8)
    args = parser.parse_args()

    if min(args.columns, args.rows, args.cell_width, args.cell_height) < 1:
        raise ValueError("Grid and cell dimensions must be positive")
    paths = [Path(path) for path in sorted(glob.glob(args.input_glob))]
    if not paths:
        raise ValueError(f"No images matched: {args.input_glob}")

    per_page = args.columns * args.rows
    page_count = math.ceil(len(paths) / per_page)
    atlas_width = args.columns * args.cell_width + (args.columns + 1) * args.padding
    atlas_height = args.rows * args.cell_height + (args.rows + 1) * args.padding
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, object]] = []

    for page_index in range(page_count):
        selected = paths[page_index * per_page : (page_index + 1) * per_page]
        atlas = Image.new("RGB", (atlas_width, atlas_height), (0, 0, 0))
        for cell_index, path in enumerate(selected):
            with Image.open(path) as source:
                image = ImageOps.contain(
                    source.convert("RGB"),
                    (args.cell_width, args.cell_height),
                    Image.Resampling.LANCZOS,
                )
            row = cell_index // args.columns
            column = cell_index % args.columns
            cell_x = args.padding + column * (args.cell_width + args.padding)
            cell_y = args.padding + row * (args.cell_height + args.padding)
            x = cell_x + (args.cell_width - image.width) // 2
            y = cell_y + (args.cell_height - image.height) // 2
            atlas.paste(image, (x, y))
        output = args.out_dir / f"atlas-{page_index + 1:03d}.jpg"
        atlas.save(output, quality=92, optimize=True)
        outputs.append({"path": str(output), "inputs": [str(path) for path in selected]})

    manifest = {
        "input_glob": args.input_glob,
        "input_count": len(paths),
        "images_per_atlas": per_page,
        "atlas_count": len(outputs),
        "atlases": outputs,
    }
    manifest_path = args.out_dir / "atlas-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "atlases"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
