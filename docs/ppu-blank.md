# Blanked PPU nametable transfers — 2026-09-27

## Baseline and admission boundary

The user merged PR #17 as `1b3213a0d4fdbaaed35ef560f7dbc87d75d21142`,
with tree `0d2a44a7dac93d859d168c3e87608b1d4f1a0f94`. The restored
328-file source tree matches exactly, and a fresh baseline run passed 551 tests.
The new explicit `mmc5-ppu-blank` profile extends the preceding CPU ExRAM and
multiplier profile. It is not installed in `native.s` or `build_native.py`.

This checkpoint executes **CPU-side PPU register and nametable transfers while
rendering and PPU-generated NMI are disabled**. It is not graphics rendering.
Only absolute LDA/STA PPU-port accesses are added. Unsupported CPU addressing
forms, PPUSTATUS reads, OAM, CHR/palette accesses, ExRAM-as-nametable, enabling
rendering, and setting PPUCTRL's NMI or master/slave bits remain refused. These
are explicit profile guards, not assertions that original hardware faults.

## Implemented state and memory behavior

PPUCTRL updates the control latch and nametable bits of the temporary address.
PPUSCROLL and PPUADDR share one write phase; mixed writes preserve the documented
coarse/fine scroll fields, fine-X latch and temporary/current address distinction.
The high PPUADDR write is masked to six bits. The second address write copies
the temporary address to the current address. Port aliases are decoded every
eight bytes through CPU address `$3FFF`.

Reads of admitted write-only PPU registers return the current PPU I/O latch.
Writes to PPUSTATUS update that latch only; status reads remain unsupported
because a physical PPU/vblank deadline model is not present. This short-window
contract does not model analog I/O-latch decay or PPU power-up write inhibition.

PPUDATA reads return the prior delayed buffer, refill it from the newly addressed
nametable byte, update the I/O latch and increment the current address exactly
once. Writes update the target and latch, preserve the delayed-read buffer, and
also increment exactly once. PPUCTRL selects +1 or +32. The current address keeps
15 bits while PPU memory decoding uses 14 bits. Only `$2000..$3EFF` is admitted;
CHR and palette paths are not silently sent through the nametable implementation.

MMC5 `$5105` selects CIRAM page 0, page 1 or fill mode independently for each
nametable quadrant. The `$3000..$3EFF` nametable mirror uses the same selection.
`$5106` supplies fill tiles; admitted `$5107` values 0..3 supply the repeated
2-bit attribute. Writes to fill-selected storage are ignored, but their PPU latch
and increment effects still occur. Selection 2 (ExRAM nametable) is refused.

Original instructions update persistent native state. Neither reference register
values nor expected intermediate memory/buffers are injected into the executor.
The existing original-instruction cycle accountant, sampled guest requests and
bank-qualified program execution remain in use.

## Protected context and independent observation

The 16-byte native PPU area at `$1C20..$1C2F` contains 13 logical state bytes plus
three scratch bytes. This profile expands the host-NMI capture-area snapshot from
32 to 48 bytes and expands the intentionally destructive worker accordingly.
Each nested interrupt saves and restores its own state. The reserved stack
watermark and canaries remain checked by the existing host suite; their limits
are not loosened. Guest CIRAM is separate at `$7E:4800..4FFF`; the bounded host
worker may not modify guest memory.

A separate 16-byte PPU record is saved at every instruction endpoint. It contains
13 logical bytes and three zero padding bytes, not the scratch contents. These
records are stored at `$7E:5000` separately from the existing 2,080-byte CPU
records, so the previous output-bank capacity does not silently overflow.

The original NES boot initializes CIRAM through actual PPU writes, initializes
the latches and read buffer, and only then begins the compared instruction window.
The native side uses the same declared starting inputs. This is a post-boot
execution contract, not equivalence of the machines' power-up timing. The original
helper occupies a separately reserved `$F000..F1FF` region in the last PRG bank;
code/data overlap is rejected before building.

The additional NES observer reads actual original PPU state and actual mapper
nametable/fill state. It does not replace original PPU/mapper read or write
handlers. Current/temporary addresses are observed as their hardware-width
15-bit values. The inherited CPU request harness remains an authored
**after-instruction stimulus**, not physical interrupt sampling.

Every endpoint compares full CPU RAM and the 32-byte CPU/timing/mapper record,
plus its separate PPU state record. **All 2 KiB of CIRAM, 1 KiB of ExRAM and
32 KiB of cartridge RAM are checked at the final recorded endpoint, not at every
instruction.** Compiled C99 tests prove initial/final snapshots are frozen even
if original execution continues afterward. Incomplete, malformed, changed or
whitespace-shortened captures cannot pass.

