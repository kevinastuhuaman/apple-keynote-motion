# Dense Object Expansion Benchmark

Use this benchmark for one-to-system reveals, dense icon fields, storefront families, product grids, and other scenes where dozens of independent objects must remain legible while the composition expands.

## Reference Pattern

WWDC20 document slides 26 to 27 provide the canonical pattern.

`native-observed` transition controls:

- Magic Move.
- 1.25 seconds.
- Match By Object.
- Fade Unmatched Objects on.
- Ease In & Out.
- On Click.

`visual-observed` choreography:

- State 1 presents one complete iPhone Home Screen in the center.
- State 2 moves that lead screen to the left and reveals four related Home Screen panels across the remaining width.
- The new panels begin from a tight overlapping source region, then separate into an ordered horizontal system.
- The viewer first reads one familiar object, then the scale of the complete system.

`inferred` adjacent-state analysis:

- 372 source objects and 276 destination objects.
- 260 matched objects.
- 259 matched objects move.
- 260 matched objects scale.
- 16 objects appear and 112 disappear.
- 96 matched text objects move or scale.

These counts describe the archive comparison, not a guaranteed reconstruction of Keynote's internal Magic Move matcher.

## Production Recipe

1. Build the complete expanded destination first.
2. Duplicate backward to create the single-object setup state.
3. Preserve each panel, icon, and label as the same object across both slides.
4. Move all future sibling objects into a tight overlapping source region.
5. Set future siblings to zero opacity in the setup state when they should not be visible yet.
6. Keep the lead object fully visible. It becomes the destination's left anchor.
7. Use 1.0 to 1.25 seconds when 50 or more objects travel or scale together.
8. Keep one stable reading order: lead object first, then siblings from left to right.

Do not distribute objects from random off-canvas directions. The effect reads as a system unfolding from one source because every sibling shares the same visual origin.

## Candidate Validation

An Advanced Commerce benchmark was built with:

- 5 storefront panels.
- 60 independently matched product icons.
- 2 persistent text objects.
- 67 objects on each motion state, including 65 persistent images.
- A 1.25-second Magic Move from one catalog to five storefronts.
- A 0.9-second Magic Move from the storefront system to one product hero.
- Match By Object, Fade Unmatched Objects on, Ease In & Out, and On Click for both transitions.

The v3 candidate movie exported successfully at 1920 by 1080 and 60 fps. Frame analysis detected a 1.167-second expansion interval and a 0.833-second refocus interval. The expansion's visual-energy proxy classified as ease-in-out, matching the native control. The refocus proxy classified as ease-out even though the native control remains Ease In & Out; the growing product hero dominates rendered pixel energy, so the proxy is not a replacement for the inspector value. Visible-pixel intervals can be shorter than inspector duration because static opening and settling frames do not cross the analysis threshold.

A later native export of the WWDC20 reference pair closed the comparison gap. The reference rendered at 1920 by 1080, constant 60 fps, with an exact active interval of 1.250 seconds and an ease-in-out visual-energy proxy. Comparing the reference interval to the candidate v3 expansion produced a scoped temporal-motion-fidelity score of **96.102/100**. The segment itself scored 95.414; the final score also includes perfect one-to-one segment structure. This score excludes content, imagery, typography, object identity, layout, composition, semantic attention quality, and overall Apple design similarity.

## V2 To V3 Learning

The dense image choreography worked in v2, but separate incoming and outgoing headline boxes crossed near the frame edges during the transition. V3 keeps one title object fixed in place and changes its text on the duplicated slide. It also removes the support line from the final product-focus state and moves the dimmed five-panel context below the product.

Reusable rule:

- Dense object movement and text movement should not compete for attention.
- When the title is context, preserve one stable text box and change content in place.
- Use a moving title only when the title movement is itself the narrative idea.
- In a refocus state, move or dim the system far enough that the selected object is the only primary target.

## Export Compatibility

An early attempt to export the Apple reference failed, and the deck contains 97 paired zero-size paths in the export-risk audit. A later export succeeded with the native controls unchanged by opening the 2.9 GB scratch deck, marking every slide except 26 and 27 as skipped in memory, exporting, and closing without saving. The candidate v3 archive contains three paired zero-size paths on each Magic Move pair, and both candidate pairs also exported successfully.

This confirms that the audit is a warning surface rather than a deterministic failure test. Retry a fresh in-memory pair export before changing any native control. Only test Fade Unmatched Objects off on a labeled scratch capture after a reproduced export failure.

## Claim Boundary

This benchmark validates dense-object continuity, attention choreography, native controls, and rendered timing. Its 96.102 score applies only to temporal motion in one aligned expansion interval. It does not establish overall visual similarity to Apple and must not be reported as a numerical Apple-style percentage.
