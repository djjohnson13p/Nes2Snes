# Verified status — 2026-09-26

## Current: optional native inline-table dispatch

The new `--native-inline-dispatch` option replaces a fully classified table-
dispatch routine with a guarded native wrapper. It retains the original body,
raw-data mapping, register/scratch/stack behavior and unknown-code fault guard.
Unsupported contexts use the original routine; the option is off by default.

283 unit tests pass. The new independent NES/SNES matrix passes 45 configurations,
1,992 records and 7,968 register-and-flag bytes. The retained runtime-safety matrix
passes 32 configurations and 4,224 records, with its audio and fault checks intact.
The dedicated GitHub workflow passed on integration revision
`872fa58060073e85f1cbd055038fe63f8865c2cb`.

Fixed-input walking takes 147 display frames for 120 game updates, versus 149
before (1.36% higher throughput). Jumping and attacking are unchanged. A fresh
31-step approach plus 84-action outdoor/respawn route completes on both platforms,
with all 420 selected state fields / 756 bytes equal. The candidate uses 15,124
display frames versus 15,242 in the baseline (0.78% higher throughput).

All 231 consecutive presented game-frame hashes in a bounded replay interval
match the previous SNES renderer: 13,246,464 pixel positions. This is not an
independent-NES visual equivalence result or all-game test. No new boss or stage
clear, audio correction, raster correction, or full-speed result is claimed.

See [native-dispatch implementation and limits](native-dispatch.md) and
[measurements](native-dispatch-verification.json).

## Previous: guarded paired-route timing and outdoor/respawn coverage

The route test distinguishes full NMI updates from skipped interrupt entries
and aligns startup consistently. Guarded mode recognizes the original fixed-bank
guard; it does not use a manual timing offset or edit guest state. The old legacy
mode remains available for historical reproduction.

That checkpoint expanded instruction coverage from 10,763 to 11,553 entries by
combining legacy and guarded traces. This pass regenerated a narrower union of
the earlier trace plus guarded route (11,214 entries); it does not replace the
larger union or establish full-game coverage. Both private game comparisons use
identical traces for baseline and candidate.

The earlier clock checkpoint passed 272 unit tests and independently checked
eight snapshots / 16,384 NES RAM bytes. Its 84 instrumented NES images and RAM
snapshots were reproduced by unmodified NES execution: 4,816,896 pixels and
172,032 RAM bytes. Those counts are NES-versus-NES, not NES-versus-SNES pixels.
See [method and limitations](route-clock.md).

## Retained runtime

The native controller replacement, counter-free profiling option, OAM destination
correction, and optional background DMA/fill-cache correction remain available.
The indirect-X shortcut remains optional and does not accelerate the observed
CV3 path. The older unpublished indirect-load flag-merge experiment is not part
of this dispatch change.

## Completion status

The project remains a trace-bounded native-execution compatibility bridge, not
a universal converter or completed native engine rewrite. Full speed, accurate
raster/audio timing and sampled DMC sound, all levels/characters/bosses/endings,
broader restart coverage and physical-console validation remain outstanding.
No complete project is ready for final user verification. No intermediate game
download is published here.

[Architecture and resumption guide](engineering-status.md). Historical reports
retain their dated scopes and test totals; they are not current completion scores.
