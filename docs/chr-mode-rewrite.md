# Guarded live CHR size changes

## Provenance and production boundary

Base: user-merged PR #23, `7fde149f2e49ed687b688883f25c74f4f97b651e`, tree
`fecf69e6d43c84dc09a9eb91bc14855a716f00a2`. The restored 378-file source archive
reconstructs that tree; a fresh baseline run passed all 686 tests without skips.
The new `mmc5-chr-rewrite-blank` adapter builds on the published A/B, OAM,
palette and nametable profiles. Earlier profiles are not modified.

This is an experimental execution adapter. Production `native.s` and
`build_native.py` are unchanged. No new commercial-game replay, RNG correction,
visible rendering improvement, speed gain or boss-clear result is claimed.
The unrecovered historical 117-action route is not substituted with a fixture.

## Why mode changes need a guard

The MMC5 hardware documentation describes CHR bank bits being positioned when
a register is written. A later size change does not rewrite those latches.
Some low latch bits are undocumented in larger modes. The pinned Nestopia
reference instead retains raw bank-write values and interprets them using the
current size. Those models need not agree when a stale register is reused.

The included diagnostic writes 3 to A register 7 in 1-KiB mode, switches to
8-KiB mode, and reads pattern data without rewriting that bank. Unmodified
Nestopia's read is retained next to the prediction from the documented latch
mapping. This is a **reference/model disagreement**, not a physical-console
measurement, and it is excluded from positive acceptance counts. No reference
emulator is patched to make either result agree.

The new adapter therefore allows a size change but refuses pattern access until
**all active registers in the selected A or B set have been rewritten after the
last actual size change**. This conservative requirement avoids relying on the
uncertain stale-latch behavior. It is a translator admission rule, not a claim
that the NES hardware faults or tracks validity masks.

## Execution and state ownership

Writes to `$5101` use its low two bits. An unchanged size leaves provenance
intact. An actual change records the new size and invalidates all twelve bank
registers for pattern access; every subsequent bank write restores that register's
validity while retaining the preceding adapter's upper-bit and set-selection
semantics. Returning to a former size also requires rewriting. Merely switching
sets or changing the upper latch does not authorize stale banks.

For set A, the active-register masks for 8/4/2/1-KiB modes are `80/88/AA/FF`.
For set B they are `8/8/A/F`. These masks decide admission only. The native
mapper computes the current slot using actual retained register values and the
current size. Capture records mark stale mapped slots as `$FFFF`; this metadata
does not authorize a read. The resolver checks the selected set before changing
PPU address/latch/buffer state or guest memory. Immutable-pattern writes follow
the same conservative gate, even though the underlying ROM write is ignored.

The current size and twelve validity bits occupy `$7E:5A09..5A0B`, adjacent to
existing guest B-bank storage and outside the host callback's writable contract.
Calculations reuse existing protected scratch. Three reserved bytes in the
existing 48-byte CHR record retain mode/provenance. No host stack frame, watermark
or canary limit is enlarged or relaxed. These native policy bytes are **not**
counted as independently observed NES hardware state.

Palette/nametable transfers can continue while pattern-bank provenance is invalid.
Rewriting and size changes preserve the existing delayed read byte. The profile
still requires forced blank, 8x16 sprite mode and no PPU-generated NMI. PPUSTATUS,
rendering, DMA/DMC, physical interrupt timing and production scheduling remain
unsupported.

## Independent acceptance and coverage

The unmodified pinned Nestopia core executes ordinary authored initialization
and program instructions to stable endpoints. No expected intermediate bank,
memory, register, buffer or timestamp values enter execution. Each endpoint checks
5,457 bytes using the preceding strict CPU/PPU/mapper/ExRAM/OAM decoder plus actual
serialized A/B registers. The latter are the reference's logical register image,
not a claim about undocumented physical latch bits. Native final mode/provenance
must independently match the last retired capture; malformed policies reject.

The deterministic complete matrix has 124 programs and two native runs per
program. It covers every directed size transition in both sets, both pattern
halves, same-mode writes with ignored upper bits, selected capacities from 8 KiB
to 1 MiB, delayed-buffer preservation and palette/scroll/OAM composition. It is
not every Cartesian combination of values, addresses and cartridge sizes.

Twelve additional targeted configurations exercise cost, partial-clock, capture
and nested-host interruption sites. Two wrong-mapping executables must complete
but fail independent readback. A third executable incorrectly preserves stale
bank authorization and must fail the refused-prefix test. Eight guards compare
against independently executed original prefixes: stale, partial A, partial B,
wrong-set, status, rendering, NMI and sprite-size cases. Prefixes terminate via
ordinary authored self-jumps; no live emulator state is edited.

These are independent **final-program endpoints**, not independent per-instruction
NES timing. Native instruction records establish host noninterference separately.
The complete source revision, finished JSON reports and actual CI result determine
acceptance; coverage counts are not proof that an unfinished run passed.

## Reproduction and resumption

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_chr_mode_rewrite.py \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/chr-modes
python3 tools/verify_chr_mode_rewrite.py --controls \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/chr-modes-controls
```

A limited smoke run explicitly reports `complete_matrix=false`. CI requires the
complete new sweep, controls, retained fixed-size A/B sweep/controls and runtime
safety. It archives exact source, authored programs, raw NES snapshots, generated
assembly, captures and the separately unresolved reference diagnostic. No private
commercial ROM, game trace, imagery or game-derived executable is published.

References: [MMC5 CHR input-latch and output-address tables](https://www.nesdev.org/wiki/MMC5#CHR_Bankswitching_($5120-$5130))
and [pinned Nestopia mapper implementation](https://github.com/libretro/nestopia/blob/8f00f500912a847062de432e38765c7285483e62/source/core/board/NstBoardMmc5.cpp).
Further hardware evidence is needed before relaxing the stale-register gate.
