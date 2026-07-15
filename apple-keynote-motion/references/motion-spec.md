# Keynote Motion Spec 2.0

Use a motion spec whenever the task requires implementation, iteration, or exact handoff. The spec is the contract between narrative intent, Keynote settings, and rendered QA.

## Evidence Labels

- `native-observed`: extracted directly from Keynote or the `.key` archive.
- `visual-observed`: confirmed in a rendered slide, build stage, or playback clip.
- `inferred`: reconstructed from object/text/media evidence and not directly verified.
- `recommended`: a design decision for the new deck.

Never present `inferred` or `recommended` values as facts about a reference deck.

## Minimal Example

```json
{
  "version": "2.0",
  "deck": {
    "title": "Example",
    "width": 1920,
    "height": 1080
  },
  "scenes": [
    {
      "id": "hero-to-detail",
      "intent": "refocus",
      "evidence": "recommended",
      "states": [
        {
          "slide": 4,
          "label": "hero",
          "objects": [
            {
              "id": "product",
              "type": "image",
              "role": "continuity",
              "frame": {"x": 380, "y": 140, "width": 1160, "height": 760},
              "opacity": 100
            }
          ]
        },
        {
          "slide": 5,
          "label": "detail",
          "objects": [
            {
              "id": "product",
              "type": "image",
              "role": "continuity",
              "frame": {"x": 90, "y": 110, "width": 820, "height": 820},
              "opacity": 100
            },
            {
              "id": "detail-label",
              "type": "text",
              "role": "entry",
              "frame": {"x": 1040, "y": 410, "width": 650, "height": 140},
              "opacity": 100
            }
          ]
        }
      ],
      "transition": {
        "from_slide": 4,
        "to_slide": 5,
        "effect": "magic-move",
        "duration": 0.8,
        "advance": "on-click",
        "delay": 0,
        "magic_move": {
          "match": "by-object",
          "fade_unmatched": true,
          "acceleration": "ease-in-out"
        }
      },
      "builds": [
        {
          "id": "label-in",
          "slide": 5,
          "target": "detail-label",
          "phase": "build-in",
          "effect": "dissolve-character",
          "duration": 0.45,
          "delivery": "all-at-once",
          "start": "after-transition",
          "delay": 0.1,
          "order": 1
        }
      ]
    }
  ]
}
```

## Required Fields For Implemented Work

For each transition, record:

- source and destination slide numbers,
- effect, duration, advance mode, and delay,
- Magic Move match mode, fade-unmatched setting, and acceleration,
- continuity, entry, exit, and intentional off-canvas objects.

For each build or action, record:

- target object,
- build-in, action, or build-out phase,
- effect and effect-specific parameters,
- order,
- start relationship (`after-transition`, `on-click`, `with-build`, or `after-build`),
- relative build when applicable,
- duration, delay, acceleration, direction, and delivery when the UI exposes them.

Run:

```bash
python3 scripts/validate_motion_spec.py motion-spec.json
```

The validator checks choreography invariants. It cannot prove that the live Keynote document matches the spec; use round-trip extraction and rendered QA for that.
