# Apple Developer API Deck Case Study

Source task: Advanced Commerce on the App Store developer-facing deck polish.

## Design Constraints

- Use SF Hello when it is installed. Helvetica is only a fallback.
- Keep slide backgrounds static black. Avoid gradient backgrounds.
- Do not over-simplify a technical deck just because it is Apple-style. Keep developer substance, but move density into diagrams and presenter narration instead of paragraph-heavy slides.
- Use SF Mono for code blocks when code readability matters; keep the surrounding deck typography SF Hello.

## Story Pattern

A strong Apple Developer API deck can carry more detail than an Apple event product teaser. The useful structure:

1. Name the API and the developer-facing promise.
2. Explain the existing trusted system it extends.
3. Show the new developer/business pressure.
4. State the API in one sentence.
5. Show who it is for.
6. Use Magic Move to compare old/static catalog setup with new/dynamic catalog setup.
7. Use a multi-slide Magic Move purchase flow for implementation.
8. Follow with one concrete payload/code slide.
9. Show what Apple handles and what the developer owns.
10. Close with requirements, limits, getting started, and apply CTA.

## Advanced Commerce Choreography

The strongest sequence is not a single dense architecture slide. Build it as states:

- `catalog source` -> `app` -> `App Store commerce`
- dynamic catalog row enters beneath a dimmed static catalog row
- Magic Move duration: `1.0s`
- then purchase flow:
  - server hero
  - server + app
  - StoreKit 2 purchase
  - App Store commerce
  - App Store Server notification
  - verification/unlock return path
- Magic Move duration: `0.8s-0.9s`

Use object opacity and position changes to keep continuity. Do not rely on build effects when public Keynote scripting cannot set them reliably.

## Automation Notes

- Keynote AppleScript can create slides, text, images, duplicate slides, and set transition properties.
- In this environment, image insertion works with:
  `make new image with properties {file:POSIX file filePath}`
- `duplicate slide` does not return the new slide object. Duplicate, then bind the destination by slide index, usually the last slide if appending:
  `duplicate s1 to after s1`
  `set s2 to slide (count of slides of d) of d`
- Exporting slide images from the live generated document is the most reliable visual QA path.
- For final current-format `.key`, native save can write a valid `Index/*.iwa` deck. If close hangs, interrupt after the file is written and close the generated document in a separate AppleScript command.
- Keynote 09 export produces `index.apxl`; it may not be compatible with this skill's `.iwa` analyzers. Prefer native save for final `.key` deliverables.
