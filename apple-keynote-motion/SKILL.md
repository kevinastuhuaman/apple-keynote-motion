---
name: apple-keynote-motion
description: Create, edit, audit, reverse-engineer, and visually verify Apple-style motion in native Keynote decks. Use for Magic Move choreography, slide transitions, text/image/shape motion, build-in/action/build-out sequencing, object continuity, WWDC or Apple-event references, `.key` analysis, rough-slide transformation, or requests to make a presentation feel like an official Apple keynote.
---

# Apple Keynote Motion

Build motion as a sequence of intentional visual states. Optimize for attention, continuity, pacing, and rendered quality rather than the number of effects.

## Truth Standard

Label implementation-relevant claims as:

- `native-observed`: extracted from Keynote or a validated archive field.
- `visual-observed`: confirmed in an exported build stage or playback.
- `inferred`: reconstructed from geometry, text, filenames, or visual matching.
- `recommended`: chosen for the new deck.

Read `references/evidence-and-confidence.md` before auditing a reference deck. Never present an inference as a native fact. Do not promise a numerical similarity percentage without a defined comparison method and rendered evidence.

## Select The Work Mode

Infer the mode from the request:

1. `plan`: produce choreography without changing a deck.
2. `audit`: inspect an existing deck and report motion, settings, risks, and opportunities.
3. `edit`: improve a user deck on a duplicate and return a verified `.key` file.
4. `create`: build a native Keynote deck or sequence from source content and verify it.
5. `reference-study`: extract reusable patterns from an official or user-supplied deck.

When the user asks to create or improve a deck, do not stop at a plan unless native editing is blocked or the user explicitly asks for guidance only.

## Load References Deliberately

- Read `references/combined-motion-taxonomy.md` for the WWDC20 motion inventory and canonical sequences.
- Search `references/all-transition-pairs-index.md` for exact transition pairs.
- Read `references/build-action-recipes.md` for no-transition build/action scenes.
- Read `references/visual-transition-archetypes.md` for visually verified source/destination patterns from all playable WWDC20 transition pairs.
- Read `references/native-transition-controls.md` for the exact Keynote 15.3 inspector settings of all 120 WWDC20 transition source slides.
- Read `references/keynote-control-surface.md` before setting or claiming detailed Keynote controls.
- Read `references/motion-spec.md` for implementation or handoff work.
- Read `references/visual-qa-loop.md` for any native edit, creation, or serious audit.
- Read `references/apple-keynote-transition-playbook.md` for black-stage visual grammar.
- Read `references/reference-corpus.md` before generalizing from WWDC20 to another Apple presentation family.
- Read `references/apple-developer-api-deck-case-study.md` for developer/API presentations.
- Read `references/transition-number-map.csv` when document and playback numbering can diverge.
- Read `references/native-playback-findings.md` for exact WWDC20 timelines and Spring Loaded 2021 playback-validated compound actions.
- Read `references/dense-object-expansion-benchmark.md` for one-to-system Magic Move scenes with dozens of persistent images or icons.
- Read `references/compound-animation-benchmark.md` for verified typewriter, paragraph cascade, chart, motion-path, simultaneous-action, and full-lifecycle recipes.
- Read `references/keynote-15-3-control-and-capture.md` before automating numeric inspector fields or exporting a large reference pair.
- Read `references/fresh-deck-blind-pilot.md` before claiming that a motion recipe generalizes beyond its reference sequence.
- Read `references/visual-taste-system.md` before designing or materially restyling static slide states.
- Read `references/native-scene-library.md` when selecting a reusable choreography pattern.
- Read `references/scene-library-manifest.md` before copying native examples from the bundled 21-slide Keynote library.
- Read `references/private-asset-library.md` when the user authorizes extraction or reuse of media embedded in supplied decks.
- Read `references/magic-move-export-compatibility.md` when native movie export fails on a Magic Move pair.
- Read `references/motion-fidelity-benchmark.md` before reporting any numeric motion-similarity result.

Do not bundle Apple-owned decks, media, screenshots, or renders. Keep local reference renders outside the skill.

## Use The Full Motion Stack

Model every sequence with four first-class layers:

1. `state transition`: slide cut, Magic Move, Dissolve, Push, or another justified shell.
2. `continuity graph`: objects that persist, enter, exit, or stage off-canvas.
3. `build timeline`: Build In, Action, and Build Out effects with targets, order, start relationships, durations, delays, delivery, and acceleration.
4. `rendered behavior`: what actually appears in build stages and playback frames.

Treat build-only and action-only slides as complete choreography. Do not reduce builds/actions to accents after Magic Move.

## Required Build Loop

For `edit`, `create`, or `reference-study` work:

