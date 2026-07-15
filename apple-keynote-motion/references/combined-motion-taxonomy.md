# Apple Keynote Combined Motion Taxonomy

Reference deck: a local WWDC20 scratch copy supplied by the user. The Apple-owned deck and rendered artifacts are not bundled with this skill.

Primary goal: convert the WWDC20 Keynote deck into a reusable mental model for building Apple-style motion in future decks. This document treats "transition" as the full motion stack, not only the slide transition dropdown.

## Coverage

- Slides analyzed in actual presentation order: 472
- Slide-level transitions: 120
- Magic Move transitions: 106
- Non-Magic slide transitions: 14
- Transition-relevant adjacent slide states dumped through native Keynote AppleScript: 194 slides
- Object records in those transition-relevant states: 2,804
- Transition pairs with object diffs: 120
- Text-specific transition pairs analyzed: 120

Authoritative raw artifacts:

- `keynote-slide-transition-settings.tsv`: Keynote UI transition setting, duration, delay, automatic/on-click, skipped flag.
- `native-motion-summary.json`: decoded native transition/build/action/media inventory.
- `transition-object-diffs.csv`: object movement/scale/appear/disappear analysis across every transition pair.
- `magic-move-complexity-ranked.csv`: all 106 Magic Move transitions ranked by motion complexity.
- `text-motion-by-transition.csv`: text-only motion across every transition pair.
- `slide-number-map.csv`: maps document slide numbers to playback numbers excluding skipped slides.
- `transition-number-map.csv`: maps each transition pair between document numbering and playback numbering.

Numbering convention: analysis artifacts use document slide numbers by default, including skipped slides. Playback/visible slide numbers exclude skipped slides. In this deck, slides 159 and 216 are skipped before the Object Flip, so the same transition is document pair `290->291` and playback pair `288->289`. AppleScript confirms the Object Flip is stored on document slide 290, and Keynote's scripting dictionary defines that property as the effect between the current and following slides.

## The Real Model

An Apple-style Keynote sequence is usually a stack of independent motion layers:

1. Slide-level transition shell.
2. Magic Move continuity across adjacent slides.
3. Object geometry changes: position, scale, size, rotation, opacity.
4. Object membership changes: appears, disappears, unmatched objects, off-canvas staging.
5. On-slide builds and actions.
6. Media triggers and movie/audio objects.

The skill should reason in these layers. A deck can have a simple dropdown transition but complex object motion, or it can have no slide transition while still containing heavy text, action, or media animation.

## Slide-Level Transition Shell

Actual Keynote transition dropdown counts:

| Transition | Count | Use in this deck |
| --- | ---: | --- |
| No transition effect | 352 | Static cuts, build-only slides, media-only slides, or invisible timing slides. |
| Magic Move | 106 | Main professional motion mechanism. Used for text, images, icons, groups, devices, cards, charts, and movie objects. |
| Dissolve | 8 | Soft handoffs, often between similar scenes or into media. |
| Push | 5 | Directional section movement. Rare in this deck. |
| Object Flip | 1 | The only UI-facing flip transition in the deck. Native ID is `apple:ca-dissolve-and-flip`. |

Key implication: the deck does not use many exotic slide transitions. The professional look comes from Magic Move plus precise object staging, builds, and timing.

## Transition Timing

Magic Move duration distribution:

| Duration | Count | Interpretation |
| --- | ---: | --- |
| 0.3s | 1 | Snap-fast UI state change. |
| 0.4s | 4 | Fast object state change. |
| 0.5s | 8 | Fast logo/icon/card repositioning. |
| 0.6s | 18 | Common quick UI transition. |
| 0.7s | 1 | Slightly slower quick transition. |
| 0.8s | 41 | Default-feeling Apple motion pace. Most common Magic Move duration. |
| 1.0s | 15 | Larger hero motion or visual breathing room. |
| 1.25s | 11 | Dense or dramatic layout morphs. |
| 1.5s | 3 | More cinematic state change. |
| 2.0s, 3.0s, 3.5s, 12.0s | 4 total | Long-running showcase or media-timed scenes. |

