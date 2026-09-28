# RAM sprite DMA with an independently observed elapsed clock

## Source and scope

This change starts from merged PR #24, `0398862d7f0d6c3052738e31a72d656152592905`,
tree `ba8052dc251b9cfd5592f82709ae8977546f4ac3`. The archived 385-file source
reconstructs that tree, and all 707 baseline tests passed locally without skips.
The new explicit profile is `mmc5-oam-dma-ram`. Earlier profiles, the production
CV3 builder, and production `native.s` remain unchanged.

This is a bounded DMA execution adapter, not a finished physical event scheduler.
It admits absolute `STA $4014` with internal-RAM source pages `$00..$1F`, while
rendering and DMC are disabled and guest interrupt requests are absent. RAM aliases
resolve before the copy. Other sources, read/modify/write triggers and other DMA
addressing modes are not silently approximated. The inherited palette, OAM,
nametable and rewrite-gated CHR behavior stays in use.

The 256 source bytes are actually read from evolving guest RAM and written to
sprite memory in order, with destination wrap and attribute-storage masking.
The guest CPU registers are not replaced by expected outputs. Copying does not
retire an extra guest instruction. Its 513/514-cycle stall is added separately;
the ordinary four cycles of the initiating STA are still charged by retirement.
DMA count, last stall and accumulated stall time are separately recorded.

## Phase synchronization, not arbitrary parity

DMA uses alternating GET and PUT bus phases. These must not be equated with a
universal even/odd CPU count at power-up. The authored original boot completes a
real DMA from the cleared page `$0700`, then runs a 20-cycle tail restoring the
declared entry A/P and I/O latch. The next program fetch is therefore a GET.
The native clock's zero is explicitly this synchronized entry, not an observed
reference timestamp. A source-program byte, seed or captured intermediate clock
is never copied from the reference into native execution.

A four-cycle STA starting on a GET writes on a PUT and needs alignment: 514 stall
cycles. Starting on a PUT instead produces a 513-cycle stall. The copy preserves
this phase relationship for later dependent instructions and repeated DMA.
Normal instruction costs and DMA delay therefore share one persistent clock.

The standalone synchronization helper occupies reserved original addresses
`$F200..F23F`. Code and data overlaps are rejected. The original PRG stored as data
in the SNES fixture includes the same authored boot and DMA instructions as the
NES input; the temporary same-length validator substitution is not published as
the original program. It changes only decoded STA $4014 instructions.

## Independent timing and endpoint evidence

A new read-only observer is installed around the pinned Nestopia CPU instruction
dispatch. It records the core's actual monotonic start/end timestamps, clock unit,
executed opcode and next PC for a bounded 31-instruction window. It performs no
emulated bus reads, clock changes or guest writes. Missing, overlapping, malformed
or discontinuous records reject acceptance. Its timestamp source is not the
project's cycle table or its predicted DMA stall.

Every original program also runs in a separately built unmodified Nestopia core.
CPU/PPU/mapper/OAM endpoints, frame and audio counts, image hashes and raw save
states must agree with the observed core. This checks observer noninterference.
The native elapsed clock and next PC then match the independent timing record at
**each instruction boundary**, including the DMA instruction and subsequent work.
The native DMA ledger must agree with the independently measured extra duration.

Full CPU RAM/registers, PPU state, palette, CIRAM, mapper state, ExRAM, OAM and CHR
registers still use independent **final** endpoints (5,457 bytes each). They are
not independent full-memory snapshots at every instruction. Native per-instruction
memory records separately establish host-interrupt noninterference. No external
bus transaction stream, within-DMA PPU event or physical-console equivalence is
claimed by these measurements.

## A deliberately restricted destination class

An unmodified Nestopia diagnostic finishes a DMA on an attribute slot and reads
the shared PPU latch. It returns `$A2`, while a separate original program doing a
CPU OAMDATA write of the same `$A6` value returns `$A6`. Both authored programs and
raw results are retained. This is a **reference-path disagreement**, not proof
of the physical hardware rule. The native adapter keeps the ordinary port's
full-byte latch behavior, and refuses DMA when initial OAMADDR modulo four is
three (so the final destination would be an attribute slot). It does not mask
CPU results or add an exception to make those endpoints pass.