1. Make a local scratch copy. Never modify the original deck or reference.
2. Record source path, file hash, Keynote version, slide dimensions, and skipped slides.
3. Recover actual document order before making slide-number claims.
4. Extract slide transitions and native motion evidence.
5. Export slide images and, when builds matter, an all-stages PDF.
6. Write or update `motion-spec.json` for the target sequence.
7. Implement native settings and object states.
8. Use Computer Use or System Events for controls not exposed by AppleScript.
9. Export important sequences at 1080p/60 fps when timing, actions, or transient states matter.
10. Analyze every frame and compare the render to the spec or a chosen reference segment.
11. Fix the largest attention error and repeat.

Keep task artifacts in a task-specific working folder. Reopen and round-trip inspect the deliverable before declaring completion.

## Design Motion By Intent

Choose one dominant intent per click:

- `reveal`: introduce a new object or statement.
- `refocus`: move from context to one detail.
- `transform`: show one state becoming another.
- `compare`: preserve a frame while changing one variable.
- `sequence`: advance a process or timeline.
- `expand`: move from one object into a system or grid.
- `collapse`: resolve a system or grid into one hero.
- `reset`: cut or dissolve to a new section.
- `payoff`: land the final state, metric, or decision.

If one click tries to perform several unrelated intents, split it into more slide states.

## Magic Move Discipline

Create Magic Move sequences by duplicating slides so continuity identity is preserved. Build the clean destination state first when that reduces complexity, then duplicate backward into setup states.

For every Magic Move, record:

- continuity objects,
- entry and exit objects,
- intentional off-canvas objects,
- duration and advance behavior,
- Match By Object, Word, or Character,
- Fade Unmatched Objects,
- acceleration.

Use Match By Object for stable text boxes and UI units. Use By Word or By Character only when rearranging language is the visual idea. Confirm all three settings in the Animate sidebar because public AppleScript does not expose them.

If movie export fails, preserve the original controls and follow `references/magic-move-export-compatibility.md`. A zero-geometry risk flag is not proof of failure. Apply any Fade Unmatched workaround only to a labeled scratch capture after an actual failure.

## Build And Action Discipline

Record each build as a timeline event, not an effect name:

- target object,
- Build In, Action, or Build Out,
- effect and parameters,
- order,
- start: After Transition, On Click, With Build, or After Build,
- relative build,
- duration and delay,
- acceleration and direction,
- delivery mode.

Use simultaneous Move, Scale, Rotate, and Opacity actions when one object needs a compound local animation. Prefer duplicated-slide Magic Move when several objects change layout together.

Study `references/build-action-recipes.md` before creating typewriter, icon-cascade, chart-draw, metric, or action-only scenes.

## Text Motion

Preserve text box width, line breaks, paragraph style, and alignment across continuity states unless the reflow is intentional. Distinguish:

- text box movement through Magic Move,
- word or character matching through Magic Move,
- delivery by paragraph, word, or character inside a build,
- static text that should cut with the slide.

Avoid moving long explanatory copy. Use motion to pace short statements, labels, metrics, and structured lists.

## Image, Shape, And Group Motion

Treat crop, mask, z-order, group membership, and opacity as part of the state. A correct x/y/scale diff can still render incorrectly when crop or stacking changes.

Name important objects in Keynote's object list when practical. Preserve identity by duplicating slides, not by recreating visually identical objects. Group only elements that should move as one unit; avoid a group that hides independent timing needs.

## Media Policy

Default to text, images, shapes, and native motion when the user does not need video or audio. Treat movie/audio objects as optional layers, never as a shortcut around learning native choreography.

When the user supplies reference decks and authorizes asset study, build or query a private provenance-preserving library instead of recreating an available high-quality source asset. Keep extracted media outside the skill and outside redistributable packages. A source deck does not prove reuse rights for every embedded asset; use placeholders or user-owned replacements when authorization is unclear.

## Timing Defaults

Use these only as starting recommendations:

- Magic Move `0.4-0.6s`: compact UI state change.
- Magic Move `0.8s`: default spatial continuity.
- Magic Move `1.0-1.25s`: dense grids, major refocus, or large scale change.
- Magic Move `1.5s+`: rare cinematic or intentionally slow sequence.
- Dissolve `0.4-0.8s`: quiet reset or related state without spatial continuity.
- Push about `0.75s`: rare directional chapter movement.
- No slide transition: title, metric, payoff, build-only, or action-only scene.

Choose duration from travel distance, object count, text readability, and narrative weight. Prefer On Click unless timing is deliberately automatic.

Inspect the midpoint of every Dissolve. If outgoing and incoming headlines or most of both layouts are simultaneously legible, use a clean cut or redesign around stable shared elements.

## Native Tool Boundary

Use AppleScript for properties exposed by Keynote:

- slide creation and duplication,
- object creation and geometry,
- text and supported media properties,
- transition effect, duration, delay, and automatic/on-click state,
- slide-image, PDF, and movie export.

Use Computer Use or System Events for unsupported UI controls:

