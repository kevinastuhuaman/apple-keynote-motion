# Evidence And Confidence

## Confidence Policy

Treat Keynote forensics as a layered evidence problem:

1. `native-observed`: a property read from Keynote, its scripting dictionary, or a validated archive field.
2. `visual-observed`: a behavior visible in exported build stages or playback frames.
3. `inferred`: a likely relationship reconstructed from text, filenames, geometry, or visual matching.
4. `recommended`: a new design choice based on the reference grammar.

State the level whenever a claim affects implementation. Never silently upgrade an inference into a native fact.

## Reliable WWDC20 Claims

The following were cross-checked against Keynote slide-transition settings:

- 472 document slides.
- 106 Magic Move transitions.
- 8 Dissolve transitions.
- 5 Push transitions.
- 1 Object Flip transition.
- 352 slides with no slide-level transition.
- Slide-level effect, duration, delay, automatic/on-click state, and skipped flag.
- All 120 transition source slides were also inspected in Keynote 15.3's Animate sidebar. For Magic Move this adds Fade Unmatched Objects, Match mode, and acceleration; for Push it adds direction. See `native-transition-controls.md`.

## Inferred WWDC20 Claims

The current object continuity, movement, scale, appearance, disappearance, and complexity values are heuristic because Keynote does not expose its private Magic Move identity graph. The source dump also includes blank placeholders and ambiguous repeated image filenames.

Use those values to find candidates, not as exact ground truth. Confirm important sequences visually before copying them.

## Rendered WWDC20 Coverage

Keynote 15.3 exported:

- 468 playback slide images from 472 document slides; four document slides are skipped.
- 119 visually reviewable transition pairs; document `436->437` ends on a skipped destination and has no visible playback pair.
- 770 all-stages PDF pages.
- 239 slides with more than one exported PDF state.
- 118 multi-stage slides with native build/action evidence after separating media-only stage changes.

Monotonic visual alignment matched final PDF states to slide-image renders with one low-confidence case: playback 104. Poppler rendered that PDF page blank because the PDF contains malformed embedded JPEG 2000 data, while the slide-image export contains the expected artwork.

These counts are `visual-observed` for this local Keynote 15.3 render. They do not prove exact effect parameters, intermediate trajectories, or timing.

## Known Coverage Limits

- Current native effect extraction scans schema-less printable strings.
- Presence counts are not necessarily build-instance counts.
- Build target, order, duration, delay, acceleration, direction, and delivery are not recovered from those strings.
- All-stages PDF exposes discrete states but can omit continuous action frames and collapse timed sub-builds into one state.
- All-stages PDF can include media-start states; multi-page does not automatically mean text/image build choreography.
- An all-stages PDF can leak an incoming transition state or a skipped document slide into the apparent stage range of a neighboring playback slide. Quarantine `unattributed-multi-stage` ranges instead of teaching them as native builds.
- A high final-state image match validates the selected final page only. It does not prove ownership or correctness of every preceding page in that range.
- Static slide-image export can superimpose animated objects and therefore may not equal a clean live-playback final state.
- Top-level geometry does not include complete z-order, crop/mask state, nested group structure, font runs, or action paths.
- A 2020 event deck is one corpus, not a universal model of every Apple presentation format.

## Claim Language

Use precise wording:

- "Keynote reports Magic Move at 0.8 seconds" for native-observed settings.
- "The exported playback shows the label arriving after the layout settles" for visual-observed behavior.
- "The image is likely the continuity anchor" for inferred matching.
- "Use 0.8 seconds here" for a recommendation.

Do not say "Apple always does this" from one deck or one sequence.
