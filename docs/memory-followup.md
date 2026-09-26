# Memory-path follow-up and sprite-DMA latch correction

This continues source revision `0e1bb3d913bf6777fb59d9c656a3b7775b54f610`.
It remains an incomplete native CV3 port, not a full-speed or perfect conversion.
The original ROM, game graphics, trace, audio and derived ROMs remain outside the
public repository. Public tests use project-authored procedural fixtures.

## Changes

- Indexed zero-page STY now has a dedicated short handler. It preserves the
  original accumulator, indexes and flags while honoring zero-page wraparound.
  The pre-existing `--no-quick-zp` switch retains generic handling.
- The specialized indirect LDA path uses a shorter address calculation and ROM
  range check. It still wraps the pointer and effective address correctly,
  mirrors internal RAM and falls back for hardware/cartridge-RAM accesses.
  `--no-specialized-indirect` retains the shared indirect-read handler.
- Ordinary internal-RAM sprite-DMA pages use an unrolled, wordwise CPU copy.
  This is not an invalid SNES DMA transfer from WRAM to WRAM. The full page is
  copied immediately; no pointer to a mutable future guest buffer is retained.
  `--no-word-oam` restores the previous MVN copy. ROM sources retain the generic
  reader. Both paths preserve the caller's guest register/flag state.

## Correctness error found and fixed

The old OAM DMA implementation copied the bytes but did not update the PPU I/O
latch with the final byte written. A subsequent read of a write-only PPU register
therefore returned an incorrect value. Both RAM and generic DMA paths now update
that latch after the copy.

The new fixture is run independently on the pinned, unmodified NES and SNES
emulators. The actual preceding source revision fails **two of three records**:
its ordinary and mirrored latch readback values are zero instead of `$A4` for the
seed-zero fixture. The corrected runtime matches all three records. This is an
actual negative control, not an artificially broken version of the new code.

For whole-page comparisons, the independent NES core's tagged save state
provides its 256-byte OAM buffer (`SPRA`); this avoids relying on its OAMDATA
readback implementation. The state parser rejects truncated, missing, duplicate
and incorrectly sized fields. The native OAM buffer is compared directly to that
independent buffer, not to a model derived from the new assembly.

The tested contract is deliberately limited to **OAMADDR zero, rendering disabled,
initialized non-stack RAM pages and selected ROM pages**. Nonzero OAMADDR,
active-rendering behavior, stack-page DMA and I/O-source DMA are not fixed or
certified by this checkpoint. The port is still not cycle-accurate. Reference:
[NESdev PPU registers](https://www.nesdev.org/wiki/PPU_registers), including the
I/O latch and OAMDMA behavior, and the pinned FCEUmm PPU state serialization.

## Fresh verification

- **190 Python unit tests pass.**
- **29 independent NES/SNES configurations pass: 1,953 CPU/register/flag records,
  7,812 register-and-flag bytes, and 4,864 raw OAM bytes, with zero differences.**
  These cover indexed STY in ordinary/C0 execution and generic fallback,
  indirect-pointer wrap and RAM/ROM/hardware paths, mirrored DMA sources,
  selected ROM pages, all three store registers and old-copy/generic fallbacks.
  The enabled STY cases check that all 128 intended fast-path stores execute.
- The preceding runtime fails the new latch fixture as described above.
- Five fixed-input gameplay captures still match the preceding SNES renderer:
  **286,720 pixels, zero differences**, after aligning presented game frames.
  This does not imply every-frame or independent-NES image equivalence.
- A fresh ordinary-controller **31-step approach and 57-action staircase route**
  completes. All 57 selected game-state/player-position endpoints match a fresh
  run of the prior checkpoint. No new level or boss completion is claimed.
- The ordinary-controller live-audio route completes startup, walking, jumping
  and attacking. The 14.709-second PCM capture has no full-scale samples, SPC
  ready=1, fault=0 and 2,282 acknowledged DSP commands. This measures working
  output, not NES audio fidelity.

The machine-readable summary is [memory-followup-verification.json](memory-followup-verification.json).
Existing indexed/bus, sweep and animated-object regressions are also rerun before
publication; their independent results are recorded in that summary and in the
checkpoint package.

## Performance

Same matching trace, audio/raster options, fixed logical-frame inputs and
unmodified Snes9x core. Host wall-clock duration is not the metric.

| Interval | Game updates | Prior checkpoint SNES frames | Updated SNES frames |
|---|---:|---:|---:|
| Walk | 120 | 235 | 225 |
| Jump | 25 | 50 | 46 |
| Attack | 25 | 50 | 50 |
| Settle | 60 | 120 | 114 |

Walking throughput improves **4.44%**, jumping **8.70%**, and settling **5.26%**;
attacking is unchanged. Walking averages **1.875 display frames per game update**.
This is faster than the previous prototype but remains well below full speed;
it is not a speedup over the original NES game. No emulator overclock or skipped
game-logic updates is used. Profiling counts locate costly routines, not measure
cycle percentages; the unmodified core supplies these final measurements.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_memory_completion.py \
  --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/memory-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/trace \
  --out build/memory-preview --experimental-audio --audio-counters \
  --audio-sweep --experimental-raster-scroll
```

The first two commands do not require a commercial game. The interactive build
requires the original authorized ROM and matching trace; do not add test replay
or forced-interrupt stress switches. The packaged compatibility fallback adds
`--no-word-oam --no-quick-zp --no-specialized-indirect` while retaining the latch
correction. It is not expected to be as fast.

## Outstanding

Full-speed execution, complete level/character/boss/ending coverage, exact sound
and raster timing, DMC samples, the documented rendering discrepancies and
physical-SNES validation remain unfinished. Unknown code can still deliberately
halt. The new tests strengthen specific memory paths; they do not establish a
perfect port or resolve the additional OAM cases explicitly excluded above.