- Magic Move match, fade-unmatched, and acceleration,
- Push direction and other transition-specific controls,
- effect selection and detailed Build In/Action/Build Out parameters,
- Build Order timing relationships and delivery modes,
- crop/mask, object-list naming, and visual-only controls.

Target Keynote by its bundle identifier so the scripts work even when the app's
display name or filename has been customized:

```applescript
application id "com.apple.Keynote"
```

Read `references/keynote-control-surface.md` before automating the UI. Re-fetch accessibility state after every UI action; do not reuse stale element indices.

## Bundled Scripts

- `analyze_keynote_reference.py`: safe archive/media metadata analysis. Do not extract full media unless explicitly requested.
- `recover_slide_order.py`: recover document slide order from `.iwa` internals.
- `analyze_native_motion.py`: classify transition/build/action/media evidence with explicit caveats.
- `dump_slide_transition_settings.applescript`: extract slide-level native settings.
- `dump_keynote_native_state_bulk.applescript`: extract slide/object geometry available through AppleScript.
- `analyze_transition_object_diffs.py`: infer adjacent-state continuity with confidence limits.
- `analyze_text_motion_layers.py`: infer text state changes separately from builds.
- `extract_native_build_timeline.py`: decode exact targets, phases, effects, order, start relationships, durations, delays, delivery, and compound actions for a stage map or selected slides from any recovered slide-order CSV.
- `patch_build_start_relationship.py`: last-resort scratch-copy patcher for one exact BuildChunk start relationship in direct or wrapped archives; never edits in place and still requires reopen, extraction, and playback verification.
- `analyze_playback_video.py`: inspect every frame of a native movie export and produce active intervals, metrics, inferred visual-energy curves, and a contact sheet.
- `compare_playback_motion.py`: compare corresponding rendered intervals with an explicitly scoped temporal-motion-fidelity score.
- `audit_magic_move_export_risks.py`: report paired zero-size drawable paths that can participate in a Keynote 15.3 export assertion; treat findings as warnings, not deterministic failures.
- `export_keynote_visuals.applescript`: export slide images or all build stages from a scratch copy.
- `export_keynote_movie_pair.applescript`: export one slide range from a scratch deck as H.264 1080p60 while skipping other slides only in memory and closing without saving.
- `make_transition_storyboards.py`: create labeled pair storyboards from exported slide images.
- `map_build_stages.py`: align every all-stages PDF page back to its playback slide and build-stage range.
- `make_build_stage_storyboards.py`: render every stage of every multi-stage slide into labeled visual panels.
- `make_storyboard_atlas.py`: tile storyboard panels deterministically for manual or agent review.
- `validate_motion_spec.py`: validate the declarative motion contract.
- `apply_slide_transitions.py`: apply the public slide-transition shell to a new deck copy; finish UI-only settings separately.
- `build_private_asset_library.py`: stream, hash, deduplicate, preview, and index media from user-supplied decks; keep its output private and outside the skill.
- `query_asset_library.py`: search the private SQLite asset catalog by name, deck, type, category, orientation, alpha, and dimensions.

## Bundled Assets

- `assets/apple-motion-native-scene-library-v2.key`: original 21-slide native Keynote library covering Magic Move, builds, actions, build outs, charts, typewriter text, paragraph cascades, dense continuity, and clean resets. Follow `references/scene-library-manifest.md` and always work from a task copy.

Run scripts only against user-approved local copies. Treat script output as evidence with the confidence level documented in `references/evidence-and-confidence.md`.

Run the synthetic regression suite after changing bundled tools:

```bash
python3 -m unittest discover -s tests -v
```

## Plan Output

For planning-only work, provide:

```text
Motion Intent:
Slide States:
Continuity Objects:
Entry Objects:
Exit Objects:
Off-Canvas Staging:
Text Motion:
Image/Shape Motion:
Transition Settings:
Build Timeline:
Implementation Boundary:
Evidence / Confidence:
QA Checks:
```

For implementation, also create `motion-spec.json` and a rendered QA artifact.

## Completion Gate

Before calling work complete, verify:

- one dominant idea per state,
- one clear attention target per click,
- stable continuity identity,
- no accidental fade, pop, crop jump, overlap, or off-canvas artifact,
- correct build order and start relationships,
- committed inspector values verified from the saved native archive,
- readable text during and after motion,
- durations that match travel and narrative weight,
- document/playback numbering clarity,
- native deck and motion spec agreement,
- full-screen playback quality,
- constant-frame-rate 60 fps evidence for transient actions and Build Outs,
- explicit evidence labels for reference claims.
- numeric similarity claims state their metric, comparison segment, weights, and exclusions.

Avoid decorative effects by default: confetti, sparkle, cube, doorway, blinds, mosaic, page turn, and theatrical flips. Use Object Flip only when the content itself requires a front/back reveal.
