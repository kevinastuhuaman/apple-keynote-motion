# Motion Fidelity Benchmark

Use a numeric score only when its scope is explicit. The bundled comparator measures rendered temporal behavior, not overall Apple design similarity.

## Temporal Motion Fidelity

For each matched active interval, the score uses:

- 40% rendered duration ratio.
- 40% normalized cumulative visual-energy curve.
- 10% normalized peak timing.
- 10% inferred easing-label agreement.

The final score is 85% average segment score plus 15% segment-count structure.

It excludes:

- content and imagery,
- typography,
- object identity,
- layout and composition,
- semantic attention quality,
- overall Apple design similarity.

## Native Benchmark Result

A six-slide benchmark was created from scratch with SF Hello, static black backgrounds, duplicated-slide continuity, three Magic Move transitions, one Dissolve, and one Push. Inspector-only controls on the first sequence were round-trip verified as 1.0 second, By Object, Fade Unmatched on, Ease In & Out, and On Click.

The first benchmark version scored 92.859 against the Spring Loaded AirTag transition. Revising the attention hierarchy from three equal labels to title, price, and centered product increased the score to 94.576 without changing the native duration or easing. Peak-timing score increased from 81.421 to 94.754.

This result proves that choreography changes alter rendered temporal behavior even when the transition settings remain identical.

## Dense Expansion Result

WWDC20 document slides 26 to 27 were later exported natively at 1920 by 1080 and constant 60 fps. Frame analysis measured the full Magic Move from 5.000 to 6.250 seconds, exactly matching the 1.25-second native duration, with an ease-in-out visual-energy proxy.

The Advanced Commerce dense expansion v3 scored **96.102/100** against that aligned reference interval:

- reference rendered duration: 1.250 seconds,
- candidate rendered duration: 1.167 seconds,
- duration score: 93.333,
- visual-energy curve score: 96.582,
- peak-timing score: 94.476,
- easing-label score: 100.000,
- segment score: 95.414,
- one-to-one segment structure: 100.000.

The 96.102 final score is 85% segment score plus 15% structure score. It is a temporal-motion result, not a visual-design score.

## Comparison Command

```bash
python scripts/compare_playback_motion.py \
  reference/playback-analysis.json \
  candidate/playback-analysis.json \
  --reference-segment 1 \
  --candidate-segment 1 \
  --output-dir audit/motion-fidelity
```

## Interpreting A High Score

- A high score means the selected intervals have similar timing and visual-energy progression.
- It does not prove that the candidate has Apple-quality composition or storytelling.
- A 99+ claim requires matched comparison scope, stable frame extraction, native-control verification, visual endpoint review, and repeated renders.
- For a new deck with different content, use the score as one QA signal alongside composition, continuity, hierarchy, crop, typography, and narrative review.
