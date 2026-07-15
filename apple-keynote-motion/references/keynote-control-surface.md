# Keynote 15.3 Motion Control Surface

The local scripting dictionary was inspected from Keynote 15.3. Target the app
by bundle identifier, `com.apple.Keynote`, rather than by its filename or display
name. This remains stable when a local installation is renamed.

Use this file to decide which settings can be automated directly and which require UI inspection.

## Slide Transitions

AppleScript exposes:

- transition effect,
- duration,
- delay,
- automatic versus on-click advance.

For Magic Move, the Keynote UI also exposes:

- Fade Unmatched Objects,
- Match By Object, By Word, or By Character,
- Acceleration: None, Ease In, Ease Out, or Ease In & Ease Out.

Those three Magic Move controls are not exposed by the Keynote AppleScript dictionary. Inspect and set them through the Animate sidebar with Computer Use or System Events, then verify visually.

### Inspector Audit Protocol

For a reference-study audit of detailed transition controls:

1. Extract all source slides with non-none transitions through AppleScript.
2. Recover document-to-playback numbering before navigating; Keynote's accessibility navigator can omit skipped slides.
3. Select each source slide by playback number, open Animate -> Transition, and read only controls visible for that effect.
4. Re-fetch the accessibility tree after every selection or sidebar action. Never reuse stale element indices.
5. Record document slide, playback slide, effect, duration, trigger, active automatic delay, and effect-specific controls.
6. Reconcile row count and effect counts against the AppleScript extraction.
7. Spot-check every rare effect and every non-default control manually.

An On Click transition may retain a visible but inactive delay value. Do not report that value as an automatic wait. The completed WWDC20 control audit is summarized in `native-transition-controls.md`.

Official reference: [Add transitions between slides in Keynote on Mac](https://support.apple.com/guide/keynote/tanff5ae749e/mac)

## Builds And Actions

Keynote distinguishes:

- Build In,
- Action,
- Build Out.

The Build Order window controls:

- After Transition,
- On Click,
- With Build N,
- After Build N,
- delay and order.

Text, charts, tables, and lists can use delivery modes such as all at once, by paragraph, by bullet group, by word, or by character depending on the effect and object type.

Action builds can combine Move, Scale, Rotate, and Opacity. Motion paths can include curves and Align to Path.

These detailed settings are not exposed by the public AppleScript dictionary. Capture them from the UI or from rendered build stages. Do not infer build order from raw effect-string order.

Official references:

- [Animate objects onto and off a slide](https://support.apple.com/guide/keynote/tan72234bb6/mac)
- [Animate objects on a slide](https://support.apple.com/guide/keynote/tanf96d92cb6/mac)
- [Change build order and timing](https://support.apple.com/guide/keynote/tan3ad5f8d82/mac)

## Object Structure

The object list is the most useful UI surface for continuity work because it exposes stack order, groups, and editable object names. Naming continuity objects makes complex scenes auditable even though Magic Move identity is preserved most reliably by duplicating the slide.

Public AppleScript exposes position, width, height, rotation, opacity, locked state, text, and selected media properties. It does not expose a complete object style, crop/mask, z-order, group hierarchy, or persistent Magic Move identity API.

Official reference: [Move and edit objects using the object list](https://support.apple.com/guide/keynote/tanc5f5e5382/mac)

## Export And Verification

Keynote AppleScript can export:

- slide images,
- PDF with every build stage,
- QuickTime movie,
- HTML.

Use slide images for state comparison, all-stages PDF for click/build reconstruction, and a movie or controlled live playback for easing and temporal QA.

Official reference: [Export a presentation](https://support.apple.com/guide/keynote/tana0d19882a/mac)
