> Nametable continuation: [full-byte fill-color writes and CPU-mode zero reads](nametable-readback.md).
> That report extends this adapter and documents the still-guarded, conflicting
> source-2 write behavior. The original palette checkpoint is described below.

# Blanked palette transfers with an unmodified NES oracle

## Source and integration boundary

This continuation starts from user-merged PR #19, commit
`4d5775ff3194909f521114219ac2ebba3ab049c5`, tree
`a41c29972d9e9d2ae5e5c08704d0371cdd8df970`. That published implementation is
not the different, older local-only `d95b95a...` experiment. Its 595-test baseline
was restored and executed before editing. The preliminary branch commit
`a5fa08ba22e96fcbbbce551902af25b1016c5ca2` only enables the existing pinned
secondary-oracle build on this development branch; it is not palette acceptance.

The explicit `mmc5-palette-blank` adapter extends the protected fixed-size CHR
profile with palette PPUDATA reads/writes. It is not imported by `native.s` or
`build_native.py`, and it does not change the production CV3 game. No new private
commercial-game replay, RNG correction, rendering improvement, speedup, boss clear,
recovery of missing historical routes or physical-console result is claimed.

## Executed behavior

Palette storage is separate guest memory at `$7E:5800..581F`. Values are six bits;
all 256 addresses in `$3F00..3FFF` select mirrored entries. The four sprite entries
at offsets `$10/$14/$18/$1C` share their corresponding background entries, not one
single backdrop cell. Palette writes retain the full written byte in the PPU I/O
latch while storing only the palette value.

Reads return immediately, apply the grayscale mask, combine the preceding I/O
latch's upper two bits, and update that latch. The delayed-read buffer is refilled
from the shadow nametable address `$2F00 | (v & $FF)`, using the currently selected
CIRAM or fill source. The helper never temporarily changes live `v`. Transfers
advance the address exactly once by the configured +1 or +32 increment. Nonpalette
accesses still use the preceding CHR/nametable handlers. Existing unsupported I/O,
rendering, PPU NMI, ExRAM nametable and live CHR-mode transitions remain guarded.

All temporary variables reuse the preceding protected PPU/resolver scratch. No
larger host-NMI stack frame or relaxed stack boundary is introduced. Palette RAM
is guest state, not callback scratch: the host-worker contract still forbids
callbacks from overwriting guest memory.