Other transition timing:

- Dissolve: 0.4s (1), 0.6s (2), 1.0s (3), 1.25s (2).
- Push: 0.75s (4) and 1.0s (1).
- Object Flip: 0.8s.

Automatic transitions:

- 25 of the 120 actual transition slides are automatic.
- Automatic Magic Move appears in sequences where timing is likely coordinated with media, narration, or multi-step visual reveals.
- Skipped slides in this deck: 159, 216, 330, 437.

Direct Keynote 15.3 Animate-sidebar inspection adds:

- all 106 Magic Move transitions use Fade Unmatched Objects,
- Match is By Object on 102, By Character on 3, and By Word on 1,
- acceleration is Ease In & Out on 101, Ease Out on 4, and Ease In on 1,
- four Push transitions are Right to Left and one is Bottom to Top,
- the Object Flip is stored on document slide 290, which is playback slide 288.

See `native-transition-controls.md` for exact rows and automatic-delay outliers. The visible `0.50s` delay on On Click transitions is a latent inspector value, not an automatic wait after the click.

Skill rule: default to 0.8s for Apple-style Magic Move. Use 0.4s to 0.6s for quick UI state changes, 1.0s to 1.25s for dense icon/text grids or hero moves, and longer durations only when the slide is acting like a mini video scene.

## Magic Move Continuity Layer

Magic Move is the deck's main engine. In creator terms, it works by duplicating a slide, preserving objects that should interpolate, then changing their geometry or membership on the next slide.

Important creator behaviors:

- Same object remains across adjacent slides: it moves, scales, resizes, rotates, or changes opacity.
- Object exists only on the destination slide: it appears during the transition.
- Object exists only on the source slide: it disappears during the transition.
- Object starts or ends off-canvas: creates a slide-in, fly-out, or carousel feel while still using Magic Move.
- A group can act as one moving unit, while inner text/images keep visual consistency.
- A movie object can be treated as a Magic Move object. Its frame can move/scale while the media trigger controls playback.

Analytical caveat: the object diff files reconstruct visual continuity from Keynote object dumps, text strings, media filenames, and geometry. They are not Apple's private Magic Move identity table. They are still the right practical abstraction for building similar decks.

## Object Types

Object types found in transition-relevant slide states. The earlier `3,193` figure counted TSV header, slide, and blank rows as if they were objects; `2,804` is the corrected object-record total:

| Object type | Count | Skill implication |
| --- | ---: | --- |
| Images/icons | 1,088 | Core layer for product UI, app icons, logos, frames, screenshots. |
| Text items | 858 | Major participant in Magic Move, not just build effects. |
| Shapes | 506 | UI chips, backgrounds, masks, cards, glyph containers, chart blocks. |
| Groups | 315 | Primary way to move complex UI/device/card units together. |
| Movie objects | 35 | Treated as visual objects plus media playback triggers. |
| Tables | 2 | Rare. Do not optimize the skill around tables. |

Skill rule: support text, images, shapes, groups, and movies as first-class motion targets. A future generator should not treat text and images separately from the transition; they are part of the same Magic Move state graph.

## Object Motion Patterns

Across the 106 Magic Move transitions, these pattern labels appear:

| Pattern | Count | Meaning |
| --- | ---: | --- |
| Scale morph | 56 | Object size changes between states. |
| Hero move | 53 | One or a few dominant objects travel between layouts. |
| Off-canvas staging | 53 | Objects begin/end outside the slide to fake scrolling, carousels, or reveals. |
| Large spatial rearrangement | 39 | Many objects move meaningfully across the slide. |
| Multi-object scale morph | 33 | Multiple objects scale together, often icons/cards/grids. |
| Transition plus native builds | 25 | Magic Move combined with build effects. |
| Many unmatched fade-in/out objects | 24 | Objects appear/disappear while continuity objects move. |
| Transition plus action effects | 8 | Magic Move combined with action builds, motion paths, rotation, or pop. |
| Text-heavy choreography | 6 | Text itself is a main moving/scaling subject. |
| Dense image/icon grid | 5 | Large icon/logo app-grid choreography. |

