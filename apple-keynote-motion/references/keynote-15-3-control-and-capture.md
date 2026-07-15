# Keynote 15.3 Control And Capture

Use this reference when Computer Use, duration fields, movie export, or a large Apple reference deck behaves inconsistently.

## Accessibility Discipline

- Use AppleScript bundle identifier `com.apple.Keynote` for document automation. For accessibility automation, resolve the running process after launch because its display name may differ from the app filename.
- Re-fetch accessibility state after every click, selection, value change, or menu action.
- Treat element indices as single-use. Popovers, object handles, and inspector changes renumber the tree.
- Use Keynote's Window menu to select an exact document when several decks are open.
- Prefer accessibility elements. Use screenshot coordinates only when the required control has no accessible element.

An empty accessibility tree with a valid screenshot is a transient control failure, not proof that Keynote is closed.

## Numeric Field Commit Gate

`set_value` can change the visible duration text without committing the model value. For each duration, delay, scale, or opacity field:

1. Select the object and correct inspector phase.
2. Set the value.
3. Re-fetch and confirm the text field.
4. Press Return to commit.
5. Re-fetch and confirm the associated slider or stepper changed.
6. Save.
7. Verify the native archive.

In the compound pilot, uncommitted fields displayed `0.4 s` but the archive still stored `1.0 s`. Pressing Return changed the slider's native value and the extractor then reported `0.4 s` for every event.

## Native Movie Export

AppleScript can request exact export properties:

```applescript
export theDocument to outputFile as QuickTime movie with properties {¬
  movie format:format1080p, ¬
  movie codec:h264, ¬
  movie framerate:FPS60}
```

Validate with `ffprobe` after every export:

- H.264 or the explicitly requested codec.
- 1080-pixel height.
- `r_frame_rate` and `avg_frame_rate` both `60/1`.
- frame count within one frame of duration times 60.

Imported 959-by-540 decks can export at 1918-by-1080. This is still a 1080p render, but record the exact dimensions. Native 960-by-540 decks export at 1920-by-1080.

## Sandbox-Safe Document Matching

- Open a local deck through `open -b com.apple.Keynote deck.key` before AppleScript automation when Keynote may not yet have sandbox access to the path.
- Reuse the already-open document instead of relying on AppleScript `open POSIX file`, which can return `Operation not permitted` for an otherwise readable local file.
- Match an open document by exact POSIX path first, then by both the full basename and the basename without `.key`. Saved Keynote windows can omit the extension from `name`, and matching only the full filename can leave an exporter waiting for a document that is already open.
- Record whether the automation opened the file or reused it. Close only documents opened by the current task.

## Export One Pair From A Large Deck

To avoid changing or copying a multi-gigabyte reference deck:

1. Open a local scratch reference.
2. Mark every slide outside the target pair as skipped in memory.
3. Export the document.
4. Close without saving.

This produced a clean native capture of WWDC20 document slides 26 to 27 without modifying the 2.9 GB scratch deck:

- 1920 by 1080.
- H.264.
- Constant 60 fps.
- 676 frames across 11.267 seconds.
- One active Magic Move interval from frame 300 to 375.
- Exact rendered interval: 5.000 to 6.250 seconds, or 1.250 seconds.
- Visual-energy proxy: ease-in-out.

This method should precede screen recording. A native export has deterministic frame pacing and no cursor, display scaling, or capture-jitter contamination.

## Failure Order

If native export fails:

1. Record the exact deck, pair, codec, resolution, frame rate, and Keynote version.
2. Inspect the Keynote log and run `audit_magic_move_export_risks.py`.
3. Retry the in-memory skipped-slide export from a fresh scratch open.
4. Only after a reproduced zero-bounds failure, test Fade Unmatched off on a labeled capture scratch.
5. Use ScreenCaptureKit or another verified constant-frame-rate recorder only when native export remains unavailable.

Never treat a low-frame-rate screen recording as a 60 fps reference, even if its container metadata claims 60 fps.