This is a conservative admission policy, not a claim that hardware refuses those
transfers. All other 192 destination addresses are covered. The disagreement
remains outside passing totals and must be resolved before removing that guard.

## Protection, negative controls and coverage

MR, GT and PPU working state remain inside the existing host-NMI envelope. DMA
metadata and output records occupy guest-owned storage at `$7E:5B00` and
`$7E:6000`, outside the callback's write contract. Neither the protected stack
frame nor its watermark/canaries are enlarged or relaxed. A targeted interrupt
after source-byte acquisition but before its destination write checks the live
copy state. Additional tests interrupt the low-word clock addition with its carry
still live, and check refusal before copying when the clock cannot accommodate
the existing retirement overflow reserve.

The 268-program main matrix has 536 native endpoints. It covers all 32 RAM page
numbers including aliases, both DMA phases, all 192 admitted OAM addresses, and
repeated transfers. It is not the full Cartesian product. Actual wrong-result
executables test missing alignment, incorrect source mirroring, a short copy and
an incorrect accumulator width on return from capture. Each must finish before
its result is rejected; crashing is not sufficient. Seven unsupported source or
destination guards compare with independently executed original prefixes. A
separate clock-overflow case must stop before changing sprite memory or its DMA
ledger.

During development, returning from the new capture helper in 16-bit accumulator
mode made the inherited byte-clear overwrite PPUCTRL. An explicit width restore
fixed it; the executable width mutant now checks that regression. An initial
source-mirroring mutant used two DMAs, so the second copy erased the first error.
Its control now uses one transfer and observes the wrong data directly. Neither
failed development test is counted as a passing result.

## Reproduction and merge gate

```sh
python3 -m unittest discover -s tests -v
# Keep a plain pinned Nestopia build before adding the read-only hook.
python3 tools/instrument_nestopia_dma.py /path/to/nestopia
python3 tools/verify_oam_dma.py --nes-core /path/to/plain.so \
  --observed-core /path/to/timed.so --snes-core /path/to/snes9x.so --out build/oam-dma
python3 tools/verify_oam_dma.py --controls --nes-core /path/to/plain.so \
  --observed-core /path/to/timed.so --snes-core /path/to/snes9x.so --out build/oam-dma-controls
```

A limited smoke run reports `complete_matrix=false`. CI requires the full new
matrix and controls, retained rewritten-CHR matrix/controls, and runtime-safety
suite. Exact tested source, raw observations, timing records, authored inputs,
assembly, failure controls and the unresolved diagnostic are archived. Verify
actual completed reports and their revision/tree before requesting the merge.

No fresh commercial-game replay, corrected CV3 random-state result, rendering,
speed improvement, boss clear or historical-route recovery is claimed. Remaining
work includes PPU event/status timing, DMC interleaving, other DMA source regions,
rendering-dependent behavior and production integration. Commercial ROMs, game
assets and private game-derived traces/binaries are not included.

Primary references: [NESdev DMA phase and halt behavior](https://www.nesdev.org/wiki/DMA),
[PPU sprite memory](https://www.nesdev.org/wiki/PPU_OAM), and pinned
[Nestopia CPU](https://github.com/libretro/nestopia/blob/8f00f500912a847062de432e38765c7285483e62/source/core/NstCpu.cpp)
and [PPU](https://github.com/libretro/nestopia/blob/8f00f500912a847062de432e38765c7285483e62/source/core/NstPpu.cpp)
implementations. Hardware documentation and emulator execution are distinct forms
of evidence; neither is labeled as a new physical-console measurement.

The timing observer records logical CPU addresses. Overlapping executable CPU
address ranges in different PRG banks are refused by this profile rather than
being assigned an inferred physical-bank identity. This guard does not change
the older bank-qualified execution profiles.
