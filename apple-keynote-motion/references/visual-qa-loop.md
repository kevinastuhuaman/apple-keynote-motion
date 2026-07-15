# Visual And Motion QA Loop

The skill is not finished when settings have been entered. Finish only after the native deck has been rendered and reviewed.

## 1. Preserve And Identify

- Work on a local scratch copy outside iCloud app-managed folders.
- Record the source path, file size, modification time, and SHA-256 hash.
- Record the Keynote version.
- Keep document and playback slide numbering separate when skipped slides exist.

## 2. Export Ground Truth

Export from the scratch copy:

```bash
mkdir -p audit-output/slide-images
osascript scripts/export_keynote_visuals.applescript deck-render-copy.key audit-output images
osascript scripts/export_keynote_visuals.applescript deck-render-copy.key audit-output stages
```

Keep Apple-owned renders outside the skill. Store only derived measurements and written analysis in shareable skill files.

## 3. Inspect Static States

Check every source/destination pair for:

- correct focal object,
- stable line breaks and text boxes,
- intended continuity objects,
- intended entry/exit objects,
- accidental off-canvas objects,
- crop or mask jumps,
- z-order changes,
- visual center and safe margins,
- black-level and image-edge mismatches.

## 4. Inspect Build Stages

Use the all-stages PDF to recover visible click states. Align the PDF pages to the final slide renders before assigning stages:

```bash
python3 scripts/map_build_stages.py \
  --pdf audit-output/all-stages.pdf \
  --slides-dir audit-output/slide-images \
  --pages-dir audit-output/all-stage-pages \
  --out-dir audit-output/build-stage-map

python3 scripts/make_build_stage_storyboards.py \
  --map-json audit-output/build-stage-map/build-stage-map.json \
  --pages-dir audit-output/all-stage-pages \
  --out-dir audit-output/build-stage-storyboards
```

Record:

- what changes at each click,
- whether builds are simultaneous or sequential,
- whether the slide begins empty, partial, or complete,
- whether the final state matches the next slide's continuity state.
- raw stage count, distinct visual-state count, duplicate hashes, blank pages, and review flags.

The PDF does not expose duration, easing, every action frame, or timed sub-builds within one click-state. It can also emit extra stages for movie starts, incoming transitions, and skipped-slide content. Enrich the map with native motion evidence when separating builds/actions from media-only states. Treat `STATIC` or `MM_PURE` multi-page ranges without native build/action evidence as unattributed until playback proves ownership.

Do not trust final-state similarity as proof that all preceding pages belong to the same slide. Check both adjacent document slides at skipped-slide and transition boundaries. Static slide-image export may also show all animated objects superimposed, so use a live-playback capture when the final state looks implausibly dense.

## 5. Inspect Playback

For each important sequence, review at normal speed and frame by frame. Check:

- acceleration and settling,
- perceived speed relative to travel distance,
- unwanted pauses,
- alpha pops,
- path curvature,
- simultaneous scale/translation behavior,
- whether text remains readable during movement,
- whether the click rhythm supports the narration.

Before export, verify numeric inspector fields from the saved archive. Keynote can display a newly typed duration without persisting it until Return commits the field. Reopen the deck and use `extract_native_build_timeline.py`; do not treat the visible inspector string as final evidence.

For native movie exports, measure every frame and create deterministic review artifacts:

```bash
python3 scripts/analyze_playback_video.py audit-output/sequence.m4v \
  --output-dir audit-output/playback-analysis \
  --label sequence-name
```

This produces frame metrics, active intervals, a contact sheet, and an inferred visual-energy easing proxy. Inspector duration and visible pixel-change duration are different measurements; preserve both.

When a candidate intentionally follows a reference interval, compare the corresponding segments:

```bash
python3 scripts/compare_playback_motion.py \
  reference/playback-analysis.json \
  candidate/playback-analysis.json \
  --reference-segment 1 --candidate-segment 1 \
  --output-dir audit-output/motion-fidelity
```

Read `motion-fidelity-benchmark.md` before reporting the score. It is not an overall Apple design score.

## 6. Test Generalization Blind

When validating a reusable skill rather than one deck:

1. Create at least three unrelated half-built briefs.
2. Duplicate each native source into control and treatment before adding motion.
3. Export both variants with identical codec, resolution, frame rate, slide delay, and build delay.
4. Validate every movie with `ffprobe`.
5. Randomize A/B labels with a sealed mapping.
6. Give reviewers only the anonymous movies and a fixed weighted rubric.
7. Require timestamps and concrete artifact observations.
8. Reveal the mapping only after every report is saved.

Score composition, continuity, timing, readability, narrative focus, and artifacts. A treatment is allowed to lose. A negative result is evidence that the motion did not earn its complexity and should change the recipe.

Do not call reviews independent when one reviewer can see another review or the mapping. Identify agent reviews as agent reviews; do not present them as human audience research.

## 7. Compare Against Intent

Compare the rendered result to `motion-spec.json`. Classify every mismatch:

- implementation mismatch,
- visual mismatch,
- timing mismatch,
- continuity mismatch,
- narrative mismatch.

Fix the highest-attention mismatch first, rerender, and repeat.

## Completion Gate

Do not call a sequence complete until:

- all expected slide/build states render,
- no unexplained pop or blank frame remains,
- no skipped-slide, incoming-transition, or media-start page is mislabeled as a native build,
- continuity objects move as intended,
- text and images remain within bounds,
- timing feels correct in full-screen playback,
- the live deck and motion spec agree,
- claims about reference behavior carry evidence labels.
- any reported similarity score states its scope and exclusions.
- reusable-skill claims include fresh-deck control/treatment evidence, not only reconstruction of one known reference.
