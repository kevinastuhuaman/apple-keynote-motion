# Visual Transition Archetypes From WWDC20

This reference summarizes a visual review of every playable transition pair in the WWDC20 source deck: 119 rendered source/destination pairs. Keynote rendered 468 playback slides from 472 document slides because four slides are skipped. Document `436->437` is therefore document adjacency only; slide 437 has no playback render.

Evidence boundaries:

- Transition effect and duration are `native-observed` from the deck.
- Source and destination composition described below are `visual-observed` from Keynote PNG exports.
- Object identity and intermediate travel are `inferred` until continuity is verified in the native object model or playback frames.
- Detailed Magic Move matching, Fade Unmatched Objects, acceleration, and Push direction were subsequently inspected in Keynote 15.3 for all 120 source slides. See `native-transition-controls.md`; endpoint composition in this file remains a separate visual observation.

Do not describe these static endpoint comparisons as frame-by-frame animation analysis.

## 1. Hero To System

Representatives: document/playback `26->27/26->27`, `118->119/118->119`, `223->224/221->222`, `380->381/377->378`.

A single product, device, or icon expands into a lineup or grid. Keep the original hero as the visual anchor and add context around it. Recommended for introducing an ecosystem after establishing one recognizable object.

## 2. System To Hero

Representatives: `438->439/434->435`, `439->440/435->436`, `446->447/442->443`.

A dense grid dims or collapses so one app, tool, or capability becomes the focal point. This is the inverse of Hero To System and works well for chaptering a crowded feature set.

## 3. Device To Detail

Representatives: `52->53/52->53`, `134->135/134->135`, `245->246/243->244`, `247->248/245->246`.

The product remains recognizable while its screen, control, or app content grows to fill more of the stage. Preserve a stable device edge or frame long enough for the audience to understand the zoom target.

## 4. Detail To Device Context

Representatives: `58->59/58->59`, `82->83/82->83`, `83->84/83->84`, `84->85/84->85`.

A cropped interface, text field, or content detail resolves back into its containing device. Use this to show where a feature lives after demonstrating the feature itself.

## 5. Progressive Product Lineup

Representatives: `20->21/20->21`, `21->22/21->22`, `117->118/117->118`, `118->119/118->119`, `205->206/204->205`.

One more device or state enters while prior objects retain their relative logic. The sequence works because each click changes one variable rather than rebuilding the entire composition.

## 6. Stable Frame, Changed State

Representatives: `174->175/173->174`, `175->176/174->175`, `176->177/175->176`, `177->178/176->177`.

The app or browser frame remains stable while a banner, call state, or content layer changes. This is the clearest comparison pattern for UI state transitions. Avoid moving the frame unless the movement itself conveys meaning.

## 7. Orbit Or Social Cluster

Representatives: `87->88/87->88`, `88->89/88->89`, `89->90/89->90`.

People, avatars, or related objects reorganize around one dominant center. Use only when relationships are the story. Keep the cluster readable at the final state and avoid arbitrary orbital movement.

## 8. Grid Montage Expansion

Representatives: `166->167/166->167`, `202->204/202->203`, `384->385/381->382`, `390->391/387->388`, `394->395/391->392`.

A product screen or small set expands into a rich montage of examples. Dense endpoints require slower timing, usually `0.8-1.25s`, and a clear persistent anchor. If every item is unmatched, a dissolve may be cleaner than forced Magic Move.

## 9. Metric Or Chart Refocus

Representatives: `244->245/242->243`, `245->246/243->244`, `264->265/262->263`, `265->266/263->264`, `426->427/423->424`.

Move from the whole dashboard to one graph, metric, or explanatory framework. Keep axes and labels static when possible; move the viewport or emphasis instead of animating every chart element.

## 10. Product On Live Background

Representatives: `219->220/217->218`, `220->221/218->219`, `422->423/419->420`, `423->424/420->421`, `416->417/413->414`.

A product appears beside a presenter or live-action background, then becomes the dominant object. Preserve the presenter/background as a calm plate and animate only the product-scale relationship.

## 11. App Family Expansion

Representatives: `304->305/302->303`, `305->306/303->304`, `380->381/377->378`, `381->382/378->379`, `438->440/434->436`.

Start with one logo or a small family, reveal the broader set, then select one hero. This creates a reliable three-beat sequence: establish, expand, refocus.

## 12. Modal Or Front/Back Reveal

Representative: document `290->291`, playback `288->289`, `0.8s`, Object Flip.

A compact information card turns into a privacy or disclosure panel. Object Flip is justified only because the content behaves like two sides of one object. The following `292->293/290->291` Magic Move expands the panel into a broader information state.

## 13. Text Label To Product Identity

Representatives: `446->447/442->443`, `447->448/443->444`, `459->460/455->456`.

A short product name resolves into an icon or physical object, then supporting copy arrives. Preserve one identity cue across the sequence; do not animate long paragraphs as the continuity object.

## 14. Ecosystem Recap

Representatives: `456->457/452->453`, `470->471/466->467`.

Previously introduced products assemble into one final lineup. Use this near a section payoff or recap. The final state should feel complete, not like another intermediate collage.

## 15. Quiet Reset

Representatives: `35->36/35->36`, `36->37/36->37`, `124->125/124->125`, `343->344/343->344`, `399->400/399->400`.

Dissolve resets the scene when spatial continuity is weak or irrelevant. Apple uses it sparingly between related visual plates and section openings. Do not replace a meaningful transform with a dissolve merely because it is easier.

## Reuse Rule

Choose an archetype from narrative intent, then construct the source and destination states. Do not copy a pair because it looks impressive. A faithful Apple-style sequence usually preserves one visual proposition per click and one recognizable anchor across the change.
