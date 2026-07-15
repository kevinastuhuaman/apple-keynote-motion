# Apple-Style Keynote Transition Playbook

Status note: this was the first-pass style/playbook artifact. For exhaustive motion classification, transition counts, all 120 transition pairs, text/image/video/build/action layering, and future skill design, use:

- `combined-motion-taxonomy.md`
- `all-transition-pairs-index.md`
- `native-transition-controls.md`

This playbook remains useful for visual grammar and high-level presentation taste, but it is no longer the source of truth for transition analysis.

Reference: a user-supplied local copy of the WWDC20 Keynote. The Apple-owned deck and extracted media are not bundled with this skill.

## Evidence Summary

- The WWDC20 `.key` file is a large media-backed Keynote archive, about 2.8 GB.
- The archive contains 472 slide records, 19 template slide records, and 3133 total archive entries.
- It includes 93 video assets: 48 `.mov` files and 45 `.mp4` files.
- It includes 35 audio assets: 18 `.wav`, 9 `.caf`, 5 `.m4a`, and 3 `.m4r`.
- It includes 1699 PNG files and 681 JPEG/JPG files.
- The largest assets are not static slide elements. They are cinematic or product/demo motion assets such as Maps flyover, Face ID UI, TV app sequences, Apple Silicon visuals, Big Sur demos, and spatial audio footage.
- Metadata identifies the template as `20_BasicBlack (10.0)`, which matches the visual system: black stage, white type, high-contrast product imagery, and restrained motion.

The main lesson: this deck is not powered by lots of flashy native transitions. It uses Keynote as a presentation shell around carefully staged product states, short native transitions, Magic Move continuity, and embedded motion/video assets.

## Core Motion Thesis

Apple-style Keynote motion is quiet, intentional, and object-centered. The audience should feel that the product or interface is naturally moving through space, not that a slide transition effect is being shown.

The system is built from five layers:

1. A black stage that removes visual noise.
2. Large, stable hero objects: product renders, UI screens, feature visuals, or big numbers.
3. Sparse copy that gives context without competing with the visual.
4. Short native transitions for continuity between states.
5. Pre-rendered videos for complex motion that Keynote should not try to fake.

## Transition Patterns Observed

### No Transition For Landing Or Stat Slides

Several high-impact slides rely on no slide transition at all. For example, the inspected `97%` availability slide uses a black background, a huge centered statistic, and no transition effect.

Use this when the slide itself is the beat. A cut can feel more premium than motion when the content is already bold and clean.

Good use cases:

- Big numbers.
- Feature names.
- Section dividers.
- Final landing states after a product animation.
- Slides where builds or embedded video carry the motion.

### Dissolve For Related UI States

Native-observed distribution across all eight Dissolves:

- Duration: `0.4s` (1), `0.6s` (2), `1.0s` (3), `1.25s` (2)
- Start: `On Click` (7), `Automatically` (1)
- The automatic case is document `346` / playback `343`, `1.0s` after `25.0s`, coordinated with media.

The inspected CarPlay sequence used short dissolves between visually related interface states. The layout remained familiar, and the dissolve softened the state change without calling attention to itself.

Use this when:

- The next slide is the same product or UI family.
- The viewer should notice a state change, not a spatial move.
- Objects do not need to maintain exact positional continuity.
- The change is informational rather than cinematic.

Default recommendation:

- `Dissolve`, `0.6 s`, `On Click`.

### Magic Move For Product And UI Continuity

Native-observed settings from all 106 Magic Move inspector panels:

- Fade Unmatched Objects: on for all 106
- Match: `By Object` (102), `By Character` (3), `By Word` (1)
- Acceleration: `Ease In & Out` (101), `Ease Out` (4), `Ease In` (1)
- Start: `On Click` (82), `Automatically` (24)
- Duration: `0.3s` through `12s`; `0.8s` is most common at 41 transitions

Magic Move is the core native Keynote transition for Apple-style motion. The reference deck uses it when the same visual object continues across consecutive slides: a product render, UI surface, icon group, or feature element.

Duration appears tuned to movement distance and narrative weight:

- `0.8 s`: modest UI/object rearrangements.
- `1.25 s`: medium hero movement or zoom.
- `1.5 s`: larger product-scale move or more cinematic emphasis.

Default recommendation:

- `Magic Move`, `0.8 s`, `Fade Unmatched Objects` on, `Match By Object`, `Ease In & Out`, `On Click`.
- Raise to `1.25 s` or `1.5 s` only when the hero object travels farther, scales significantly, or needs a more deliberate cinematic beat.

The long `2s`, `3s`, `3.5s`, and `12s` cases are specialized scenes and should not become defaults. Inspect their playback and media timing before borrowing them.

### Push For Directional Chapter Movement

Native-observed settings:

- Documents `221-224` / playback `219-222`: `0.75s`, Right to Left, On Click.
- Document `384` / playback `381`: `1.0s`, Bottom to Top, On Click.

Use Push only when the direction has semantic value, such as moving through a horizontal sequence or lifting into a new chapter. It is not a substitute for object continuity.

### Object Flip For A Two-Sided Metaphor

The only Object Flip is stored on document slide `290` and transitions `290->291`; because two skipped slides precede it, the playback pair is `288->289`. It lasts `0.8s` and starts On Click. Keynote 15.3 exposes no additional direction control in this inspector state.

Use it only when the content genuinely behaves like two sides of the same object, as in the App Privacy to Nutrition Facts metaphor.

### Embedded Video Carries Complex Motion