This is the heart of the future skill: classify a desired transition by pattern, not by a single Keynote effect name.

## Text Layer

Text is animated in two different ways:

1. Text as Magic Move object geometry.
2. Text as build/action effects inside a slide.

Text transition facts:

- Transition pairs analyzed: 120
- Transition pairs with text object changes across the slide boundary: 42
- Transition pairs with native character/text build effects: 9
- Most complex text Magic Move: slide 26 -> 27, with 96 text items moving and scaling.

Native text/character build effects on transition slides:

| Effect | Count |
| --- | ---: |
| `apple:dissolve character` | 6 |
| `apple:fade and move character` | 2 |
| `apple:move in character` | 1 |
| `apple:zoom character` | 1 |

Skill rule: when text is part of the layout itself, prefer Magic Move. Use character builds for the content reveal layer: labels, bullets, stat phrases, privacy labels, or typewriter-like moments.

## Image, Icon, And Logo Layer

Images/icons are the densest object type in transition scenes. The hardest examples are not single images. They are grids, repeated app icons, logos, screenshots, and device frames moving at once.

Core image/icon patterns:

- Dense app grid morph: many icons and labels move/scale together.
- Logo constellation: logos reposition into a neat grid or fan out from a cluster.
- Device UI move: screenshot or phone frame becomes a hero element, then exits or shrinks.
- Off-canvas carousel: icons start thousands of pixels outside the slide and settle into frame.
- Replace-with-fade: unmatched icons disappear while a few continuity objects carry the eye.

Skill rule: for professional Apple motion, build image/icon scenes as state diagrams. Decide which objects are continuity anchors, which are entrance-only, which are exit-only, and which are off-canvas staging objects.

## Video And Media Layer

Media exists in two forms:

1. Movie objects visible on slides.
2. Native media triggers.

Media-trigger presence by slide in decoded slide records:

| Trigger | Count |
| --- | ---: |
| `apple:movie-start` | 108 |
| `apple:audio-start` | 64 |

Movie objects found in transition-relevant slide states: 35.

Important interpretation:

- `movie-start` and `audio-start` are not slide transitions.
- A slide can be `MEDIA_ONLY`, `MM_PLUS_MEDIA`, or `TRANSITION_DISSOLVE_PLUS_MEDIA`.
- Media can coexist with Magic Move. Example: slide 70 -> 71 moves/scales a movie object and related images during a Magic Move.

Skill rule: treat video as a visual object in the geometry layer plus a trigger in the timing layer. Even if future decks mostly use images/text, the skill should preserve the model so movie objects can be moved, scaled, and timed like any other object.

## Build And Action Layer

Build-effect presence by slide in the schema-less native-motion scan. These values count slides containing an effect identifier, not verified build instances:

| Build effect | Count |
| --- | ---: |
| `apple:dissolve character` | 51 |
| `apple:zoom character` | 31 |
| `apple:appear` | 27 |
| `apple:zoom` | 26 |
| `apple:dissolve` | 20 |
| `apple:move in` | 17 |
| `apple:move in character` | 14 |
| `apple:fade and move character` | 11 |
| `apple:pop` | 7 |
| `apple:fade and move` | 1 |

Action-effect presence by slide in the corrected classifier. Earlier versions incorrectly placed `action-scale` and `action-opacity` in the build table:

| Action effect | Count |
| --- | ---: |
| `apple:action-scale` | 43 |
| `apple:action-motion-path` | 37 |
| `apple:action-opacity` | 21 |
| `apple:bc-appear` | 15 |
| `apple:bc-zoom-big character` | 12 |
| `apple:bc-zoom-big` | 9 |
| `apple:action-rotation` | 4 |
| `apple:wipe` | 2 |
| Singletons | `bc-expand`, `bc-3D-cube`, `action-blink`, `bc-typewriter`, `keyboard`, `revolve`, `action-jiggle`, `wipe-iris` |

