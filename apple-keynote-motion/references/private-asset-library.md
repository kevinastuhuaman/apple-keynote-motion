# Private Asset Library Workflow

Use this workflow when the user supplies Keynote reference decks and explicitly asks to reuse or study their embedded media.

## Copyright And Provenance Boundary

- Keep extracted media outside the installed or shareable skill.
- Treat the library as private and user-authorized, not redistributable.
- A deck filename or visual appearance does not prove that every embedded asset was created or licensed by Apple.
- Record the source deck, source hash, archive member, resource identifier, and slide-component relation when available.
- Never silently publish, upload, or include extracted media in a skill ZIP.

## Build

The full graph mode requires `keynote-parser`. The script degrades to archive-only metadata when that dependency is unavailable.

```bash
python3 scripts/build_private_asset_library.py \
  --source-dir "/path/to/reference decks" \
  --output-dir "/private/path/keynote-asset-library" \
  --preview-workers 4
```

The output contains:

- `catalog.sqlite`: authoritative searchable index.
- `catalog.csv` and `catalog.json`: portable metadata exports.
- `index.html`: visual browser with deck, media, category, orientation, and text filters.
- `objects/sha256/`: unchanged unique payloads stored by hash.
- `previews/`: derived thumbnails, representative video frames, and audio waveforms.
- `LIBRARY.md`: corpus counts and reuse warning.

## Query

```bash
python3 scripts/query_asset_library.py /private/path/keynote-asset-library \
  --query "iphone camera" \
  --kind image \
  --category product-render \
  --min-width 1600 \
  --exclude-small \
  --limit 20
```

Useful filters:

- `--deck`: restrict to one source deck.
- `--slide`: return assets mapped to an exact source slide; repeat it to match any listed slide.
- `--sha256`: resolve an exact object hash or unique leading prefix.
- `--kind`: image, video, audio, document, or other.
- `--category`: product-render, UI screenshot, component diagram, poster frame, background, photography, graphic, or video motion.
- `--orientation`: landscape, portrait, or square.
- `--with-alpha`: find transparent product cutouts and icons.
- `--min-width`: reject low-resolution source material.
- `--min-height`: combine with width to enforce a minimum inspectable source size.
- `--has-preview`: return only entries with a generated visual or waveform preview.
- `--exclude-small`: remove Keynote-generated small variants.

## Selection Protocol

1. Write the scene role and primary anchor before searching.
2. Search by product, behavior, component, or environment, not by vague mood.
3. Prefer the original-resolution asset over `-small` variants.
4. Inspect every candidate at full size.
5. Confirm whether the asset is tied to a source slide and study that slide's composition.
   Use `--deck` plus `--slide` to recover the full asset set for that source state.
6. Record the selected asset hash and source deck in the task workspace.
7. Preserve crop, mask, and black-level behavior when it is part of the reference treatment.
8. Use a placeholder or user-owned replacement when reuse rights are unclear.

Do not let asset availability dictate the story. Use the library to strengthen an already-defined scene.
