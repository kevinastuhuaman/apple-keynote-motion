# Native Timeline And Playback Findings

This reference combines typed Keynote archive fields with every-frame movie analysis. Keep the evidence layers separate:

- `native-observed`: transition controls, build targets, phase, effect, duration, delay, delivery, and action attributes decoded from Keynote records or read in the inspector.
- `visual-observed`: frame count, active intervals, changed regions, and rendered timing measured from a native 60 fps export.
- `inferred`: easing labels estimated from cumulative rendered pixel change.

## WWDC20 Exact Timeline Coverage

The exact extractor resolved every active event in all 118 structural build/action scenes:

- 1,131 events total.
- 808 Build Ins, 185 Actions, and 138 Build Outs.
- 107 After Transition, 818 With Build, 163 After Build, and 43 On Click starts.
- 314 text, 273 image, 258 shape, 208 group, 76 movie, and 2 table targets.
- Durations from 0.05 to 10.0 seconds; median 0.6 seconds.
- No unresolved target, build, or build-chunk references.

These counts are stronger than raw effect-string inventories because each row is tied to a slide, target, order, phase, and timing relationship.

## WWDC20 Every-Frame Samples

Eight representative sequences were exported at 1920x1080 and 60 fps, then measured frame by frame. The local corpus covers:

- compact Build In and Build Out timing,
- kinetic typewriter and transient UI,
- action paths,
- chart or shape motion,
- dense icon choreography,
- Magic Move with a repaired export-only setting.

The analysis output includes `frame-metrics.csv`, `playback-analysis.json`, `playback-analysis.md`, and a labeled keyframe contact sheet. Do not place Apple-owned videos or contact sheets inside the shareable skill.

## Spring Loaded 2021: AirTag

Document slides 31 to 32 use these native transition controls:

- Magic Move.
- 1.0 second.
- Match By Object.
- Fade Unmatched Objects on.
- Ease In & Out.
- On Click.

The 60 fps export measured a 1.017-second transition. The destination then runs a separate native sequence:

1. Start Movie, 0.5 second, On Click.
2. `$29` Build Out with From Darkness, 0.5 second, after the first build with 0.5-second delay.
3. `$99` Build In with From Darkness, 0.5 second, After Build 2.
4. `4 pack` Build In with From Darkness, 0.5 second, With Build 3.

This is a useful proof that a slide-pair movie can contain both a slide transition and destination builds. Treating the clip as one effect would lose the actual construction.

## Spring Loaded 2021: Compound Action Swap

Document slide 42 contains ten linked Action events with no slide transition:

- First beat: one image moves for 1.0 second On Click. A second image starts 0.2 seconds later with simultaneous Move, Scale, and Opacity actions, all 1.0 second.
- Second beat: the two images exchange emphasis through simultaneous Move, Scale, and Opacity actions, all 0.5 second.
- Every action uses native `kEaseBoth` acceleration.

The native durations align with two measured playback intervals: 1.05 seconds and 0.50 seconds. This is the canonical example for combining actions inside one fixed slide.

## General Extraction

Use a stage map for a complete structural audit, or use recovered slide order for selected slides in any deck:

```bash
python scripts/extract_native_build_timeline.py reference.key \
  --slide-order audit/slide-order.csv \
  --slide 31 --slide 32 --slide 42 \
  --output-dir audit/native-timeline \
  --output-prefix selected-build-order
```

Run this tool in the isolated environment containing `keynote-parser`. Do not install reverse-engineering dependencies globally just to inspect one deck.

## Every-Frame Analysis

```bash
python scripts/analyze_playback_video.py sequence.m4v \
  --output-dir audit/playback \
  --label sequence-name
```

The analyzer reads every frame. It does not watch the movie as a continuous human perceptual stream, and its easing classification does not replace the native Keynote acceleration setting.