## Tests and retained evidence

The matrix contains 184 authored programs: all 81 combinations of the admitted
nametable sources, +1/+32 transfers across selected boundaries and mirrors, fill
tile/attribute cases, mixed scroll/address-latch sequences, explicit read-buffer
preservation and one sampled guest-NMI sequence. Each runs normally and under
free-running host vblank interrupts; three selected programs additionally run
under cost, partial-clock, capture and nested-worker interruption stress.

Three deliberately broken executables test the actual acceptance checks:
unbuffered reads, incorrect CIRAM aliasing, and incorrectly permitted fill writes.
They must reach their completion markers and then fail the result comparison;
a crash alone is not accepted as evidence that the comparison detects the defect.
Eleven actual access guards are compared to independently executed original
prefixes. They must leave prior CPU/PPU logical state and all external memories
unchanged. Scratch bytes are not falsely described as immutable guest registers.

Fresh local execution passes **380 scenarios / 11,780 dependent instruction
boundaries**: 24,502,400 CPU-state bytes and 188,480 PPU-record bytes match. Final
snapshots additionally compare 778,240 CIRAM bytes, 389,120 ExRAM bytes and
12,451,840 cartridge-RAM bytes. The 196 host-enabled scenarios witness 7,186
emulated SNES vblank interrupts. All three completed-but-wrong executables and
all eleven guards are rejected as intended. The 183 no-request plans also match
the separately built unmodified NES core's final CPU RAM/image hashes and frame
counts. The full unit/assembler suite passes **575 tests with zero skips**, both
in the working source and a clean source copy.

Core hashes, retained-suite results and exact-source reproduction results are in
`ppu-blank-verification.json`. Repeated runs do not
increase distinct coverage counts. Eighteen representative earlier-profile builds
(three per existing profile) are compared to separately restored baseline builds;
this is not a claim to rebuild every historical fixture.

## Preserved fill-attribute reference disagreement

The pinned original FCEUmm core does not mask upper bits of `$5107` before
expanding the fill attribute. An authored write of 4 returns `$54` from the
attribute byte, rather than the documented low-two-bit result `$00`. The observed
and unmodified reference cores agree on execution outputs. The separate diagnostic
retains this as **a non-passing reference-accuracy result**, not an accepted
mapping result. Native upper-bit writes are refused before logical mutation;
the implementation does not copy the disagreement. The existing mode-0 PRG
mapping disagreement remains separate and is not corrected here.

## Production boundary and resumption

No fresh commercial-game replay was performed. Production `snes/src/native.s`
and `tools/build_native.py` remain unchanged. Earlier CV3 route evidence is
historical; the known RNG discrepancy is not fixed. No pixel-rendering improvement,
physical-console result, speedup, first-boss clear or recovered lost route is claimed.

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_ppu_blank.py /path/to/pinned/fceumm
# Rebuild the observed core while retaining an independently built plain copy.
python3 tools/verify_ppu_blank.py \
  --nes-plain /path/to/plain-fceumm.so \
  --nes-probe /path/to/ppu-observed-fceumm.so \
  --snes-core /path/to/plain-snes9x.so --out build/ppu-blank
```

The new workflow runs the independent PPU matrix, reference disagreement,
retained CPU-I/O matrix and runtime safety, then archives exact tested source,
authored inputs, generated code, captures and negative controls. Its actual
candidate revision and final status must be checked before asking for a merge.
No commercial ROM, private game trace, screenshot or game-derived executable is
included. Next add independently tested CHR/PPU data and rendering-dependent
mapping behavior, then physical event/stall timing and efficient production
integration. Blanked nametable access alone does not supply those pieces.

References: [PPU registers](https://www.nesdev.org/wiki/PPU_registers),
[PPU scrolling](https://www.nesdev.org/wiki/PPU_scrolling),
[MMC5 nametable/fill registers](https://www.nesdev.org/wiki/MMC5), and the pinned
[FCEUmm PPU](https://github.com/libretro/libretro-fceumm/blob/236ccdfc911e84c60fea6b9d0699c2d440a8de14/src/ppu.c)
and [MMC5 implementation](https://github.com/libretro/libretro-fceumm/blob/236ccdfc911e84c60fea6b9d0699c2d440a8de14/src/boards/mmc5.c).
