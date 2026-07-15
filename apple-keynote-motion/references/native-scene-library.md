# Native Scene Library

These modules are reusable choreography recipes, not mandatory templates. Select one by narrative intent, adapt the static state using `visual-taste-system.md`, and verify the rendered result.

All timelines are `recommended`, derived from the native and visual evidence named in each module.

## Foundation Modules

### 1. Clean Reset

- Intent: reset between complete layouts.
- Objects: no required continuity object.
- Timeline: cut by default; Dissolve `0.4–0.6s` On Click only when the midpoint remains legible.
- Evidence: fresh-deck schoolyard failure and WWDC20 Dissolve controls.
- QA: inspect the midpoint for double-exposed headlines or competing layouts.

### 2. Stable-Shell Chronology

- Intent: sequence events while preserving context.
- Objects: fixed route, timeline, diagram, or screen; three or four labels.
- Timeline: no transition; each label Dissolve In `0.4s`, All at Once, On Click.
- Evidence: fresh-deck transit treatment, preferred `+9.5` in blind review.
- QA: previous labels remain readable but visually subordinate.

### 3. Incremental Benefit Stack

- Intent: reveal three or four principles or capabilities.
- Objects: one stable anchor and independent short statements.
- Timeline: Move In, Bottom to Top, `0.8s`, one On Click per statement.
- Evidence: compound benchmark slide 3 and WWDC20 paragraph stacks.
- QA: statements align to one grid and do not shift the slide.

### 4. Fixed-Shell Callouts

- Intent: refocus on screenshot, map, or device details.
- Objects: stable base plus one callout per click.
- Timeline: no transition; callout Pop In `0.8s`, On Click.
- Evidence: WWDC20 document/playback slide 111.
- QA: crop, z-order, and callout placement do not hide the referenced detail.

### 5. Metric Payoff

- Intent: land a result.
- Objects: short label, dominant number, optional final state.
- Timeline: label Dissolve `0.8s` After Transition plus `0.4s` delay; number Scale In `0.4s` With Build 1; settle `0.6s` After Build 2 when needed.
- Evidence: WWDC20 metric scenes 47, 121, and 122.
- QA: the number, not the animation, is remembered.

## Core Motion Modules

### 6. Hero-To-Detail Refocus

- Intent: move from product context to one feature.
- Objects: persistent product/device plus optional destination label.
- Timeline: duplicate slide; Magic Move `0.8–1.0s`, By Object, Fade Unmatched on, Ease In & Out, On Click.
- Evidence: Spring Loaded AirTag and the validated AirTag rebuild.
- QA: identity, crop, and optical center remain stable.

### 7. Stable UI State Toggle

- Intent: compare one changed UI state.
- Objects: persistent frame/device and one state layer.
- Timeline: Magic Move `0.6–0.8s`; shell fixed; changed layer enters/exits.
- Evidence: WWDC20 stable-frame and semantic-toggle sequences.
- QA: only the intended variable changes.

### 8. Chart Scaffold To Comparison

- Intent: introduce quantitative evidence.
- Objects: native chart, axes, labels, and conclusion.
- Timeline: baseline uses two Wipes, `1.0s` each, Background First, On Click; advanced variant reveals scaffold, groups, then data.
- Evidence: compound benchmark slide 5 and WWDC20 11-event chart scene 427/424.
- QA: chart geometry remains fixed while evidence accumulates.

### 9. Transient Object Lifecycle

- Intent: introduce, emphasize, and remove a token or notification.
- Objects: one transient object over a stable shell.
- Timeline: From Darkness In `0.7s` at `85%`; Pulse `0.6s`, one repeat at `110%`; Dissolve Out `0.6s`; each On Click.
- Evidence: compound benchmark slide 7.
- QA: inspect 60 fps playback because the important state is transient.

### 10. Kinetic Typewriter

- Intent: make entered text or code the story.
- Objects: short text, command, or code line.
- Timeline: Keyboard In `3.0s`, cursor on, On Click; optional Dissolve Out `1.0s`.
- Evidence: compound benchmark slide 2 and WWDC20 document/playback slide 85.
- QA: text is short enough to wait for and playback reveals every intermediate state.

## Advanced Modules

### 11. Compound Object Travel

- Intent: transform one object while moving it to a destination.
- Objects: one focal object and destination context.
- Timeline: Move `1.2s` On Click; Scale to `125%` and Opacity to `50%`, both `1.0s` With Build 1; Ease In & Out.
- Evidence: compound benchmark slide 6.
- QA: verify all three actions begin together and the object does not jump at the endpoint.

### 12. Icon Grid Cascade

- Intent: reveal a family of apps, partners, or capabilities.
- Objects: independent icons on a stable grid.
- Timeline: Fade and Move, Bottom to Top, `0.4s`; all With Build 1; optional `0.1s` row-leader stagger.
- Evidence: WWDC20 document/playback 385/382, 32 exact native events.
- QA: icons preserve consistent size and no event remains unresolved after extraction.

### 13. Hero-To-System Expansion

- Intent: expand one familiar object into an ordered family.
- Objects: persistent hero and every destination sibling.
- Timeline: Magic Move `1.25s`, By Object, Fade Unmatched on, Ease In & Out; future siblings start overlapped at the hero origin with zero opacity.
- Evidence: WWDC20 26→27 and the 67-object hard benchmark.
- QA: use a dense continuity graph and inspect every frame for pops or z-order changes.

### 14. System-To-Hero Collapse

- Intent: resolve a dense system onto one selected object.
- Objects: full system, selected hero, subordinate context.
- Timeline: Magic Move about `0.9s`; enlarge hero while moving or dimming context out of the attention field.
- Evidence: hard-benchmark candidate second pair.
- QA: the hero is unmistakable by the midpoint.

### 15. Compound Attention Swap

- Intent: exchange emphasis between two peers without a slide transition.
- Objects: two cards, products, or feature groups.
- Timeline: beat 1 moves A while B moves, scales, and changes opacity With Build 1 plus `0.2s`; beat 2 exchanges both in `0.5s`; Ease Both.
- Evidence: Spring Loaded document slide 42, ten exact events and measured playback.
- QA: full archive extraction and 60 fps playback are mandatory.

## Build Order

1. Implement modules 1–5 as universal foundation scenes.
2. Add modules 6–10 for normal production decks.
3. Use modules 11–15 only when object identity and detailed native controls can be verified.

Do not promote Object Flip, Push, or media-heavy cinematic scenes into defaults. Their value is contextual and their evidence is narrower.
