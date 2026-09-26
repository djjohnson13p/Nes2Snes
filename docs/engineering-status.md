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
