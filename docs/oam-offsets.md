# Nonzero sprite-DMA destinations — 2026-09-26

Initial investigation baseline: `a19a87c328e47e3603e3f049b605a85693e230c9`.
Final integration baseline: `086efb94182f6dd28be01acb699e1993c6112462`.
The newer counter-free optimization was discovered on main during publication
and is preserved, not overwritten or claimed as newly authored in this change.
This is a compatibility correction, not a speed milestone or a complete port.
Commercial ROMs, game-derived graphics, audio and execution traces remain outside
this public repository. Public test inputs are authored procedural programs.

## Corrected behavior

The preceding `WriteOamDma` copied all 256 source bytes to destination zero,
regardless of the guest OAMADDR register. A full transfer must instead begin at
that destination and wrap within the 256-byte sprite memory. The new handler
honors that destination, returns OAMADDR to its original value after the full
copy, and permits a subsequent OAMDATA write at the correct position. It copies
immediately: changing the source afterward does not change the copied buffer.

The fast zero-offset path is preserved; a nonzero offset selects a bounded
byte-copy path in `native_oam_offset.inc`. Existing context handling preserves
guest registers and flags. Tests cover initialized ordinary RAM, RAM mirrors,
selected mapped ROM pages, STA/STX/STY writers, C0 execution, direct/generic
interception and a follow-up write. Active-rendering DMA, guest-stack/I/O-source
DMA, OAM decay and revision-specific OAMADDR corruption are not certified here.

## Independent tests and reference disagreements

The primary destination/address oracle is **unmodified Nestopia**, pinned at
`8f00f500912a847062de432e38765c7285483e62`. Tests extract its actual serialized PPU
OAM and OAMADDR, not a rotation array calculated by the new assembly or renderer.
The strict NST reader checks chunk bounds, duplicate fields, expected lengths
and bounded decompression. The libretro wrapper's documented eight/twelve-byte
tracked-input footer is kept separate from the NST root, not mistaken for padding.

- **216 unit tests pass** after integrating with the newer source revision.
- **All 256 destination offsets in both counted and counter-free builds, plus
  19 additional configurations, pass**: 531 configurations, 135,936 OAM bytes
  and 1,601 CPU/register/flag records (6,404 record bytes) checked.
- The comparison masks only physically absent sprite-attribute bits 2, 3 and 4.
  Raw byte disagreements remain recorded; this is not raw-byte identity.
- The actual preceding source fails the offset-1 negative control in **all 256
  meaningful OAM bytes** while its CPU/flag/latch records still pass. The new
  runtime has zero meaningful OAM differences in the same test.
- The exhaustive fixture uses a host acknowledgement to advance between cases.
  That acknowledgement is confined to the procedural test, never game input or
  an interactive build. All 256 observations must be present and correctly ordered.

The original FCEUmm oracle remains in the test run. At its pinned revision it
redirects some nonzero-offset writes in `B2004`, producing a disagreement with
Nestopia in **248 of the 256 offsets**. These are retained explicitly, not
silently dropped or counted as passing NES hardware comparisons. The destination
fix follows Nestopia and the documented incrementing OAMDATA/DMA behavior.

A **separate unresolved latch discrepancy** is retained. At destination 127,
seed 7 and an unrestricted final source byte, Nestopia reports latch `$63` while
FCEUmm and this bridge report `$6F`. Inspection shows Nestopia's generic DMA
path masks the absent attribute bits in its latch as well as stored OAM. This
checkpoint does not claim to settle that discrepancy on physical hardware.
The acceptance fixture neutralizes only those disputed bits in the final RAM
source byte; the unrestricted failing comparison remains in the report outside
pass totals. No claim of unrestricted nonzero-offset DMA-latch equivalence is made.

Reference sources inspected:

- [NESdev PPU registers — OAMADDR, OAMDATA, OAMDMA and I/O latch](https://www.nesdev.org/wiki/PPU_registers).
- [NESdev PPU OAM — implemented attribute bits](https://www.nesdev.org/wiki/PPU_OAM).
- Nestopia's authored `source/core/NstPpu.cpp`, `NstState.cpp` and
  `libretro/libretro.cpp` at the pinned revision above.
- FCEUmm `src/ppu.c` at `236ccdfc911e84c60fea6b9d0699c2d440a8de14`.

The existing 29-case memory suite (1,953 records and 4,864 raw OAM bytes),
11-case indexed suite (1,425 records), and pulse-sweep/length/nested-interrupt
suites also passed again with their original oracles and scoped comparisons.

No emulator implementation is incorporated in the native runtime. Emulators
remain external reference/test dependencies.

## Gameplay checks and cost

Fresh 086efb9 baseline and corrected ROMs use the same supplied ROM, trace,
audio/raster settings, `--no-runtime-counters`, fixed guest inputs and unmodified
Snes9x core. The counted diagnostic mode remains available. Five selected images
still match the baseline: **286,720 pixels, zero differences**. The ordinary
controller builds independently complete the 31-step approach plus 57-action
staircase route; all 57 selected game-state/player-position endpoints match.
This does not establish new room, boss, character, or whole-game completion.

| Interval | Guest updates | Baseline display frames | Corrected display frames |
|---|---:|---:|---:|
| Walking | 120 | 191 | 191 |
| Jumping | 25 | 42 | 42 |
| Attacking | 25 | 50 | 50 |
| Settling | 60 | 106 | 106 |

These counter-free intervals are unchanged by the destination fix. An earlier
counted comparison during this investigation measured 225 versus 226 walking
frames; that result belongs to the counted mode and must not be mixed with this
one. Relative to the previously delivered counted build, the retained
optimization is 17.80% faster on this walking interval (225/191), but this DMA
fix is not itself a speedup. It is still below full speed at about 1.592 display
frames per walking update. There is no evidence that the currently tested CV3
route required a nonzero DMA offset. No overclock or skipped guest
updates is used. The saved audio implementation is unchanged, not newly perfected.

The integrated counter-free CPU/PPU/APU/mapper matrix and unknown-code guards
are rerun separately; their results are included in the compact evidence.

See `oam-offset-verification.json` for the compact measurements. Public CI emits
full per-case evidence, both reference disagreements and the negative control.

## Reproduce

With ca65/ld65 on PATH and pinned unmodified emulator cores:

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_oam_offsets.py \
  --nes-core /path/to/nestopia_libretro.so \
  --snes-core /path/to/snes9x_libretro.so \
  --fceumm-core /path/to/fceumm_reference.so \
  --previous-root /path/to/a19a87c-source --out build/oam-offsets
```

The first `--nes-core` is Nestopia, not FCEUmm. The secondary core is retained for
explicit diagnostics; the optional previous source supplies the negative control.
No commercial ROM is required for this matrix. Omitting `--previous-root` does
not establish that a negative control was performed.

## Why this is not a finished port

This remains a trace-bounded native-execution/compatibility bridge, not a complete
rewrite of all game subsystems. Frequent memory, hardware and bank operations
still need software handlers. Matching isolated CPU or PPU tests cannot establish
full-speed execution, pixel-perfect timing, complete sound or every gameplay path.
Timing changes can expose latent compatibility faults. The remaining raster,
audio/DMC, coverage and physical-console validation gaps are not resolved here.

## Publishing and session status

The connected account reported push access, and a branch plus investigation
commit `eaf5a852144cdd44f43b714eb6d6611c77310276` were successfully written during
this continuation. No additional user authorization was needed. Some generic
connector fetch URLs were rejected as unsupported endpoint forms; supported
commit/run/artifact actions succeeded. Those request restrictions are not
repository write denials. The prior silent chat interruptions are undiagnosed;
no claim is made that GitHub permissions or this DMA fault caused them.
