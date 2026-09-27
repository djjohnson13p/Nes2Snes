# Dependent native execution and one interrupt timeline

## Base and actual integration

PR #10 was merged as `3d93f14d3c96b9865c49e4aeae79829e46e854af`, with
source tree `03c57d5a42b8adaab1a005194faffea3524108d3`. That exact signed Git
object and all source files were restored from the public commit and checked CI
archive. The local Git history is shallow at that revision, not a full clone.
All 402 baseline tests passed before these changes.

The new prototype **executes instructions, advances a persistent original-cycle
clock, resolves a stream of interrupt requests, executes the selected handler,
and returns to the interrupted program**. This connects the previously separate
instruction-cost and interrupt-entry components in a running native SNES program.
There is no per-step replay of expected register, stack, seed or timestamp values.

`snes/src/guest_timeline.inc` calls the existing `GuestInstructionCycles` and
`GuestInterruptBoundary` routines. A bounded static translator in
`tools/timeline_program.py` supplies actual native instruction execution and
software NES-stack operations, including JSR/RTS and IRQ/NMI return through RTI.
Every control target is checked against supplied original instruction entries;
an unknown dynamic target faults instead of executing unclassified bytes.

**This is a procedural integration prototype, not the live CV3 scheduler.**
`native.s` and `build_native.py` remain unchanged and do not include this engine.
It is new work, not a recovered copy of the previously blocked local-only block
executor or the missing 117/298-action gameplay routes.

## Inputs, execution and event contract

Each case contains one immutable authored program, its explicit instruction
entries, initial RAM/register inputs, vector addresses and a sorted request
schedule. Both machines retain their own evolving state for all 112 instructions.
The SNES inputs are generated from those declarations, **not** from captured
NES after-states. The original NES boot sequence independently establishes the
declared initial state; the verifier checks all initial bytes before comparing.

The prototype accepts ordinary unindexed RAM below `$0200`, immediate/register
operations, conditional branches, direct jumps and explicitly implemented
control/stack operations. Indexed/indirect addressing, I/O, BRK, undocumented
opcodes, overlapping or missing instruction entries and unobserved static targets
are rejected. This is intentionally not an all-opcode or arbitrary-ROM translator.
Guest decimal is retained in the saved status but disabled during native ALU
execution, matching the already tested NES binary-arithmetic behavior.

The timeline charges each original instruction's cost, applies **every** declared
request whose time is now due, and charges an accepted interrupt's seven-cycle
entry separately. An asserted IRQ remains asserted until a scheduled deassertion;
a serviced NMI latch is consumed. Handlers and subsequent RTI returns execute as
part of the same stream; they are not substituted with expected results.

Requests in these tests are applied **after completed instructions**. An event
whose deadline falls during interrupt entry is handled after the next instruction,
as specified by this test contract. This is not a physical pin detector or a
PPU/mapper scheduling model. Branch polling phases, late edges, vector hijacking,
DMA/DMC stalls and real PPU deadlines remain outside this acceptance claim.

The prototype owns the guest zero-page/stack and its GC/GI/GT scratch contexts;
its native host stack is separate. Host NMI is disabled in the authored test ROM.
This does not prove safe interruption of the prototype by production host NMI.
The 32-bit clock has a conservative near-overflow guard reserving the maximum
instruction-plus-entry cost. A rejected retirement does not roll back an already
executed instruction; the whole run fails acceptance rather than being resumed.

## Independent evidence

`timeline_probe.h` is a **fixture-only request-stimulus harness**, not a read-only
gameplay observer. It asserts the same declared requests through existing FCEUmm
APIs after original instructions complete. The original CPU execution, cycle
charging, interrupt selection, stack writes and return implementation are not
replaced. Records capture actual relative core time, PC, A/X/Y/P/S, requests,
event cursor, original opcode, entry decision and the complete 512-byte writable
guest region. The request harness is never used for the private game regression.

The final local suite contains **427 passing unit/assembler tests**, including
25 new tests, real native assembly, compiled C99 harness checks, malformed-input
and incomplete/fault-bearing evidence rejection. The emulator matrix passes:

