# Verified status — 2026-09-26

## Current: guarded paired-route timing and outdoor/respawn coverage

The route test now distinguishes full NMI updates from skipped interrupt entries
and aligns startup consistently. The opt-in guarded mode recognizes the original
fixed-bank guard; it does not use a manual timing offset or edit guest state.
The old legacy mode remains available for historical reproduction.

The 31-step approach plus 84 named actions completes on both NES and SNES with
all five selected area/camera/player fields equal at every endpoint: 420 field
values, 756 bytes, zero differences. The route includes an outdoor death/respawn;
it does not clear a boss. Observed instruction coverage increased from 10,763 to
11,553 while keeping the unknown-code safety guard enabled.

272 unit tests pass. A separate authored guard fixture verifies eight snapshots
and 16,384 NES RAM bytes against an unmodified reference. The original game's
instrumented NES captures are also reproduced by unmodified NES execution:
84 images, 4,816,896 pixels and 172,032 RAM bytes. Those pixel counts are NOT
NES-versus-SNES pixel equivalence. Public CI uses procedural inputs only.

See [complete method and limitations](route-clock.md) and
[machine-readable evidence](route-clock-verification.json).

## Current native runtime and historical speed results

The runtime retains the [native controller replacement](native-controller.md),
[counter-free profiling option](runtime-counters.md),
[OAM destination correction](oam-offsets.md), and opt-in
[background DMA/fill-cache correction](nametable-dma.md).
The latest merged indirect-X shortcut is also optional and does not accelerate
the supplied observed CV3 path. This validation checkpoint changes no native
runtime handler and claims no new speed result.

The prior fixed-input walking benchmark was 149 SNES display frames for 120 game
updates with native controller polling. That is a historical benchmark, not a
measurement of the new 84-checkpoint route. The original 57-action staircase
comparison alone did not establish all-frame or whole-game fidelity.

## Completion status

The project remains a trace-bounded native-execution compatibility bridge, not
a universal converter or completed native engine rewrite. Full speed, accurate
raster/audio timing and sampled DMC sound, all levels/characters/bosses/endings,
broader restart coverage and physical-console validation remain outstanding.
No complete project is ready for final user verification. No intermediate game
download is published here.

[Architecture and resumption guide](engineering-status.md). Historical reports
retain their dated scopes and test totals; they are not current completion scores.