The relevant hardware contract is described in NESdev's
[PPU registers](https://www.nesdev.org/wiki/PPU_registers#Reading_palette_RAM)
and [PPU palettes](https://www.nesdev.org/wiki/PPU_palettes). These tests cover
memory-transfer state under the stated blanked profile, not PPU revisions lacking
palette readback, latch decay, physical bus pin timing or palette corruption on
rendering transitions.

## Why the primary oracle changes here

The previously used FCEUmm reference has a known palette-latch discrepancy.
Consequently these new palette programs use **unmodified Nestopia** at
`8f00f500912a847062de432e38765c7285483e62` as the primary independent execution.
CPU/PPU/mapper handlers are not patched, expected seeds or intermediate results
are not injected, and no game or CPU output byte is masked to make a comparison
pass. A separate unmodified FCEUmm run retains its disagreement explicitly as a
non-passing reference-accuracy diagnostic, outside the passing endpoint totals.

The original authored boot initializes all palette entries through actual PPU
port writes, then establishes the prior CHR/nametable state. A program writes its
completion marker and enters a direct self-jump, leaving registers and transfer
memory stable while the unmodified reference completes its video frame. The
native run executes 31 dependent instructions to the same stable endpoint.
This is a common post-boot starting contract, not power-up equivalence.

`palette_state.py` decodes the pinned core's bounded NST chunks. CPU state comes
from CPU/REG and CPU/RAM; PPU transfer state, palette storage and CIRAM come from
PPU/REG, PPU/PAL and PPU/NMT. Duplicate, truncated, oversized, concatenated or
malformed data is rejected. Raw states and original serialized palette bytes are
retained in the artifact.

**Serialization representation is not a CPU-result tolerance.** This Nestopia
revision retains the full written byte in its internal `palette.ram` array and
applies the six-bit mask when using the value. The decoder records that raw array
as `palette_storage` and separately decodes its six-bit hardware values as
`palette`. CPU registers, CPU RAM, the I/O latch and read-buffer results are still
compared byte-for-byte without discarding their upper bits. Invalid serialized
address/write-phase bits are rejected rather than masked away. See the pinned
[NstPpu.cpp](https://github.com/libretro/nestopia/blob/8f00f500912a847062de432e38765c7285483e62/source/core/NstPpu.cpp)
SaveState and palette-read/write implementations.

## Comparison units and limits

Each independent endpoint compares 2,048 CPU-RAM bytes, seven canonical CPU
register bytes, ten PPU transfer-state bytes, 32 decoded palette entries, and
2,048 CIRAM bytes: **4,145 bytes per endpoint**. Canonical CPU P images set the
nonpersistent PHP B/U bits consistently; actual arithmetic and interrupt flags
are not discarded. Final native fields must also equal the last retired native
record, and every native record must carry the correct instruction count.

**This new oracle does not establish per-instruction NES equivalence or independent
NES-cycle timing.** Native per-instruction CPU/PPU/CHR records are retained and
compared between no-host and host-interrupted runs only. Those checks demonstrate
host noninterference, not an independent NES instruction trace. Cartridge RAM and
ExRAM likewise have native no-host/host comparisons here; their independent
behavior is covered by the retained suites, not a new palette-specific snapshot
oracle. Rendered pixels, audio, OAM, vblank status, decay timestamps and scanline
phase are outside these endpoint comparisons.

The palette matrix has no guest IRQ/NMI request stream. The adapter rejects such
stimuli rather than representing an instrumented request injection as an
unmodified-oracle test. Actual emulated SNES host NMIs are separately exercised.

## Reproducible acceptance checks

`verify_palette_timeline.py` executes 304 authored programs in both no-host and
free-running host-NMI modes. The first 256 pair every palette-address alias and
every possible written byte; this is not their full Cartesian product. Other
cases cover backdrop aliases, grayscale, upper-latch combinations, mapped shadow
reads, port mirrors, pattern/nametable/palette crossings and both increments.
Two isolated case workers are the default; reports are ordered deterministically.
A limited smoke run explicitly sets `complete_matrix=false`.

`verify_palette_controls.py` executes 12 additional targeted host configurations
across three of those programs: cost, partial-clock, capture and nested workers.
The declared wait sites must actually be exercised; nested return counts, stack
watermarks and canaries remain required. Three deliberately broken binaries must
complete and then fail for wrong upper latch bits, backdrop aliases or shadow
read-buffer contents.

Six unsupported-operation tests run after a real palette write. For each, a
separately authored original-NES prefix replaces the refused instruction with a
self-jump at that same PC. Native refused state is compared to that independently
executed prefix. No live RAM/register patch or expected state is supplied. These
are profile guards, not assertions that original hardware faults on the operation.

The public workflow requires the complete new matrix, controls, full retained
230-scenario CHR suite, and 32-configuration runtime-safety suite. It archives
exact tested source, authored PRG, generated assembly, raw NST states, decoded
captures and negative results. Its tested commit and final conclusion must be
verified before requesting the user's merge. Local results are not CI results;
replaying saved captures is not an additional emulator execution.

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_palette_timeline.py \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/palette-timeline
python3 tools/verify_palette_controls.py \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so \
  --fce-core /path/to/unmodified-fceumm.so --out build/palette-controls
```

Next work is the remaining OAM/status and rendering-dependent PPU behavior,
independently verified original event/stall timing and efficient production
integration. Earlier CV3 route results remain historical, and the explicit RNG
mismatch is not fixed by these palette-memory operations.