- **18 dependent scenarios / 2,016 completed instruction boundaries**. Three
  program placements cross conditional-branch page boundaries differently, each
  running six request/initial-state scenarios. Across the measured executions,
  33 distinct original opcode bytes execute, including 12 taken branch page
  crossings, **18 IRQ entries and 33 NMI entries**.
- Exact comparison of **1,096,704 bytes**, comprising 1,032,192 guest-RAM bytes
  and 64,512 timeline/register/metadata bytes. There is no mismatch tolerance,
  coordinate-only acceptance, supplied intermediate seed, or expected PC table.
- All three no-request cases also match the unmodified NES core's full final RAM
  and frame-image hashes, video callback counts and audio-frame counts.
- Two additional declared clock-origin tests verify **224 dependent boundaries**
  across low-word carry, including a nonzero high word. Comparison rebases only
  the declared clock origin and remains exact on every other byte. These are
  counter-arithmetic checks, not extra physical-timing scenarios.
- Actual native mutation controls reject a missing interrupt-entry charge and
  processing only one overdue event. Actual native fault tests reject an unknown
  PC and a near-overflow clock. Failed outputs cannot become passing comparisons,
  even with matching bytes or falsey fault payloads. Every declared event must be
  exercised before a scenario is accepted.

The normal windows cover 347 to 400 original cycles after the defined initial
state. These are small integration programs, not full-game or reset-to-power-on
cycle coverage. Per-instruction dispatch and full-state capture are intentionally
expensive; this checkpoint is not a demonstrated speed solution.

The first real unknown-PC test found a new assembler-width bug in the prototype's
failure-marker path: the fault status was set, but the marker was not written.
That run was rejected. An explicit accumulator-width directive fixes the path;
both actual native fault tests now report the expected marker and stop position.
An earlier mutation test did not exercise multiple simultaneously overdue events;
the final control uses the burst scenario and must demonstrably fail. Development
failures are not included in passing totals.

All **32 retained runtime-safety configurations** also pass: 4,224 records /
16,896 register-and-flag bytes and 1,024 OAM bytes, with unknown-code guards and
existing audio stress retained. These remain scoped compatibility tests, not
cycle-perfect audio or universal hardware-equivalence claims.

## Private CV3 regression and unresolved discrepancy

The original ROM was restored from the user's existing private checkpoint and its
complete recorded SHA-256 verified before use. Fresh guarded 84-action then
133-action original-NES runs recreate the 12,359-site trace. The game binary remains
`0f4ac141190f4b7e0c3bbc1a691938c21872b133560e33bb4256f57c5b66f0ac`.

Fresh clean-boot NES/SNES execution matches all **665 selected fields / 1,197 bytes**
at the 133 endpoints, plus **133 separately counted player-health bytes**. All
three Block 1-03 destination checks pass. Unmodified NES replay also reproduces
the recording. These private runs use the ordinary read-only tracing core, never
the request-stimulus core. Their results are local, not public CI game coverage.

The explicit random-byte comparison still **fails at 131 endpoints**. The new
engine is not installed in CV3; no forced seed, rewritten enemy spawn, loosened
comparison, game speed improvement or new boss clear is claimed.

## Reproduction, publication and next work

```sh
python3 -m unittest discover -s tests -v
# Keep a plain build of pinned FCEUmm, then install only this test harness.
python3 tools/instrument_timeline_probe.py /path/to/fceumm
# Rebuild the fixture-only core separately.
python3 tools/verify_timeline.py --nes-plain /path/to/plain.so \
  --nes-probe /path/to/timeline-stimulus.so --snes-core /path/to/snes9x.so \
  --out build/timeline
```

The workflow uses only authored programs, records the exact tested source commit,
and retains the full independent/native captures and generated assembly, including
mutation and fault results. An existing passing summary is removed when a new run
starts. The actual new candidate's CI must pass before requesting the user's merge;
local execution is not substituted for that CI result.

Next replace the authored after-instruction request policy with independently
verified physical-event and stall models, then integrate a protected live guest
context behind an explicit experimental gate. Mapping and I/O transitions need
coverage before broadening the translator. Keep fast block execution as a separate
performance task: calling a general cost helper and copying state on every
instruction is not a route to full speed by itself. No private original ROM,
trace, commercial image, disassembly or game-derived binary belongs in this PR.
