# Native Transition Controls From WWDC20

## Scope And Method

This reference records every source slide with a non-none transition in the user-supplied WWDC20 deck. Keynote 15.3's Animate sidebar was inspected through macOS Accessibility on a local scratch copy.

Evidence level: `native-observed` for the control values below. There are 120 unique source slides and zero extraction errors:

| Effect | Count |
| --- | ---: |
| Magic Move | 106 |
| Dissolve | 8 |
| Push | 5 |
| Object Flip | 1 |

The transition belongs to the source document slide and runs to the following document slide. Playback numbering excludes skipped document slides 159, 216, 330, and 437.

## Magic Move Controls

### Duration

| Duration | Count |
| --- | ---: |
| 0.3s | 1 |
| 0.4s | 4 |
| 0.5s | 8 |
| 0.6s | 18 |
| 0.7s | 1 |
| 0.8s | 41 |
| 1.0s | 15 |
| 1.25s | 11 |
| 1.5s | 3 |
| 2.0s | 1 |
| 3.0s | 1 |
| 3.5s | 1 |
| 12.0s | 1 |

### Matching And Easing

- Fade Unmatched Objects: on for all 106.
- Match: By Object 102, By Character 3, By Word 1.
- Acceleration: Ease In & Out 101, Ease Out 4, Ease In 1.
- Start: On Click 82, Automatically 24.

The non-object match exceptions are:

| Document / playback | Match | Duration |
| --- | --- | ---: |
| 87 / 87 | By Character | 1.0s |
| 175 / 174 | By Character | 0.8s |
| 176 / 175 | By Character | 0.8s |
| 426 / 423 | By Word | 0.6s |

The non-default acceleration exceptions are:

| Document / playback | Acceleration | Duration | Start / delay |
| --- | --- | ---: | --- |
| 219 / 217 | Ease Out | 0.5s | Automatic / 0.4s |
| 245 / 243 | Ease In | 3.5s | Automatic / 0s |
| 265 / 263 | Ease Out | 12.0s | On Click |
| 304 / 302 | Ease Out | 0.5s | On Click |
| 305 / 303 | Ease Out | 0.5s | On Click |

By Object with Ease In & Out is the measured dominant pattern, not a universal rule. By Word or By Character is rare and should be used only when language rearrangement is the visual idea.

## Automatic Transitions

Twenty-five of the 120 transitions are automatic: 24 Magic Moves and one Dissolve.

| Document / playback | Effect | Duration | Delay |
| --- | --- | ---: | ---: |
| 67 / 67 | Magic Move | 0.8s | 1.65s |
| 72 / 72 | Magic Move | 0.8s | 0s |
| 76 / 76 | Magic Move | 0.8s | 0.8s |
| 78 / 78 | Magic Move | 1.0s | 0s |
| 95 / 95 | Magic Move | 0.6s | 0.2s |
| 144 / 144 | Magic Move | 0.8s | 1.5s |
| 219 / 217 | Magic Move | 0.5s | 0.4s |
| 225 / 223 | Magic Move | 0.8s | 12.0s |
| 230 / 228 | Magic Move | 0.8s | 0.4s |
| 234 / 232 | Magic Move | 0.8s | 0.4s |
| 245 / 243 | Magic Move | 3.5s | 0s |
| 254 / 252 | Magic Move | 3.0s | 0.8s |
| 307 / 305 | Magic Move | 0.4s | 0s |
| 315 / 313 | Magic Move | 0.6s | 0s |
| 317 / 315 | Magic Move | 0.6s | 0s |
| 321 / 319 | Magic Move | 1.25s | 0s |
| 326 / 324 | Magic Move | 1.0s | 1.5s |
| 328 / 326 | Magic Move | 0.8s | 6.5s |
| 346 / 343 | Dissolve | 1.0s | 25.0s |
| 350 / 347 | Magic Move | 0.6s | 0s |
| 364 / 361 | Magic Move | 0.6s | 0s |
| 377 / 374 | Magic Move | 0.5s | 0.1s |
| 416 / 413 | Magic Move | 0.8s | 0.4s |
| 422 / 419 | Magic Move | 2.0s | 0.4s |
| 456 / 452 | Magic Move | 0.4s | 0s |

Automatic delays often coordinate media or a multi-step visual sequence. Do not copy them into a new deck without reconstructing the full click and media timeline. On Click rows display a latent `0.50s` delay value in the inspector; it is not an automatic wait after the click.

## Dissolve Controls

| Duration | Count |
| --- | ---: |
| 0.4s | 1 |
| 0.6s | 2 |
| 1.0s | 3 |
| 1.25s | 2 |

Seven are On Click. Document 346 / playback 343 is automatic after 25.0s and has a movie-start marker, so it is a media-timed exception.

## Push Controls

| Source document / playback | Duration | Direction | Start |
| --- | ---: | --- | --- |
| 221 / 219 | 0.75s | Right to Left | On Click |
| 222 / 220 | 0.75s | Right to Left | On Click |
| 223 / 221 | 0.75s | Right to Left | On Click |
| 224 / 222 | 0.75s | Right to Left | On Click |
| 384 / 381 | 1.0s | Bottom to Top | On Click |

The four horizontal Pushes form one directional sequence. The vertical Push is a separate chapter movement. Direction is part of the meaning and must be specified in a new motion spec.

## Object Flip Control

The single Object Flip is on source document slide 290, which is playback slide 288:

- document pair `290->291`,
- playback pair `288->289`,
- duration `0.8s`,
- On Click,
- no additional direction control exposed in this inspector state.

This corrects the easy numbering mistake caused by the two skipped slides before the pair.

## Implementation Defaults

Use the corpus as calibration, not a template:

- start with Magic Move 0.8s, By Object, Fade Unmatched Objects on, Ease In & Out;
- shorten to 0.4-0.6s for compact UI state changes;
- extend to 1.0-1.25s for dense or large spatial movement;
- use automatic timing only when the complete narration/media timeline requires it;
- specify Push direction explicitly;
- reserve Object Flip for a genuine two-sided metaphor.

All values must still be rendered and reviewed in the target deck.
