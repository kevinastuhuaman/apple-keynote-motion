# Build And Action Recipes From WWDC20

The WWDC20 deck contains 78 media-independent no-transition scenes with native motion strings under the original classifier. A later Keynote all-stages export produced 770 PDF pages for 468 playable slides. Monotonic visual alignment found 239 multi-stage slides, including:

- 60 with native build evidence,
- 45 with build plus action evidence,
- 13 with action evidence,
- 91 media-only stage changes,
- 30 unattributed stage changes.

The first three groups provide 118 structural multi-stage scenes across the whole deck. Media-only stages are intentionally excluded from the recipes below.

For production-tested synthetic implementations of Keyboard, paragraph cascades, chart Wipe, simultaneous Move + Scale + Opacity, motion paths, and a Build In/Action/Build Out lifecycle, also read `compound-animation-benchmark.md`.

An all-stages PDF proves discrete exported states and their order. It does not expose animation frames, duration, easing, delivery, or every action. A one-page slide may still contain native actions or automatic animation that PDF export does not separate. Effect counts remain raw archive-string occurrences unless stated otherwise.

## Provenance Gate

Classify a rendered sequence before deriving a recipe:

- `structural`: native build or action evidence supports the visible states.
- `media-only`: repeated or changed pages are movie/audio trigger states, not native object choreography.
- `unattributed`: the range changes visually but native evidence does not assign the change to that slide.

Create native recipes only from `structural` sequences. A high-confidence final-page match does not validate every preceding page. In this corpus, playback 159 visibly includes content from skipped document slide 159, and several `STATIC` or `MM_PURE` ranges appear to contain incoming-transition spillover.

## Character Ladder

Representative: document/playback `14/14`.

`D14/P14` exports two states: blank, then the complete five-item operating-system ladder. Native evidence contains `move in character` for all five labels. Treat this as one click-stage containing a timed character cascade, not five separate clicks, unless the Keynote Build Order UI proves otherwise.

## Metric Reveal Trio

Representatives: `46/46`, `47/47`, `121/121`, `122/122`, `277/275`, `279/277`.

`D47/P47`, `D121/P121`, `D122/P122`, `D277/P275`, and `D279/P277` export two states: blank, then the metric plus its short label. Native evidence combines scale, zoom-character, and dissolve-character strings. `D46/P46` exports only one PDF state despite equivalent native evidence, proving that all-stages PDF is not a complete action-frame recorder. Treat the number as the dominant beat and keep the unit and label secondary.

## Long-Form Text Rhythm

Representatives: `54/54`, `169/168`, `380/377`.

`D54/P54` exports blank, then a two-line bilingual statement. `D380/P377` exports blank, then a dense field of feature labels. Use character or paragraph delivery only when text itself is the visual system. Keep copy sparse enough that the audience can read the final state; the build should pace meaning, not decorate prose.

## Screenshot With Callouts

Representatives: `73/73`, `92/92`, `111/111`.

`D73/P73` exports three states: the full phone, a closer crop, then a new message bubble. `D111/P111` holds the map still while one magnified callout and then a second callout appear. Keep the underlying screenshot stable and add one dominant highlight per click.

## Kinetic Typewriter

Representative: `85/85`.

The native archive combines typewriter/keyboard, blink, motion paths, scale, appearance, dissolve, and zoom. The PDF exposes only two click-states: the full phone and the isolated completed text field. The typing itself occurs within a state and requires playback or UI inspection. Use this only when typing is the product story.

## Image Grid Cascade

Representative: `385/382`.

`D385/P382` contains 32 images and 32 raw fade-and-move occurrences, but exports only blank and the complete grid. This supports a synchronized or timed cascade within one click-stage, not 32 click-stages. Stage icons from a meaningful direction, use consistent delay, and preserve a clean final grid.

## Image Grid Burst

Representative: skipped document slide `437`; another dense candidate is `217/215`.

`D217/P215` exports three states: full icon grid, App Store hero, then full grid again. Native evidence contains Pop, scale, paths, and character dissolve. Use this grid-to-hero-to-grid pulse only when selecting one identity from a system is the story. Do not apply Pop to every grid by default.

## Shape Or Chart Draw

Representative: `427/424`.

`D427/P424` exports five states in this order: axis labels, axes, first category, second category, then the complete grid, title, and plotted field. Native evidence contains wipe plus text dissolves. Reveal structure before categories and categories before the final data field.

