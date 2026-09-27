# CPU-only MMC5 ExRAM and multiplier — 2026-09-27

## Baseline and scope

PR #16 was merged as `85105e09229783cb4535f36db2053f15db42d6d0`, with
source tree `145b399839485d0de3456cffda7a699d60d85fa3`. The source restored
from its verified CI artifact reconstructs that tree exactly. A fresh baseline
run passed 533 tests. This checkpoint adds the explicit `mmc5-cpu-io` profile;
it does not replace the previous cartridge-RAM profile or production CV3 runtime.

The new profile executes CPU accesses to MMC5 ExRAM in modes 2 and 3, and absolute
LDA/STA operations on multiplier registers `$5205/$5206`. Original instructions
operate on persistent native state, then use the existing cycle accountant and
sampled interrupt path. No expected intermediate memory, product, seed, mode,
register or timestamp is supplied to execution.

## ExRAM behavior

`$5C00..$5FFF` resolves to a separate 1-KiB guest allocation at SNES
`$7E:4000..43FF`, not a mirror of internal RAM or PRG RAM. The low two bits of
`$5104` select the mode. Mode 2 permits CPU reads/writes; mode 3 permits reads
but ignores writes. Read/modify/write instructions still update flags and
retire their normal original instruction costs when the final write is ignored.
Changing modes preserves contents. PRG-RAM write-protection registers do not
control ExRAM.

All 61 admitted external-memory opcode/addressing forms are exercised in both
writable and read-only modes. Indexed/indirect operations retain the actual
original pointer and registers. Supported crossings from `$5FFF` to `$6000`
resolve to the appropriate separate memories. An ExRAM-backed indirect jump uses
the NMOS within-page pointer wrap, but its resulting code target must still be a
declared original ROM bank/PC entry.

Rendering-dependent ExRAM modes 0/1 remain refused before mode mutation. A
preliminary indexed address in an unsupported register region is also refused,
even if its final address would be ExRAM or a multiplier register. These are
explicit prototype limits, not claims that original hardware faults there.
Dummy bus accesses, open bus and rendering-time restrictions are not modeled.

## Multiplier and protected context

Writing either multiplier operand recomputes the unsigned 8-by-8-bit product;
reads return the low or high result byte. The native shift/add routine uses
binary arithmetic regardless of the guest decimal flag and does not share SNES
hardware-multiply registers with asynchronous host code. The guest flag image
and original instruction cost remain under the existing execution contract.
Only absolute LDA/STA register accesses are admitted in this checkpoint.

Mode and operands occupy GT+24..26, and product occupies GT+28..29, inside the
existing host-NMI snapshot. Address/arithmetic scratch uses the already protected
resolver workspace. Guest ExRAM and PRG RAM are not host scratch; the bounded
host worker must not change them. Actual emulated SNES vblank tests exercise
free-running execution and the existing cost, clock, capture and nested-worker
stress sites. This does not claim interruption at every multiplier instruction.

## Independent observation and acceptance

The original NES program initializes ExRAM and multiplier operands through real
mapper-register and memory writes. The added observer only reads actual original
mapper state and copies ExRAM at the first/final recorded boundaries; original
CPU, mapper and multiplier implementations remain unchanged. The inherited
request harness still supplies the declared after-instruction stimulus. It is
not a physical NES event or interrupt-sampling model.

Each instruction endpoint compares all 2 KiB of CPU RAM and 32 metadata bytes,
including the observed ExRAM mode and multiplier operands. All 1 KiB of ExRAM
and all 32 KiB of cartridge RAM are compared separately at the final recorded
endpoint, **not at every instruction**. A compiled observer test mutates memory
after the window and proves that the saved initial/final snapshots remain intact.
Malformed, incomplete, whitespace-shortened and changed snapshots are rejected.

