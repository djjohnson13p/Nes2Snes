# Engineering status and resumption guide

## Product and production boundary

Nes2Snes remains a trace-bounded native-execution compatibility bridge for the
supplied MMC5 CV3 ROM, not a completed native engine or universal converter.
Unknown execution faults instead of treating unobserved data as code. The
production builder is `tools/build_native.py`, with `snes/src/native.s` and its
includes. Recent `*_timeline`/port adapters are separate procedural prototypes;
passing their tests does not mean that the production game uses them.

The last published base used for the current continuation is merged PR #21,
`a9a7408e95ff58e1da9615668dd76a9abc360ace`. Its tree is
`039fc32dfd8fac8f320eba6db88c543f71ed6ecf`. Always read live repository/PR status
before editing; this recorded base is not a promise that main never advances.

## Current source checkpoint, subject to its merge gate

Read [blanked OAM ports](oam-ports.md) for the new `mmc5-oam-blank` adapter,
independent raw sprite-memory/address checks, composed palette/CHR behavior and
unchanged host-stack limits. The full matrix, actual mutants and guards must
finish on the exact source revision before requesting the user's merge. A draft
PR, partial report or completed source upload is not acceptance evidence.

The preceding layers are [nametable readback](nametable-readback.md),
[palette transfers](palette-timeline.md), [CHR transfers](chr-blank.md),
[PPU nametable transfers](ppu-blank.md), [CPU-side ExRAM](mmc5-cpu-io.md),
[cartridge RAM](mmc5-cartridge-ram.md) and [MMC5 PRG mapping](mmc5-timeline.md).
Their test counts and source identities belong to their own checkpoints.

The new OAM work started from the published base. Earlier local-only OAM and
CHR-set workspaces were absent from the current mounted workspace and were not
used. Do not claim their source, tests or complete recovery from conversation
summaries or unreferenced partial Git trees.

## Gameplay evidence is narrower than the new component tests

The saved [133-action route](block103-entry.md) establishes Block 1-03 entry,
not a first-boss clear. Keep the 84-action death/respawn route too. The exact
historical 117-action script and later unpublished boss-route source are not
recovered. The [idle-state audit](idle-state-audit.md) records the unresolved
random-state timing divergence. No component-test count is a percent-complete
measure, speed gain or proof of whole-game correctness.

The new OAM checkpoint does not change the production game builder/runtime and
does not claim a new commercial-game replay. Distinguish independent NES final
endpoints, independent instruction comparisons, SNES host/non-host comparisons,
old-build identity checks, and inspection of archived results. They prove
different things; none can silently substitute for another.

## Resume and verification protocol

1. Read this guide, the newest implementation report, current main and open PRs.
   Check the local tree and all pending edits. Preserve known-good evidence.
2. Restore the exact source and pinned toolchain. Hash-check the source archive
   and rebuild its Git tree. Run the unit/assembler suite before new edits.
3. Implement one bounded change with independent comparisons and real negative
   controls. Preserve unknown-code guards, stack bounds and reference failures.
4. For private gameplay work, restore the authorized original ROM and exact
   trace provenance. Fresh gameplay requires an actual replay, not an old report.
5. Publish a complete source-only commit and check CI's tested revision/tree.
   A PR merge-test SHA can differ from its branch head; verify the actual tree.
   Clearly request the user's merge only after the applicable checks pass.
6. Save a resumption record distinguishing published commits, local experiments,
   finished executions and unfinished tests. Local archives are not remote backups.

No copied commercial ROM, extracted assets, commercial screenshots, game-derived
executable or reconstructed commercial game source belongs in the public repo.
Authored procedural test inputs and independent result records may be archived.
Do not publish private game traces. Do not hand work to Codex or claim unattended
development after a response ends.

## Remaining integration work

Independently verified PPU status/event timing, DMA/DMC stalls, rendering-dependent
PPU/mapper behavior, live CHR selection and an efficient production execution
path remain unfinished. Do not replace missing timing with expected seeds or
silently broaden a profile to emulate an unresolved reference discrepancy.
A complete-port claim also requires broader stages/characters/bosses/endings,
death/restart coverage, controlled speed measurements, explicit audio/visual
accuracy criteria and eventual physical-console testing.

The previous chronological guide is preserved unchanged in
[engineering-status-history.md](engineering-status-history.md). It supplies
historical context, not current acceptance totals.

## Latest blanked A/B CHR transfer adapter

Read [CHR set transfers](chr-set-transfers.md) for the explicit forced-blank,
8x16-sprite profile composed with OAM/palette transfers. It retains both bank
sets and the last-write selection under host interruption without enlarging the
protected stack frame. This is newly authored from merged PR #22, not recovery
of a previous local-only CHR experiment. Live size changes and rendering remain
refused. Check the exact candidate's completed reports and CI before merge.
Production CV3 is unchanged and has no fresh gameplay/timing acceptance here.
