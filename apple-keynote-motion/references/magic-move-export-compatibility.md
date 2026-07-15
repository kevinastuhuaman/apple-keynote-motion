# Magic Move Export Compatibility

## Observed Failure

Keynote 15.3 failed to export WWDC20 document slides 456 to 457 even though live playback and visible geometry were valid. The application log contained:

```text
KNMagicMoveMatchMaker.m:1922 zero width or height bounding rect for texture!
```

The pair contained a zero-size `slideNumberPlaceholder` on both slides while Fade Unmatched Objects was enabled. Disabling Fade Unmatched Objects on the source slide of a scratch copy allowed the 1080p/60 fps export to complete.

## Evidence Boundary

- Zero-size geometry and Fade Unmatched flags are `native-observed`.
- The relationship between those fields and the Keynote assertion is `inferred` from a reproduced failure.
- A risk flag does not prove that a pair will fail.

The WWDC20 audit flags 106 Magic Move pairs with paired zero-size paths and Fade Unmatched enabled. Spring Loaded flags 37 of 39 pairs as high risk, but its AirTag 31 to 32 pair exported successfully with the original setting. The audit is intentionally sensitive and is not a deterministic failure predictor.

## Recovery Order

1. Preserve the original reference deck and its controls.
2. Export from a local scratch copy.
3. For a large deck, mark every non-target slide as skipped in memory, export the pair, and close without saving.
4. If export succeeds, do not change anything based only on a risk flag.
5. If export fails, record the exact pair, codec, frame rate, and Keynote version.
6. Check the Keynote application log for the zero-bounds assertion.
7. Run `audit_magic_move_export_risks.py` and inspect paired zero-size paths.
8. Reopen a fresh scratch and retry the in-memory skipped-slide export once.
9. On the scratch copy only, disable Fade Unmatched Objects for the failing source slide and retry.
10. Label the movie as an export-repaired capture and retain the original inspector value in the audit.

WWDC20 slides 26 to 27 initially appeared non-exportable but later exported with native controls unchanged through the in-memory skipped-slide method. The result was 1920 by 1080 H.264 at constant 60 fps, with the complete 1.250-second Magic Move preserved. Treat a first failure as reproducible evidence to investigate, not a permanent property of the pair.

Do not delete placeholders or rewrite visible geometry as the first response. Do not propagate the temporary export setting back into the original Apple deck.

## Read-Only Audit

```bash
python scripts/audit_magic_move_export_risks.py reference-copy.key \
  --output-dir audit/magic-move-export-risks
```
