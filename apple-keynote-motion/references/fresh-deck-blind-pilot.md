# Fresh-Deck Blind Pilot

Use this pilot as the generalization check for motion choices on decks that were not part of the Apple reference corpus.

## Method

Three unrelated three-slide briefs were created: museum conservation, transit incident response, and schoolyard cooling. Each imported native deck was duplicated into a control and treatment before animation work.

All six variants were exported with identical settings and validated as H.264, 1080-pixel height, constant 60 fps. Treatment archives were reopened and decoded before export. The final native treatment timelines contained:

- museum: one 0.5-second image Build In and two 0.6-second Dissolve transitions,
- transit: four text Dissolve Build Ins at 0.4 seconds and two 0.6-second Dissolve transitions,
- schoolyard: three text Dissolve Build Ins at 0.4 seconds and two 0.6-second Dissolve transitions,
- zero unresolved native build or chunk references.

A deterministic script randomized A/B labels and wrote a sealed mapping. Three separate agent reviewers received only one anonymous pair and the same weighted rubric: composition 15%, continuity 20%, timing 15%, readability 15%, narrative focus 20%, and artifacts 15%. The mapping was opened only after all reports were saved.

## Results

| Brief | Control | Treatment | Difference | Winner |
| --- | ---: | ---: | ---: | --- |
| Museum | 81.5 | 88.5 | +7.0 | Treatment |
| Transit | 82.5 | 92.0 | +9.5 | Treatment |
| Schoolyard | 84.0 | 77.0 | -7.0 | Control |
| Mean | 82.7 | 85.8 | +3.2 | Treatment, 2 of 3 |

These are blinded agent-review scores, not human audience research or a universal quality metric.

## What Generalized

- Motion earned its time when it exposed object continuity or a meaningful sequence.
- The museum treatment made the fragments-to-form relationship easier to follow.
- The transit treatment turned four simultaneous labels into a readable chronology.
- Stable shells and cumulative reveals improve narrative focus because the audience reparses less.

## What Failed

The schoolyard treatment lost because the full-layout dissolves briefly showed outgoing and incoming headlines, labels, numbers, cards, and chart elements at the same time. The settled states were strong; the boundary frames were not.

Durable rule:

- Use Dissolve for quiet resets when the two states do not create illegible double exposure.
- Use a clean cut when the headline and most of the layout change together.
- Do not reward a treatment for motion existing. Inspect the midpoint frames.
- If a treatment loses a blind comparison, preserve the control behavior or revise the transition.

## Validation Boundary

Three small synthetic briefs are evidence of initial generalization, not proof across every domain or deck length. Repeat the same sealed control/treatment protocol on real user decks as the skill evolves.