The multiplier fixtures contain 320 authored operand pairs. Every byte value
occurs in each operand position; edge combinations and immediate read-after-write
cases are included. This is **not exhaustive testing of all 65,536 pairs**.
Three executable mutants must finish and still be rejected for wrong results:
ignored read-only protection, incorrect ExRAM aliasing and a stale product.
Unsupported-mode and indexed-register guards must preserve the prior CPU state,
mapper state and both complete external memories.

Fresh local acceptance passes **551 unit/assembler tests** and **251 authored
plans / 514 native scenarios / 15,934 dependent instruction boundaries**. Those
compare **33,142,720 internal-state bytes**, **526,336 final ExRAM bytes**, and
**16,842,752 final cartridge-RAM bytes**, with zero mismatches. The 263 host-enabled
scenarios witness 9,324 emulated SNES vblank NMIs. All 250 no-request plans also
match a separately built unmodified NES core's CPU-RAM/image hashes and frame
counts. Three executable mutants and six guard scenarios are rejected as intended.

The full retained cartridge-RAM matrix passes all 404 scenarios; all 32 retained
runtime-safety configurations pass. Fifteen representative builds across the five
older profiles are byte-identical to separate baseline builds. All 551 tests
also pass from a clean source tree; three representative independent/native
emulator replays, including nested interruption, reproduce complete captures and
binary bytes. This is not a second complete matrix or all-old-fixture build sweep.
The final comparison code revalidates all 514 saved scenarios, mutants and guards.

Fresh completed measurements are recorded in `mmc5-cpu-io-verification.json`.
Unit/assembler tests, the complete new execution matrix, the retained cartridge
RAM matrix and runtime safety are separate checks. Selected old-profile binary
identity checks and clean-source replay samples are not extra distinct coverage.
GitHub CI results must be verified against the actual published candidate.

## Development corrections and unchanged claims

The first NES smoke capture was incomplete because the existing 16-frame sampler
allowance ended before the expanded boot finished initializing both external
memories. The new profile uses a 20-frame observation allowance on both plain
and observed cores; older profiles are unchanged. Only the fixed recorded
instruction window is compared, and its original-cycle origin is unchanged.
This is a capture-duration correction, not a game-timing fix or an overclock.
A pointer-read helper was also kept separate from operand-value storage so that
the high-byte fetch cannot overwrite the saved low byte; an actual ExRAM indirect
jump fixture exercises that distinction.

Production `snes/src/native.s` and `tools/build_native.py` are unchanged.
**No new commercial-game replay was performed.** Earlier CV3 route and RNG
results remain historical; the known RNG mismatch is not corrected here. No
rendering improvement, gameplay speedup, boss clear or recovered missing route
is claimed. PRG mode 0 retains its earlier reference disagreement and remains
outside the admitted mapping profile.

## Reproduction and next work

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_cpu_io_timeline.py /path/to/pinned/fceumm
# Rebuild the observed core, retaining a separately built unmodified core.
python3 tools/verify_cpu_io_timeline.py \
  --nes-plain /path/to/plain-fceumm.so \
  --nes-probe /path/to/cpu-io-fceumm.so \
  --snes-core /path/to/snes9x_libretro.so --out build/cpu-io
```

The workflow archives exact source, authored programs, generated assembly,
original authored PRG, complete captures, external-memory snapshots, mutants and
guards. No commercial ROM, game trace, game image or game-derived executable is
published. Next connect the remaining PPU/CHR/nametable and rendering-dependent
ExRAM state, then independently verified event/stall timing, before enabling an
efficient production path. The diagnostic dispatcher is not a demonstrated
full-speed solution.

Hardware reference: [NESdev MMC5](https://www.nesdev.org/wiki/MMC5), especially
CPU ExRAM modes and the multiplier. Independent execution uses pinned FCEUmm
`236ccdfc911e84c60fea6b9d0699c2d440a8de14` and unmodified Snes9x
`fae2fea08f74180759ef540ee94259213f503480`, as recorded in the workflow.
