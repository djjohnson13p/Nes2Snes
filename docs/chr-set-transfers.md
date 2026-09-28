# Blanked CHR set selection composed with OAM and palette transfers

## Source and recovery boundary

The base is user-merged PR #22, `b0a1f3d2460b9323afd9b7cefd0dcb01b6c23bc4`,
source tree `e1812d34ec7cda2455b6c3e36f493305bb9e0cc0`. The 370-file source
archive from its successful CI reconstructs that tree. The baseline's 662
unit/assembler tests passed locally before this work.

This is new implementation on that published base. The earlier local-only
`54cd33e9...` CHR-set source was absent from this workspace and is not recovered
or reused. Its test counts are not this checkpoint's acceptance evidence.

The new explicit `mmc5-chr-sets-blank` adapter composes the published OAM,
palette, nametable and CHR paths. **It requires rendering disabled, 8x16 sprite
mode, no PPU NMI and a bank size fixed at boot.** The production `native.s` and
`build_native.py` are unchanged. No fresh CV3 replay, RNG correction, visible
rendering, speed gain, boss clear or physical-console result is claimed.

## Execution and memory ownership

All twelve CHR bank registers retain their own ten-bit value. A write captures
the then-current upper latch and selects the written set, even when that bank
value is unchanged or that register is inactive in the fixed bank size. A later
upper-latch write does not retroactively change stored banks or select a set.

Set A uses the existing eight registers. Set B's four words plus last-set byte
are guest mapper memory at `$7E:5A00..5A08`, outside the host callback's writable
contract. Computation uses existing protected scratch. OAMADDR remains separate;
neither the host stack frame nor its watermark/canary requirements are enlarged.
The original NES initialization uses ordinary register writes, not state patches.

The selected bank set supplies PPUDATA pattern reads. Set B repeats its 4-KiB
window in 1/2/4-KiB modes; its single register in 8-KiB mode covers the full 8 KiB.
All four fixed sizes are supported. Bank switching leaves the previous delayed
read byte intact; only a subsequent read refills that buffer using the new map.
Palette and nametable transfers still use their existing handlers.

Rendering, live bank-size changes, switching back to 8x8 sprites, PPU status,
DMA/DMC and PPU-generated NMI remain refused. The documented 8x8 bank-set rule
has differed in earlier reference emulators; this profile does not broaden its
contract to that case or declare the discrepancy resolved.

## Independent observations, not expected-state injection

Unmodified Nestopia `8f00f500912a847062de432e38765c7285483e62` executes authored
boot/program inputs to a stable self-jump. The read-only decoder extracts each
register's separately packed high bits, both bank sets, the upper latch and the
last-set selector from its actual NST mapper state. Raw NST snapshots are kept.
The existing parser gains an explicit boolean option to decode 8x16 mode; its
default still refuses that mode. The new adapter requires it rather than treating
an accidentally cleared sprite-mode bit as acceptable.

A complete independent endpoint is **5,457 bytes**: the previous 5,430-byte
CPU/PPU/palette/CIRAM/ExRAM/mapper/OAM endpoint plus 27 bank-register bytes. CPU
results are not masked or altered to force agreement. The native bank registers
must also match the last retired native capture. B-bank data reuses reserved
padding in the existing 48-byte CHR record; prior profiles keep zero padding.

These are final-program-state comparisons, **not independent per-instruction
NES timing**. Native instruction records separately check host noninterference.
Emulated SNES host NMIs cannot write guest memory under the callback contract.
They can interrupt partially computed addresses and bytewise bank writes, but
must preserve caller/scratch state so execution completes consistently.

## Test coverage and failures

The deterministic sweep contains 274 distinct programs and two native executions
per program. It covers both switching directions, all eight pattern slots, all
four fixed sizes, every register (including inactive/unchanged writes), all four
upper-latch values, capacities from 8 KiB to 1 MiB, pattern boundaries, and OAM/
palette/scroll interleaving. This is not every Cartesian combination of inputs.
A smoke run explicitly reports `complete_matrix=false`.

Twelve targeted configurations exercise cost, partial-clock, capture and nested
host-worker sites. Three actual wrong-result executables force set A, discard
high bits or select the wrong B register in the upper pattern half. They must
complete before their comparisons reject them. Five refused-prefix programs
check status, rendering, NMI, sprite-size and bank-size guards against independently
executed original prefixes, without editing live emulated state.

An early guard-harness run incorrectly required fully initialized mapper state
while waiting for the original boot to finish. It failed rather than passing a
wrong endpoint. The wait now reads only the bounded CPU/PPU state until the
requested PC is reached; complete strict mapper/OAM validation still applies to
the accepted endpoint. A regression test includes that uninitialized boot phase.

The full new matrix, controls, unit suite and retained regressions must finish
before merge. Counts above describe planned distinct coverage, not a substitute
for completed reports. Generated reports and the PR verification record specify
actual completed results, core hashes, tested source, and local versus CI scope.
A source upload or draft PR alone is not acceptance evidence.

## Reproduce and resume

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_chr_sets.py --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/chr-sets
python3 tools/verify_chr_sets.py --controls \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/chr-sets-controls
```

The workflow requires the complete new sweep/controls, retained OAM sweep and
controls (including the preserved alternate-core disagreement), and runtime
safety/audio stress. It archives exact source, generated assembly, authored NES
inputs, raw snapshots and result comparisons. No commercial ROM, private game
trace, game imagery or game-derived executable is included.

Remaining integration includes original PPU status/event timing, DMA/DMC stalls,
rendering-dependent mappings and efficient production execution. The saved
133-action route still establishes Block 1-03 entry only; the missing historical
117-action route and a verified SNES first-boss clear are not recovered here.

References: the author's [MMC5 hardware-test report](https://sourceforge.net/p/fceultra/bugs/787/)
and pinned [Nestopia register and state implementation](https://github.com/libretro/nestopia/blob/8f00f500912a847062de432e38765c7285483e62/source/core/board/NstBoardMmc5.cpp).
