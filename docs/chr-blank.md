# Banked CHR-ROM transfers with rendering disabled — 2026-09-27

## Provenance and execution boundary

The user merged PR #18 as `57f8976ea7e847970ea3686783c138861660a93f`,
source tree `7db4bf8b97fac12ffd2f12762022e74cfed3467f`. Its 338-file
CI source archive was restored exactly and all 575 baseline tests passed.
This is a new continuation, not recovery of an older unpublished experiment.

The explicit `mmc5-chr-blank` profile executes CPU PPUDATA reads from original
banked CHR ROM. It supports set A, with one CHR bank size selected at boot:
1, 2, 4 or 8 KiB. Cartridge CHR sizes are power-of-two values from 8 KiB to
1 MiB. Rendering, PPU-generated NMI and 8x16 sprite mode stay disabled. This
is a memory-transfer implementation, not a visible graphics renderer.

Original `STA abs` writes to `$5120..$5127` latch the current low two bits of
`$5130` with their bank byte. Changing `$5130` alone does not retroactively
remap those registers. Same-mode `$5101` writes ignore upper bits; a write
that changes the active size is refused. Set-B writes are also refused.
These are deliberate profile guards, not assertions that original hardware
faults. The register snapshots use logical bank indices, not a claim that
they reproduce the physical MMC5 register encoding.

## Mapping and buffering

The immutable authored CHR image follows the separate original PRG image in
the SNES cartridge. Its starting bank depends on PRG size; it is not hardcoded
to one layout. Every new fixture verifies exact original CHR bytes in both
NES and SNES inputs. Tests include 32-KiB, 256-KiB and 1-MiB PRG layouts.
Native reads resolve the current bank to those original bytes, never translated
execution code or expected results supplied by an oracle.

The existing delayed PPUDATA buffer, I/O latch, +1/+32 increment and nametable
path remain active. Pattern reads refill the buffer; the caller receives its
preceding value. CHR-ROM writes are ignored while retaining their PPU latch
and address-increment effects. Transfers exercise crossings between pattern
banks and into nametable space, mirrored ports, high-bit latching and small-ROM
address-line wrapping. No dummy transaction or external bus-cycle claim is made.

## Independent observations and sampling

The NES boot uses original mapper and PPU writes to initialize its own state.
The added observer reads actual FCEUmm CHR register values and mapped `VPage`
pointers into the original CHR image. It does not replace mapper/PPU behavior,
calculate the reference map using the native bank formula, or inject expected
intermediate state. The inherited fixture request harness still applies
requests after completed instructions; it is not physical NES pin timing.

Every endpoint compares 2 KiB of CPU RAM plus 32 CPU/timing/mapper bytes,
16 PPU-state bytes, and 48 CHR-state bytes. The CHR record contains mode,
upper latch, eight logical register indices, eight actual mapped 1-KiB slots
and zero padding. Full CIRAM, ExRAM and cartridge RAM are compared separately
at the final recorded endpoint, not at every instruction. Compiled observer
tests verify snapshot freezing and rejection of invalid mapped pointers.

## Completed local results

The final suite passes **595 unit/assembler tests, zero skipped**. The expanded
execution matrix passes **109 programs / 230 native scenarios / 7,130 dependent
instruction boundaries**. It compares **14,830,400 CPU-state bytes, 114,080 PPU
bytes and 342,240 CHR bytes**, all exact. Final snapshots additionally compare
471,040 CIRAM bytes, 235,520 ExRAM bytes and 7,536,640 cartridge-RAM bytes.

All 108 no-request programs match a separately built unmodified NES core's
final CPU-RAM/image hashes and video/audio frame counts. The 121 host-enabled
scenarios exercise **4,824 emulated SNES vblank NMIs**, including partial-clock,
capture and nested-worker cases. The three mutated native executables finish
but fail comparisons: wrong raw-CHR offset, live rather than latched upper bits,
and unbuffered data. All six guards preserve prior guest/PPU/CHR state and
complete writable memories against independently executed original prefixes.

The full retained PPU matrix passes **380 scenarios / 11,780 boundaries**, with
all three wrong-result controls, eleven guards and the separately non-passing
fill-attribute diagnostic retained. All **32 runtime-safety configurations**
pass: 4,224 records / 16,896 register-and-flag bytes plus 1,024 OAM bytes, with
fault guards and audio stress. Forty-two representative older-profile builds
are byte-identical to a separately restored baseline: three programs in each
of seven profiles, each with no host interrupt and nested host interruption.
This is representative build identity, not an exhaustive rerun of every older
fixture. See `chr-blank-verification.json` and actual CI for exact provenance.

## Stack failure found during development

The first 16-byte CHR working-state layout exceeded the existing nested-host
stack watermark: `$1E8A`, below the required `$1E90`. It was not accepted.
Packing high bank bits reduced the new storage to 12 bytes, and calculations
reuse already protected address-resolution scratch. The final handler saves
60 bytes in its capture/context region rather than 64. The failing targeted
case now observes `$1E92`; the stack bound and canaries are unchanged. This
is verified emulated interruption coverage, not proof of every possible
interruption point or physical-console testing.

A directory-reuse regression also verifies that an old profile rebuilt in a
previous CHR output directory cannot accidentally append stale CHR data.

## Deliberate limits and reproduction

Live CHR-size changes remain guarded. The documented size-dependent bit latch
and the pinned emulator's current-size interpretation must not be conflated.
This checkpoint verifies a size fixed at boot, not a live-transition model.
Set B, 8x16 selection, rendering, CHR RAM, palette/OAM/status behavior, ExRAM
nametables and independently timed hardware events/stalls remain open.

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_chr_blank.py /path/to/pinned/fceumm
# Rebuild that core, retaining a separately built unmodified copy.
python3 tools/verify_chr_blank.py \
  --nes-plain /path/to/unmodified-fceumm.so \
  --nes-probe /path/to/chr-observed-fceumm.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/chr-blank
```

The workflow runs the new matrix, retained PPU matrix and runtime safety, and
archives exact source, authored inputs, generated assembly and snapshots.
Deterministic CHR bytes are generated from the committed fixture; repeated
large CHR images are not duplicated in the evidence tar. No commercial ROM,
private trace, game screenshot or game-derived binary is included.

Production `snes/src/native.s` and `tools/build_native.py` are unchanged.
**No fresh commercial-game replay was performed.** The earlier RNG mismatch
is unresolved. No gameplay speedup, boss clear, lost-route recovery or visible
graphics improvement is claimed. Next work is the remaining PPU memory and
rendering-dependent mapping behavior, then independently verified event/stall
timing and efficient production integration.

Reference: [MMC5 CHR registers and upper-bit latching](https://www.nesdev.org/wiki/MMC5#CHR_Bankswitching_($5120-$5130)).
Original oracle: FCEUmm `236ccdfc911e84c60fea6b9d0699c2d440a8de14`;
SNES executor: Snes9x `fae2fea08f74180759ef540ee94259213f503480`.