The deck repeatedly uses embedded high-resolution videos for motion that would be weak or time-consuming as native Keynote builds. Examples include Maps flyovers, UI animations, chip visuals, product footage, spatial audio visuals, and app demos.

The inspected U1 chip section shows the pattern clearly:

1. Magic Move brings the product/chip visual into the right stage position.
2. A later slide has no transition.
3. The embedded movie carries the active motion.

Use this when:

- The motion is detailed, atmospheric, or continuous.
- UI interaction needs to feel real.
- You need depth, particles, camera moves, waves, reflections, or product spin.
- The animation would require many manual Keynote builds.

Default recommendation:

- Use Keynote native transitions for spatial continuity.
- Use video for animation quality.
- Do not make Keynote do advanced motion graphics if a rendered asset will look better.

## Design Grammar

### Black Stage

The reference deck’s `BasicBlack` template matters. The black canvas makes Apple’s white typography, product surfaces, and saturated UI visuals feel precise and premium.

Rules:

- Default to black or near-black background.
- Avoid decorative gradients and visual filler.
- Let the product or UI create the visual interest.
- Use contrast, scale, and spacing instead of ornament.

### One Dominant Idea Per Slide

The deck often treats slides as states inside a sequence, not as standalone information pages. A slide can exist only to support one transition step.

Rules:

- One hero visual or one message per slide.
- If a slide needs three ideas, split it.
- If a transition needs a staging slide, create it.
- Do not force every slide to be information-dense.

### Object Continuity

Magic Move works best when the same object exists on adjacent slides and is matched by object identity. The deck’s polished feel comes from moving the product or UI object itself, not from applying generic effects.

Rules:

- Duplicate slides before moving objects.
- Keep matched objects consistent across consecutive slides.
- Keep grouped objects grouped if the group should move as one thing.
- Use off-canvas positions deliberately for entrances/exits.
- Fade unmatched objects rather than forcing everything to move.

### Motion Restraint

Professional Apple-style motion avoids gimmicks. Effects such as sparkle, confetti, cube, doorway, blinds, and other theatrical transitions should generally be avoided unless the deck has a deliberately playful moment.

Preferred native effects:

- No transition.
- Dissolve.
- Magic Move.
- Occasional simple move/fade only when needed.

Avoid by default:

- Confetti.
- Sparkle.
- Cube.
- Doorway.
- Blinds.
- Flip.
- Mosaic.
- Page turn.
- Any transition the audience would describe as an effect.

## Practical Build Workflow

### 1. Storyboard As Scenes

Think in short cinematic sequences, not isolated slides.

Example sequence:

1. Section title or feature name.
2. Product/UI hero appears cleanly.
3. Magic Move zooms, repositions, or reveals the relevant area.
4. Embedded demo/video shows the feature in motion.
5. Big takeaway or metric lands with no transition.

### 2. Build The Static State First

For each scene, create the final clean visual state first. Make sure typography, spacing, hierarchy, and image quality work before adding motion.

### 3. Duplicate For Motion

Use duplicated slides as adjacent states. Move, scale, crop, or fade objects between duplicates. Then apply Magic Move.

### 4. Add Native Transitions Sparingly

Use these defaults:

- Big beat: no transition.
- Related UI state: `Dissolve`, `0.6 s`.
- Same object continuity: `Magic Move`, `0.8 s`, `Fade Unmatched Objects` on, `Match By Object`, `Ease In & Out`.
- Hero object continuity: `Magic Move`, `1.25 s` to `1.5 s`, same settings.

### 5. Add Rendered Motion Assets

When motion should feel cinematic or product-grade, use video. Keep it visually integrated with the slide stage.

Recommendations:

- Prefer transparent or black-background motion assets when they must sit on the black stage.
- For UI demos, export clean video at the final display aspect ratio.
- Avoid visible player controls, compression artifacts, or mismatched black levels.
- Use video to complete a motion idea after Magic Move sets up the stage.

### 6. Preview In Presentation Mode

Do not judge timing only in the editor. Test in presentation mode because build pacing, click rhythm, and transition timing feel different when played full-screen.

Check:

- Does the motion direct attention to the right object?
- Does any transition feel like a gimmick?
- Does the click rhythm feel calm and intentional?
- Are there any unmatched objects that pop unexpectedly?
- Is the video motion doing work that a native transition should not?

## Recommended Defaults For Future Decks

| Situation | Transition | Duration | Settings |
| --- | --- | ---: | --- |
| Big title, stat, or section beat | None | n/a | Use cut or builds only |
| Same visual family, different UI state | Dissolve | 0.6 s | On Click |
| Modest object continuity | Magic Move | 0.8 s | Fade Unmatched on, Match By Object, Ease In & Out |
| Hero product move or zoom | Magic Move | 1.25-1.5 s | Fade Unmatched on, Match By Object, Ease In & Out |
| Complex product/UI animation | None or setup transition | n/a | Use embedded video for the active motion |

## Production Checklist

- Use a duplicate deck while experimenting. Do not edit the reference deck.
- Start from a black-stage template.
- Keep slide copy minimal and large enough to feel intentional.
- Use high-resolution product/UI assets.
- Create sequences from duplicated slides.
- Use Magic Move only when object continuity is real.
- Keep `Fade Unmatched Objects` on for Magic Move unless there is a specific reason not to.
- Use `Match By Object` for predictable continuity.
- Keep acceleration at `Ease In & Out`.
- Use `Dissolve 0.6 s` for related UI state changes.
- Use no transition for clean beats and post-animation landing states.
- Render complex animations as videos.
- Preview every sequence full-screen.
- Cut any transition that draws attention to itself instead of the product.
