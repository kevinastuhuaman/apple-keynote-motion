# Compound Animation Benchmark

Use this benchmark when a scene depends on Build In, Action, and Build Out timelines rather than duplicated-slide Magic Move.

## Verified Native Suite

A seven-slide synthetic deck was created and round-trip verified in Keynote 15.3. The final archive contains 17 native events across six structural slides:

- 8 Build In events.
- 7 Action events.
- 2 Build Out events.
- 2 `With Build 1` relationships.
- 0 unresolved build or chunk references.

The native movie exported as H.264 at 1920 by 1080, constant 60 fps. Every frame was analyzed and the all-stages PDF was mapped back to slide/build state.

## Recipes

### Typewriter With Exit

- Build In: Keyboard, 3.0 seconds, On Click.
- Build Out: Dissolve, 1.0 second, On Click.
- Target: one short code or command text box.

Use this when the act of entering text is the product story. Do not apply it to explanatory prose.

### Four-Step Text Cascade

- Four separate text objects.
- Build In: Move In, Bottom to Top, 0.8 seconds each.
- Delivery: All at Once per object.
- Start: one On Click event per line.

Separate objects make order and timing explicit. Use paragraph delivery only when the lines must remain one semantic text block.

### Sequential Attention Transfer

- Opacity to 50%, 1.0 second, On Click.
- Scale to 150%, 1.0 second, On Click.
- Move on a short path, 1.0 second, On Click.
- Acceleration: Ease In & Out.

This is intentionally sequential. Do not call a scene compound merely because it contains several action types.

### Native Chart Reveal

- Two chart objects.
- Build In: Wipe, 1.0 second.
- Delivery: Background First.
- Start: On Click.

Reveal structure before comparison. If axes, series, and annotations need distinct pacing, use separate chart objects or a verified chart-delivery mode.

### True Move + Scale + Opacity

One image uses three linked Action events:

- Order 1: Move, 1.2 seconds, On Click, Ease In & Out.
- Order 2: Scale to 125%, 1.0 second, With Build 1, Ease In & Out.
- Order 3: Opacity to 50%, 1.0 second, With Build 1, Ease In & Out.

This is the canonical local compound action. The move is the reference build; scale and opacity share its click through `With Build 1`.

Use simultaneous actions when one object must travel and change emphasis. Use Magic Move when several objects change layout together.

### Full Object Lifecycle

One image completes all three phases:

- Build In: From Darkness, 0.7 seconds, 85% starting scale.
- Action: Pulse, 0.6 seconds, one repeat, 110% scale.
- Build Out: Dissolve, 0.6 seconds.
- Start: On Click for each phase.

This pattern is useful for a temporary proof point, notification, status token, or callout that must enter, receive emphasis, and leave without changing the slide shell.

## Start-Relationship Truth Gate

Record each event as target, phase, effect, order, duration, delay, start relationship, and delivery. A list of effect names is not a timeline.

Keynote duration fields must be committed with Return or by moving focus through a control that commits the edit. A visible typed value is not proof that the archive changed. After saving:

1. Reopen the deck.
2. Run `extract_native_build_timeline.py`.
3. Confirm every duration and relationship from the archive.
4. Export a 60 fps movie.
5. Inspect every frame and transient Build Out state.

If a required `With Build` relationship cannot be set reliably through the inspector, `patch_build_start_relationship.py` may be used only on a new scratch output. It supports direct archives and wrapped `Index.zip` archives. The source and output paths must differ, exactly one native BuildChunk record must match, and the result must pass the reopen, native-extraction, and playback gates above.

## Claim Boundary

This suite proves native compound construction, exact timeline extraction, rendered playback, and lifecycle coverage. It does not prove that every Keynote effect combination is visually appropriate. Choose effects from narrative intent, not benchmark coverage.