Skill rule: choose the engine that fits the scene. Use Magic Move for multi-object layout continuity; use builds/actions as the primary choreography for fixed-stage text, metrics, callouts, chart draws, icon cascades, typewriter moments, and local motion paths.

## Combined Motion Classes

Decoded slide motion classes after separating `action-*` and `bc-*` identifiers from build identifiers:

| Class | Count | Meaning |
| --- | ---: | --- |
| `STATIC` | 145 | No transition, no build/action/media. |
| `MEDIA_ONLY` | 77 | Timing/media slides with no slide transition. |
| `MM_PURE` | 64 | Magic Move only. |
| `BUILD_ONLY` | 45 | On-slide build identifiers without slide transition. |
| `BUILD_ONLY_PLUS_ACTION_MEDIA` | 38 | Builds plus actions and media, no slide transition. |
| `BUILD_ONLY_PLUS_ACTION` | 25 | Builds plus actions, no slide transition. |
| `MM_PLUS_MEDIA` | 15 | Magic Move plus movie/audio trigger. |
| `MM_PLUS_BUILD` | 11 | Magic Move plus builds. |
| `ACTION_ONLY_PLUS_MEDIA` | 10 | Actions plus media, no slide transition. |
| `ACTION_ONLY` | 8 | Action identifiers without transition/build. |
| `MM_PLUS_BUILD_ACTION` | 7 | Magic Move plus builds plus actions. |
| `BUILD_ONLY_PLUS_MEDIA` | 4 | Builds plus media, no slide transition. |
| `TRANSITION_DISSOLVE` | 7 | Pure dissolve transition. |
| `MM_PLUS_BUILD_MEDIA` | 5 | Magic Move plus builds plus media. |
| `TRANSITION_PUSH` | 5 | Push transition. |
| `MM_PLUS_BUILD_ACTION_MEDIA` | 2 | Full stack: Magic Move, builds, actions, media. |
| `MM_PLUS_ACTION` | 1 | Magic Move plus action. |
| `MM_PLUS_ACTION_MEDIA` | 1 | Magic Move plus action plus media. |
| `TRANSITION_CA_DISSOLVE_AND_FLIP` | 1 | Object Flip. |
| `TRANSITION_DISSOLVE_PLUS_MEDIA` | 1 | Dissolve plus movie/audio trigger. |

Most deck motion is not a named transition. It is a composition strategy. These classes remain effect-presence heuristics; they do not recover target objects, true instance counts, build order, duration, delivery, or easing.

## Canonical Study Sequences

These are the slide pairs or clusters the future skill should learn from first:

| Slides | Why it matters |
| --- | --- |
| 26 -> 27 | Hardest dense app icon grid. 372 -> 276 objects, 260 matched, 259 moved, 260 scaled, 96 text items moved and scaled. |
| 439 -> 440 | Icon grid with extreme off-canvas staging. Many icons travel 4,900 to 5,600 px. |
| 440 -> 441 | Dense icon grid collapse with many disappearances plus character dissolve. |
| 293 -> 294 | App Privacy label. Magic Move plus `zoom character` and `fade and move character`. Text/card choreography. |
| 313 -> 314 | Home dashboard state change. Text, shapes, icons, and tile layouts all move/scale. |
| 316 -> 318 | Home dashboard continuation. Text-heavy state changes plus dissolve-character/appear action layer. |
| 82 -> 85 | Messages inline replies sequence. Text, bubbles, avatars, and UI panels move/scale/reveal. |
| 87 -> 90 | Messages group UI with hero device movement, off-canvas staging, pop/appear/revolve accents. |
| 176 -> 180 | FaceTime/contact card sequence. Magic Move plus audio/media timing, repeated UI card movement. |
| 203 -> 204 | Group-heavy scene. Off-canvas staging, many disappeared objects, builds. |
| 305 -> 306 | Logo/grid choreography with moderate duration, strong example for brand-grid motion. |
| 383 -> 384 | App icon off-canvas motion into a grid. Clean image/icon movement reference. |
| 446 -> 448 | Full-stack pro-app/Rosetta sequence. Magic Move plus builds, action motion path, action scale/opacity, audio, and dissolve-character. |
| 70 -> 71 | Movie object moved/scaled during Magic Move. Good video-as-object reference. |

