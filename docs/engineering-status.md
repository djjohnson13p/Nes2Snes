# Engineering status and resumption guide

## What this project actually is

The current product is a **trace-bounded native-execution compatibility bridge**
for the supplied MMC5 CV3 ROM. Ordinary compatible instructions run on the SNES
CPU; many incompatible memory and I/O instructions enter project-authored host
handlers. Raw original-data maps remain separate from patched execution maps.
This is not a recovered, fully understood original source tree, a universal
NES-to-SNES converter, or a completed native-engine rewrite.

## Why completion has been difficult

1. **The chosen implementation has ongoing translation costs.** Same-length
   patches preserve the game's addresses and simplify initial execution, but
   each intercepted operation can require register saves, address decoding,
   emulated hardware behavior and register restores. Faster SNES hardware does
   not make that overhead free. Small fast paths cannot by themselves establish
   a route to full speed.
2. **Timing is part of the game's behavior.** Mapper IRQs, PPU state and sound
   events cannot all be replaced by one similarly named SNES register. Current
   frame-scheduled IRQ and audio work remains approximate. The rendering and
   sound reports intentionally retain disagreements instead of calling them
   successful equivalence tests.
3. **Coverage is narrow compared with a whole game.** The current known trace,
   inferred instruction boundaries, initial benchmark and staircase route do
   not cover every character, stage, boss, death/restart and ending. Unknown
   execution deliberately faults rather than pretending that data is code.
4. **Regression success is not completion.** Some tests compare to independent
   NES execution; others compare to separately implemented models or the prior
   SNES renderer. Preserving the previous renderer's pixels does not prove it
   matches the original NES on every frame. Test counts must not be presented
   as percent-complete measurements.
5. **Development instrumentation had a measurable cost.** The playable builds
   also maintained per-access profiling counters. The counter-free checkpoint
   separates this bookkeeping from fault checks and actual audio/game counters.
   Its measured improvement is documented in `runtime-counters.md`.

## Conversation interruption versus project failure

These are separate phenomena. A failed ChatGPT response does not establish that
an assembler, emulator or ROM crashed. There is no access here to internal
ChatGPT generation logs, so no specific cause is asserted for the previous
"Thinking"/missing-response incidents. OpenAI's help article recommends a fresh
chat for long, unresponsive conversations, among other troubleshooting steps.
That is a recovery option, not a diagnosis:
https://help.openai.com/en/articles/7996703-troubleshooting-chatgpt-error-messages

During this continuation, one local test command reached its execution timeout.
It was rerun with monitored execution and recorded results. That observed command
limit must not be retroactively asserted to explain all earlier chat failures.
Source, test evidence and private reproduction inputs are saved at each completed
checkpoint. No claim of unattended development after a response ends is made.

## Next engineering priorities

- **Performance:** measure the remaining guest/bridge/render/audio frame costs;
  then choose a substantial hot subsystem for native replacement or larger-block
  translation. Preserve the counted build for diagnosis and the counter-free
  build for user-facing performance comparisons. Do not infer cycle percentages
  from instruction-frequency histograms.
- **Coverage:** extend a deterministic route through a first boss and verify it
  against the NES original. Retain failures, input scripts and trace provenance.
  Merely extending the trace is not equivalent to proving gameplay correctness.
- **Fidelity:** close the known raster transition discrepancies, complete DMC and
  remaining sound behavior, and improve scheduling accuracy. Do not hide known
  failures by loosening an independent comparison.
- **Completion:** a claim of a complete port requires broader route/character/
  boss/ending and restart checks, controlled speed measurements, documented
  audio/visual tolerances and eventual physical-console testing. "Perfect" is
  not implied by any finite fixture count.

## Resume without relying on conversation history

1. Read `README.md`, this file and the newest implementation report.
2. Verify the repository revision and local source before editing. Preserve the
   preceding known-good build; do not use an incomplete staged transfer.
3. Restore the pinned toolchain and run unit tests. The source-only repository
   needs the user's private original ROM and matching trace to rebuild CV3.
4. Change a bounded subsystem, add independent checks where available, and run
   fixed-input plus ordinary-controller regressions. Report exactly which oracle
   supplied each claim and whether a result is fresh or historical.
5. Publish source-only changes atomically, verify the resulting CI revision,
   and package private game-derived binaries separately. Report the saved
   checkpoint rather than silently leaving an incomplete multi-part transfer.

No copied commercial ROM, game assets or game-derived disassembly belongs in the
public source repository. Do not publish the private trace or playable binaries.

## Latest saved-source recovery

See `palette-reads.md` before resuming beyond this guide. It separates the
verified `a209aaf` baseline, the newly reconstructed palette-read correction,
and the missing 117-action Block 1-03 script. Do not infer that an old local
route, an unpublished experiment, or a source-staging commit passed acceptance.
Keep exact tested source hashes and private trace provenance with each new run.