## Action-Only Fixed Stage

Representatives: `303/301`, `312/310`, `340/337`, `387/384`, `466/462`.

`D303/P301` exports a HomeKit icon followed by a device lineup. Other action-only examples export one PDF page even though native paths or substitutions exist. Use motion paths, expansion, or object substitution while the slide remains fixed, but inspect playback because all-stages PDF often omits intermediate action frames.

## Native Kinetic Montage

Representative: `28/28`.

This is the densest native-motion candidate in the corpus, with hundreds of raw scale, path, character-dissolve, opacity, zoom, and iris-wipe strings. It exports only one PDF state. Do not derive a recipe from raw counts or all-stages PDF alone; capture playback frames.

## Timeline Stack

Representative: `471/467`.

Native evidence includes zoom-character, appear, and `bc-appear`, but the all-stages PDF exports only one state. Use sequential text states for milestones or availability, keep the timeline spatially stable, and validate the sequence in playback.

## Incremental Benefit Stack

Representatives: `D65/P65`, `D274/P272`, `D449/P445`.

These export four or five click-states: blank, then one concise line at a time. Existing lines remain fixed while the next line appears. This is the correct pattern for three to four benefits, principles, or product capabilities. Keep one text box or paragraph unit per line and avoid moving the whole stack as it grows.

## Platform Feature Inventory

Representatives: `D158/P157`, `D405/P402`.

Start blank, establish the platform name, then add feature tiles around the anchor. `P157` uses five stages; `P402` uses eight. Add one feature cluster per click and preserve a stable anchor so the audience never has to reparse the whole system.

## Semantic State Toggle

Representatives: `P314`, `P315`, `P320`.

Keep the complete layout fixed and change one meaningful variable: locked/unlocked, on/off, or dark/illuminated. This is a comparison beat, not a new composition. Preserve position and scale so the audience reads the state change immediately.

## Concept To Proof

Representatives: `P281`, `P286`, `P288`, `P301`.

Begin with a compact concept token, then resolve it into the concrete interface, product, or system that proves the idea. The visual pattern can be implemented by media, builds, actions, Magic Move, or the rare justified Object Flip; the visual resemblance alone does not identify the native engine.

## Fixed Shell With Overlay

Representatives: `P291`, `P326`, `P328`, `P388`, `P395`.

Keep the device, card, or interface shell stable while one row, callout, notification, popover, or dialog appears. For a transient callout, return to the unchanged anchor before leaving the scene. This preserves orientation and makes the overlay the only attention target.

## Matrix Spotlight Tour

Representatives: `P426-P430`.

Keep the full capability map in place, dim its context, and brighten one region per beat. Use separate slide states when the emphasis travels across a large matrix; use builds when the whole tour belongs to one fixed slide. Never move the matrix itself unless spatial movement is part of the explanation.

## Blackout Hinge

Representatives: `P235`, `P286`, `P415`, `P422`.

Use a deliberate black state between ideas that share no honest continuity anchor. The blackout is a narrative reset, not a missing render. Confirm it in playback because media-only and export-failure pages can also appear black.

## Claim To Scaffold To Evidence

Representatives: `P385-P386`, `P424`.

Land the claim, reveal the chart scaffold, add comparison groups, and finish with the quantified result. Axes and labels should arrive before the final data field. This keeps the audience's parsing order aligned with the argument.

## Export Limitation

All-stages PDF captures discrete build states, not full animation playback. Use it to establish reveal order and state composition. Use Keynote preview or movie export to verify action paths, timed cascades, typewriter behavior, easing, acceleration, and simultaneous effects.

## Compound Action Swap

Representative: Spring Loaded 2021 document slide `42`.

This fixed-slide sequence uses ten linked Action events across two beats. The first image moves for 1.0 second On Click. A second image starts 0.2 seconds later with simultaneous Move, Scale, and Opacity actions for 1.0 second. The next beat exchanges emphasis through simultaneous Move, Scale, and Opacity actions for 0.5 second. All actions use `kEaseBoth`.

The native durations align with two measured playback intervals, 1.05 seconds and 0.50 seconds. Use this pattern when one visual state must hand attention to another without changing the slide shell. Keep each compound target on one start relationship; do not split Move, Scale, and Opacity across separate clicks.