## Design Recipes For The Skill

### Recipe 1: Pure Magic Move Hero

Use when one object or group carries the transition.

- Duplicate the slide.
- Keep the hero object/group continuous.
- Change x/y/scale/size on the next slide.
- Duration: 0.8s to 1.0s.
- Use no extra build unless the text needs a reveal accent.

### Recipe 2: Dense Icon Grid Morph

Use for app icons, logos, features, partner logos, or product tiles.

- Create a grid of icons/images plus labels.
- Duplicate slide.
- Preserve anchors that should interpolate.
- Move and scale many objects together.
- Let irrelevant objects disappear and destination-only objects appear.
- Duration: 1.0s to 1.25s for readability.
- Study 26 -> 27 and 439 -> 440.

### Recipe 3: UI State Change

Use for screenshots, app panels, cards, messages, dashboards.

- Group related UI units.
- Duplicate slide.
- Move groups, resize containers, and reveal/hide child details.
- Keep text labels as Magic Move objects if they should track with the UI.
- Add `appear`, `dissolve character`, or `pop` only for secondary details.
- Duration: 0.6s to 0.8s for small UI changes, 1.0s to 1.25s for major state changes.

### Recipe 4: Text As Layout

Use when text is part of the object choreography, not just copy appearing.

- Keep text items duplicated across slides.
- Move/scale text using Magic Move.
- Avoid character builds for the moving text itself unless the text is also revealing new content.
- Use character dissolve/zoom/fade-and-move for labels or stat copy after the layout arrives.
- Study 293 -> 294, 313 -> 314, and 26 -> 27.

### Recipe 5: Media As Object

Use when video should feel integrated into slide motion.

- Treat the movie as an image-like object for Magic Move geometry.
- Move/scale the movie frame across slides.
- Separately set the movie start timing.
- Keep duration coordinated with automatic transition only when needed.
- Study 70 -> 71 and the media-heavy Magic Move classes.

### Recipe 6: Full-Stack Choreography

Use for keynote-level moments where several motion systems combine.

- Magic Move handles the scene state change.
- Builds reveal details after or during the state change.
- Actions handle local accents: motion path, rotation, scale, opacity, pop.
- Media trigger starts movie/audio when the visual object reaches the right state.
- Use sparingly. The deck has only 2 `MM_PLUS_BUILD_ACTION_MEDIA` slides.
- Study 446 -> 447.

## Skill Architecture Implication

The future Codex skill should not ask "what transition do you want?" first. It should ask or infer:

1. What objects should maintain continuity across slides?
2. Which objects should enter, exit, or start off-canvas?
3. Is text part of the geometry motion, the reveal motion, or both?
4. Are images/icons/logos moving as a grid, hero object, carousel, or device UI?
5. Is there media playback, and is the movie itself moving/scaling?
6. Which timing bucket applies: fast UI, default Apple, dramatic morph, or media-timed scene?
7. Which accent builds are needed after the layout transition?

Recommended output structure for the skill:

- `motion_intent`: hero, grid, UI state, text reveal, media scene, full-stack.
- `slide_transition`: Magic Move, Dissolve, Push, Object Flip, or none.
- `duration`: numeric seconds with rationale.
- `advance`: click or automatic with delay.
- `continuity_objects`: objects duplicated across slides.
- `entry_objects`: destination-only objects.
- `exit_objects`: source-only objects.
- `off_canvas_objects`: staging objects and direction.
- `builds`: text/image/shape build effects and order.
- `actions`: motion path, scale, opacity, rotation, pop, typewriter, keyboard, wipe, etc.
- `media`: movie/audio triggers and whether the media object participates in Magic Move.

## Bottom Line

For Apple-style decks, Magic Move is the main slide transition, but the professional effect comes from combining it with object continuity, off-canvas staging, text/image participation, build accents, action effects, and media timing. The future skill should generate a choreography plan, not a single effect name.
