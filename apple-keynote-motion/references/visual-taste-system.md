# Apple Keynote Visual Taste System

Use this reference before motion design. Motion amplifies the static state; it does not repair weak hierarchy, generic imagery, or an unclear story.

## Evidence Boundary

- The strongest rendered corpus is WWDC20 black-stage product and UI choreography.
- The local private corpus spans nine user-supplied Apple-event deck copies from 2016–2021, but archive provenance does not prove that every embedded asset was created or licensed by Apple.
- Treat type sizes, margins, crop ratios, and colors as `recommended` until measured from a rendered source in the same presentation family.
- Do not average product events, platform keynotes, developer/API decks, demos, and executive presentations into one visual style.

## Route By Presentation Family

| Family | Primary job | Typical density | Visual anchor | Motion bias |
| --- | --- | --- | --- | --- |
| Product event | Create desire and clarity | 0–1 | Product render, feature visual, live plate | Hero continuity, reveal, payoff |
| Platform keynote | Explain a system at scale | 1–2 | UI, icon family, system diagram | Expansion, comparison, sequence |
| Developer/API | Teach adoption and implementation | 2–3 | Code, request/response, architecture | Stable shell, staged explanation |
| Demo/UI walkthrough | Show behavior truthfully | 1–2 | Device or application surface | State toggle, refocus, embedded demo |
| Executive/business | Support a decision | 1–2 | Metric, trend, framework | Compare, prove, land |

Select the closest family first. Borrow from another family only when the scene role is compatible.

## Tag Every Slide

Record these tags in the motion spec or production notes:

- `scene-role`: establish, explain, inspect, compare, prove, transform, payoff, reset.
- `composition`: one of the families below.
- `stage`: black, near-black, light-neutral, media-field, product-sampled.
- `density`: 0 beat, 1 hero, 2 explained, 3 technical.
- `primary-anchor`: the first object the audience should see.
- `secondary-evidence`: one supporting visual or statement.
- `tertiary-annotation`: labels that may be removed without losing the idea.
- `pace`: hold, reveal, accumulate, refocus, breathe, land.

If the primary anchor cannot be named in one phrase, split the slide.

## Composition Families

### Identity Or Word Beat

- One short phrase, product name, feature name, or metric.
- Use the stage itself as the frame; do not add a card.
- Centered or deliberately offset, with no competing support copy.
- Density 0. Prefer a cut or a restrained Build In.

### Centered Hero

- One complete product, icon, or interface object dominates the stage.
- Support copy is absent or one short line.
- Preserve enough empty stage for the object to feel intentional.
- Best for establish, transform setup, and payoff.

### Hero Plus Copy

- One visual and one text block; one must clearly dominate.
- Align to a common optical center, not merely equal columns.
- Keep copy short enough to be spoken rather than read silently.
- Avoid generic split-screen marketing composition when the product should own the viewport.

### UI Or Device Detail

- Show the real interface or device at inspectable resolution.
- Crop around the behavior being discussed, not around decorative symmetry.
- Add at most one active callout layer per click.
- Preserve the shell across adjacent states when using Magic Move.

### Full-Bleed Media Field

- Photography or video is the stage, not an image inside a floating card.
- Place type only over a region with stable contrast and quiet detail.
- Use a clean cut when the next media field changes completely.

### Live Plate Plus Product

- Use environmental photography to establish context; keep the product truthful and legible.
- Match black levels, perspective, and lighting before adding motion.
- Avoid stock-like atmospheric imagery that does not reveal the product or behavior.

### Comparison

- Keep the comparison axis stable: before/after, old/new, option A/B, or metric A/B.
- Use equal geometry only when equal weight is the message.
- Change one variable per state; do not animate every label independently.

### Process Or Architecture

- Use a stable spatial grammar: left-to-right flow, top-to-bottom stack, or hub-and-spoke.
- Reveal in causal order.
- Keep arrows and connectors subordinate to named system objects.
- Prefer native shapes and text over a single flattened diagram when staged explanation matters.

### System Or Grid

- The grid is evidence of breadth, not decoration.
- Use consistent cell geometry and visual weight.
- Enter as a coordinated wave or expand from a real hero object.
- Avoid filling every empty region merely because assets are available.

### Metric Or Chart

- Lead with the decision-relevant number or trend.
- Reveal axes/scaffold before data only when the audience needs orientation.
- Keep chart decoration below the weight of the conclusion.

### Recap Lineup