## Latest continuation after the palette merge

Read `block103-entry.md` first for the newly authored 133-action clean-boot route,
explicit destination contract, recovered trace provenance and the post-merge
indirect-CI repair. The older missing 117-action route is still not recovered.
The new route proves Block 1-03 entry, not a boss clear or full-speed completion.

## Latest idle-state measurement

Read `idle-state-audit.md` for fault-aware route comparisons, the read-only observer,
its independent calibration, and the newly reproduced random-state divergence.
The local-only first-boss checkpoint reported in the conversation was not recovered
in that continuation. Do not infer its route or test results from the restored
Block 1-03 source. No runtime scheduling fix or new boss-clear claim is made.

## Latest original-cycle accounting

Read `guest-cycles.md` for the isolated native instruction-cost primitive, independent
NES timing measurements and separate observed interrupt accounting. This is not a
live scheduler or a recovered copy of the previously unpublished idle-budget work.
The production runtime remains unchanged and the private RNG comparison still fails.

## Latest sampled interrupt-entry component

Read `interrupt-boundary.md` for native IRQ/NMI decision and stack entry, the
fixture-only external-request harness, independent checks and remaining timing
limits. The preceding local-only block executor was not recovered. Production
runtime is unchanged; this is not a live scheduling or random-state correction.

## Latest composed execution prototype

Read `integrated-timeline.md` for the native instruction/cycle/interrupt integration,
dependent stream comparisons, exact clock-origin checks and actual fault guards.
The authored request policy is not physical pin sampling or the live CV3 scheduler.
The production game binary is unchanged and the explicit RNG test still fails.

## Latest host NMI context integration

Read `host-nmi.md` for real SNES vblank interruption of the composed prototype,
register/scratch preservation, nested entry, actual corruption controls, and the
bounded worker contract. This does not change the authored guest request policy
or install a physical-event scheduler in CV3. The RNG comparison remains failing.

## Latest guarded RAM timeline

Read `ram-timeline.md` for the opt-in full 2-KiB RAM profile, indexed/indirect
address resolution, original cycle costs, complete-memory captures and actual
before-access fault guards. Host NMI protection remains enabled in its tests.
Production CV3 scheduling is unchanged; ROM/I/O and physical timing remain open.

## Latest immutable cartridge-read profile

Read `rom-timeline.md` for the separate `nrom-32k` prototype profile, original-ROM
versus translated-code separation, guarded writes, independent comparisons and
preserved prior profiles. This is fixed NROM mapping, not MMC5 integration or a
production CV3 timing fix. No fresh commercial-game replay is claimed there.

## Latest bank-qualified MMC5 PRG profile

Read `mmc5-timeline.md` for modes 1/2/3 program-bank writes, bank-qualified code
selection, raw data/current vectors, independent mapping captures and guarded
unsupported operations. Mode 0 has a preserved reference disagreement. This
profile does not implement PRG RAM, CHR/ExRAM/mapper IRQ/audio or physical event
timing and is not enabled in production CV3. No new game replay is claimed.

## Latest single-chip cartridge-RAM profile

Read `mmc5-cartridge-ram.md` for the explicit 32-KiB PRG-RAM profile, aliasing,
protection-register semantics, exact initial/final cartridge snapshots, and
host-interrupted tests. Other RAM-board wiring and RAM code execution remain
unsupported. This does not change production CV3 or fix physical event timing.

## Latest CPU-only ExRAM and multiplier profile

Read `mmc5-cpu-io.md` for ExRAM modes 2/3, absolute multiplier-register execution,
read-only endpoint observation and real emulated host-NMI tests. External memories
are checked at the final recorded boundary, not every instruction. Rendering modes
0/1, PPU integration and physical event/stall timing remain unsupported. No new
CV3 replay or production timing correction is claimed by this checkpoint.

## Latest blanked PPU nametable profile

Read `ppu-blank.md` for the shared scroll/address latch, buffered CPU transfers,
CIRAM/fill routing, extended host-context protection and independent PPU snapshots.
Rendering, CHR/palettes/OAM, status timing and ExRAM nametables remain guarded.
An upper-bit fill-attribute reference disagreement is retained separately. This
profile is not installed in production CV3 and has no fresh commercial-game replay.

## Latest fixed-size CHR-ROM transfer profile

Read `chr-blank.md` for blanked set-A CHR reads, latched upper bits, original
CHR separation, independent physical-map snapshots and compact host context.
All four bank sizes are tested separately; live size changes and set B remain
guarded. This is not rendering or production CV3 integration. No new private
gameplay replay, RNG fix or speed improvement is claimed.
