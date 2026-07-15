# Reference Corpus Strategy

## Current Corpus

The local read-only corpus contains nine official Apple event or WWDC decks. Archive-derived counts are motion signals, not verified build instances:

| Deck | Slides | Magic Move | Dissolve | Push | Build slides | Action slides | Motion density |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WWDC20 | 465 | 105 | 8 | 5 | 134 | 90 | 53.1% |
| Spring Loaded 2021 | 235 | 39 | 0 | 1 | 52 | 29 | 38.7% |
| WWDC16 | 413 | 65 | 8 | 14 | 52 | 36 | 34.1% |
| WWDC17 | 535 | 64 | 7 | 12 | 54 | 47 | 29.7% |
| iPhone X 2017 | 368 | 27 | 19 | 4 | 21 | 21 | 22.8% |
| Mac 2016 | 164 | 19 | 0 | 0 | 20 | 11 | 22.6% |
| Education 2018 | 180 | 20 | 0 | 4 | 9 | 11 | 21.1% |
| iPhone 7 2016 | 298 | 21 | 4 | 2 | 28 | 15 | 20.5% |
| Loop 2016 | 242 | 25 | 0 | 2 | 13 | 18 | 20.2% |

WWDC20 has complete transition-pair analysis, exact timelines for all 118 structural scenes, and eight every-frame playback studies. Spring Loaded 2021 adds newer native inspector and 60 fps evidence for AirTag Magic Move and compound Move, Scale, and Opacity actions.

The skill also includes one user-owned Apple Developer API deck case study. That is useful context, not an official Apple reference.

## What The Corpus Can And Cannot Teach

The corpus is strong evidence for:

- transition frequency and timing in that deck,
- Magic Move as a dominant state-change mechanism,
- dense icon/UI choreography,
- combined build/action/media scenes,
- black-stage event presentation grammar.

It is still not sufficient evidence for:

- every current Apple presentation format or post-2021 design change,
- light-stage or editorial decks,
- current Keynote 15.3 authoring conventions,
- Apple Developer session typography and information density,
- universal margin, type-size, corner-radius, easing, or pacing rules.

## Expand By Presentation Family

Build separate local corpora when the user supplies references:

1. Apple event product launch.
2. WWDC platform keynote.
3. Apple Developer technical/API presentation.
4. Executive or business review.
5. Product demo or UI walkthrough.

Do not average these into one style. Route a new deck to the closest family, then borrow only compatible motion patterns from the others.

## Corpus Intake Protocol

For each reference deck or official playback:

- record source/provenance and copyright restrictions,
- record Keynote version and document dimensions when available,
- hash the source and keep it outside the skill,
- extract slide order, skipped slides, transitions, and native motion evidence,
- export static states and build stages,
- capture representative playback clips,
- classify each claim by evidence level,
- add only written analysis and derived measurements to the shareable skill.

## Calibration Goal

Measure improvement by repeatable outcomes:

- continuity correctness,
- build-order correctness,
- timing error against a chosen reference,
- unexpected-pop count,
- text-bound and overlap errors,
- reviewer preference in blind comparisons.

Do not use an undefined “99% similar” score. Define the target sequence, reference frames, timing tolerances, and review protocol first.