- Resolve a sequence into three or four memorable outcomes.
- Reuse objects already introduced rather than adding a new visual language.
- Finish with one sentence or action, not another explanatory section.

## Typography

Use SF Hello when it is installed and authorized for the user's environment. Fall back to Helvetica when unavailable. Use SF Mono for code and fixed-width payloads. Never bundle proprietary fonts.

Define roles before selecting point sizes:

| Role | Function | Recommended behavior |
| --- | --- | --- |
| Chapter | Reset attention | Short, dominant, little or no support text |
| Headline | State the slide idea | One thought; usually one or two lines |
| Metric | Carry the proof | Larger than the headline when it is the argument |
| Support | Add essential context | One compact sentence or phrase |
| Label | Name an object | Small but immediately legible at playback distance |
| Annotation | Clarify one detail | Lower contrast; remove when it competes |
| Code | Demonstrate implementation | Monospaced, cropped to the lines being discussed |

Rules:

- Use weight, size, and opacity to create hierarchy; do not rely on many colors.
- Preserve line breaks across motion states unless reflow is the visual idea.
- Keep long prose in presenter notes.
- Technical density is allowed, but reveal or highlight the exact line being discussed.
- Match type scale to the container. Compact panels do not receive hero typography.
- Keep letter spacing at zero unless an existing source demands otherwise.

## Stage And Color

- Default to static black for product-event and dark developer scenes when compatible with the source family.
- Use light-neutral stages for documentation-like technical explanation only when that improves readability.
- Derive accents from the product, UI, or semantic state already on screen.
- One accent family per scene is usually enough.
- Use gray for hierarchy, not as a substitute for weak contrast.
- Do not use decorative gradients, gradient orbs, or bokeh fields.
- Check that embedded videos and images match the stage black at their edges.

## Image And Asset Treatment

Choose the treatment from the narrative job:

| Job | Preferred treatment |
| --- | --- |
| Establish the product | Complete product cutout or truthful hero render |
| Explain a feature | Device/UI detail with one focal crop |
| Show breadth | Ordered grid of related assets with consistent scale |
| Show context | Full-bleed photograph or live plate |
| Show implementation | Native code, payload, diagram, or request/response surface |
| Show change | Same shell, one changed state or highlighted region |

Cropping rules:

- Crop to increase meaning, not to make the image fill a rectangle.
- Preserve recognizable product geometry when identification matters.
- Allow intentional edge crops only when the object remains unambiguous.
- Keep device perspective and scale consistent across continuity states.
- Do not enlarge low-resolution screenshots beyond inspectable quality.
- Treat alpha, mask, crop, z-order, and stage black as part of the asset.

## Density And Hierarchy

- `density 0`: one phrase, name, or number.
- `density 1`: one hero plus one support statement.
- `density 2`: one visual system plus two or three explanatory elements.
- `density 3`: technical slide with code, payload, architecture, or detailed comparison.

Sequence density deliberately. A run of density-3 slides needs a density-0 or density-1 reset. Do not solve a dense slide by shrinking everything; split the explanation into states.

## Sequence Rhythm

- Establish: create a clear frame and let it breathe.
- Explain: accumulate only the elements needed for the sentence being spoken.
- Refocus: preserve context while moving attention to one detail.
- Prove: show the metric, behavior, or implementation evidence.
- Land: remove scaffolding and resolve to one remembered idea.

Judge pacing in presentation mode. Slide hold time depends on narration and information load, not transition duration alone.

## Static Anti-Patterns

- Card carpets with equal visual weight.
- Generic centered title repeated on every slide.
- Product imagery used as decoration rather than evidence.
- Tiny technical text shown all at once.
- Arbitrary crops that hide recognizable product geometry.
- Multiple accent colors without semantic meaning.
- Headline, subtitle, labels, and diagram all competing at full white.
- Excessive on-slide conclusions that repeat the presenter.
- Recreating an available high-quality source asset with a weaker generic substitute.
- Using an Apple-supplied asset without recording provenance or checking whether reuse is authorized.

## Visual Completion Gate

Before motion implementation, verify:

- the presentation family and scene role are explicit,
- the primary anchor wins at thumbnail size,
- the slide has one dominant idea,
- type roles and density are intentional,
- asset source and reuse status are recorded,
- crop and resolution survive full-screen playback,
- stage color and media edges match,
- removing tertiary annotation improves or preserves comprehension,
- the next and previous states form a coherent sequence.
