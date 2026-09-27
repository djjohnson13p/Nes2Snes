# Blanked nametable readback on the palette adapter

## Base, scope, and recovery boundary

This change starts from merged PR #20, commit
`4e10bf6a46caf57395512a9143996ebe5abfe152`, source tree
`e0f17aee28d6edeaf8907a6685136f62914f5df9`. The 357-file CI archive restores
that exact tree, and a fresh run passes its 623 baseline tests.

The preceding local OAM commit `3cf8531f49202b73887335619c2afe13c3a25b9d`
was not present in the restored workspace or the saved files inspected. This is
separate nametable work, not recovery or publication of that OAM implementation.
No partially uploaded OAM tree is used as a starting point or acceptance record.

Only the explicit `mmc5-palette-blank` adapter changes. The production CV3 runtime
and builder, and all earlier non-palette profiles, remain unchanged. No fresh
commercial-game replay, RNG correction, rendering improvement, speedup, or boss
clear is claimed.

## Executed behavior

Palette-profile writes to the MMC5 fill-color register `$5107` now accept all
byte values. Its low two bits choose the palette index replicated in the four
attribute fields. Upper bits are not carried into the attribute byte. This is
verified against the existing unmodified Nestopia oracle, not the known differing
FCEUmm fill implementation. Earlier FCEUmm-observed profiles keep their old guard
and their separately recorded reference diagnostic.

All values of nametable selector `$5105` are now admitted in this adapter. Source
2 reads return zero in the inherited CPU-only ExRAM modes 2 and 3, independently
of the nonzero ExRAM contents visible to CPU reads. Buffered reads and palette
shadow-buffer refills use that selection without replacing live PPU `v`.
Switching between the admitted ExRAM modes preserves storage. CIRAM sources 0/1
and fill source 3 retain their previous behavior.

**Source-2 PPU writes remain guarded.** An authored diagnostic writes through
source 2, changes the mapping to CIRAM, and reads the same address. Unmodified
Nestopia returns `$77`; unmodified FCEUmm returns the original `$3C`. This is a
preserved reference disagreement, not a verified hardware rule. The native
implementation refuses that operation before latch/address, CPU state, or guest
memory changes. It does not copy either uncertain write behavior. Rendering-
dependent ExRAM modes 0 and 1 remain refused too.

The old palette control that refused the selector value `$AA` is replaced by a
rendering-dependent ExRAM-mode refusal. Selector `$AA` is now exercised as a
positive read case, with separate before-write guards; the previous negative
case is not silently counted as retained.

## Independent observation and acceptance

The existing unmodified Nestopia endpoint method is retained: ordinary original
instructions initialize the machine and run to a stable self-jump. The native
side receives authored code/data and initial state, not expected intermediate
registers, read buffers, mapper results, or timestamps.

A new read-only NST decoder obtains the actual saved ExRAM mode, nametable
selector, fill tile and fill color from the mapper's serialized registers. It
also decodes the complete 1 KiB ExRAM snapshot. The serialized fill-color bits
share a byte with unrelated split-screen state; decoding its low two bits is a
field extraction, not a tolerance applied to CPU readback. Raw NST files remain
in the evidence. Missing, duplicated, truncated and malformed mapper chunks and
external-memory snapshots reject acceptance.

Each new independent endpoint compares **5,173 bytes**: the existing 4,145-byte
CPU/PPU/palette/CIRAM endpoint plus four mapper-state bytes and 1,024 ExRAM bytes.
Final native mapper fields must also match the last retired native CPU/PPU record.
These are **final-endpoint** comparisons, not per-instruction NES timing checks.
Native per-instruction records are used for host-interrupt noninterference only.

No extra host context or stack storage is introduced. Existing canaries, stack
watermarks, nested-return counts and protected-scratch comparisons remain required.
Three actual wrong-result binaries test missing fill masking, nonzero source-2
readback and incorrect quadrant selection. Four refused-prefix tests cover
source-2 writes in both CPU modes and attempts to enter ExRAM modes 0/1.

## Reproduction and evidence

The new deterministic matrix contains **544 authored programs**: all 256 color
writes, all 256 selector values with one chosen quadrant per program, 16 explicit
quadrant/source combinations, eight ExRAM-mode cases, and eight palette-shadow
cases. Each runs without host interrupts and with free-running host interrupts.
This is not every Cartesian combination of values, mappings and accesses.
Targeted cost, partial-clock, capture and nested-worker controls are separate.
A limited smoke run explicitly reports `complete_matrix=false`.

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_nametable_palette.py \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/nametable-palette
python3 tools/verify_nametable_palette.py --controls \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so \
  --fce-core /path/to/unmodified-fceumm.so --out build/nametable-controls
```

The updated palette workflow requires the new complete matrix and controls as
well as the retained palette, CHR and runtime-safety suites. It archives the exact
tested source, authored inputs, generated assembly, raw NST states, decoded
captures and non-passing reference diagnostics. Completed run results and their
actual tested revision, not the planned program count, determine acceptance.

The native resolver and the observation code changed in this checkpoint; it does
not implement OAM, DMA/DMC, PPUSTATUS timing, rendering, or production scheduling.
The prior OAM publication block and missing source remain separate recovery work.

References: [MMC5 nametable and fill registers](https://www.nesdev.org/wiki/MMC5)
and pinned [Nestopia MMC5 state and register implementation](https://github.com/libretro/nestopia/blob/8f00f500912a847062de432e38765c7285483e62/source/core/board/NstBoardMmc5.cpp).
The primary core is unmodified Nestopia `8f00f500912a847062de432e38765c7285483e62`;
the alternate diagnostic core is FCEUmm `236ccdfc911e84c60fea6b9d0699c2d440a8de14`.
