# Layer masking, repeatable recovery, and unresolved timing

This continues `fe74572107f068ffa7e3244d251b3b431fa8c830`. It is a correctness
increment, **not** a perfect port, full-speed result, or complete-game test.
The supplied ROM, trace, audio, screenshots and generated game ROMs stay private.

## Implemented

The native SNES window clips the leftmost eight pixels independently for NES
background and sprites. The renderer now applies the top/HUD snapshot's own
layer-enable bits rather than applying the bottom/playfield settings everywhere.
Window-mask HDMA follows the same run lengths as the layer-enable table. This
also handles an object-only HUD and top-visible/bottom-blank presentations.
Window configuration is initialized lazily and reused; unchanged top/bottom
masks do not require an extra HDMA channel. The new path uses channel 3; existing
TM and raster-scroll tables retain channels 1 and 2. All snapshots are prepared
before their transfer window; live guest state is not consumed during display.

`--no-layer-masks` compiles the new path out. With the same input, trace and
options, that fallback reconstructs the starting interactive ROM byte-for-byte:
`b6895590ccd0ebf3d68139a31dc173127c624d5bcfc8343b7a04ce113bd9e029`.
The new interactive audio/counter/raster build is
`4ccb9e2d9ce9a8edb9c3d2337ff9ca4a663b298eb36d14626dd0941314a4c49d`.

## Actual test scope

- **150 unit tests** pass. The new tests validate authored fixtures, bad inputs,
  distinct variants, counter cycling, and the independent window truth table.
- **32 steady scenes**, covering all 16 supported PPUMASK layer/left-edge
  combinations in both sprite sizes, match the independent FCEUmm output:
  **1,835,008 binary pixel classes, zero differences, no excluded pixels**.
  These black/white tests establish geometry, not analog color fidelity.
  The old renderer's negative control differed in 1,092 pixels of the left strip.
- Two changing-mask runs observe 272 distinct presentations each, spanning all
  masks and counter wrap. Each checks 221 settled presentations exactly against
  the independent static NES images. **51 boundary presentations per run are
  explicitly not compared** because guest/render timing is not precisely aligned.
  This tests stale-window state, not transition timing or every-frame equivalence.
- Six split tests match 342,528 pixels outside the partial interrupt row.
  **90 pixels differ on the six transition rows in aggregate**; only two cases
  are whole-frame exact. The passing stable-region check does not erase that fact.
- The earlier seven raster cases retain **546 full-frame pixel differences**
  on their partial transition rows and zero differences in 397,824 stable pixels.
- Fresh CPU/PPU/direct-bank regressions compare **419 records / 1,676 bytes**
  against independent NES and SNES cores with zero differences. These are this
  pass's repeated regressions, not 419 newly implemented CPU behaviors.
- 160 animated object frames (81,920 OAM bytes), the four existing audio/mute/
  fallback/interrupt-stress cases, and ordinary controller-driven startup,
  walking, jumping and attacking pass again. A live 15.49-second capture has
  SPC ready=1, fault=0, 2,282 acknowledgements and no full-scale PCM samples.

## A reference disagreement is not counted as a pass

A seventh split fixture sets PPUMASK to zero after the MMC5 interrupt. Across
four sampled frames, the pinned FCEUmm core alternates between two outputs, with
12,987 and 32,676 white pixels. The separately built, unmodified Nestopia core
produces an all-black frame at each sample. The SNES produces a stable split
with 12,952 white pixels. **These are incompatible observations, not proof that
one of them is hardware-correct.** The Nestopia NTSC filter is explicitly off.

`probe_mask_oracles.py` retains all three complete outputs, hashes, frame counts
and option settings. Its result is `diagnostic_only_not_accuracy_pass`. That
render-disable case is absent from the *six-case supported split matrix*, not
silently removed from the project results. Physical hardware or a more precise
cycle/PPU investigation is still needed. No emulator source was changed to make
these comparisons pass.

## Recovered game route and performance

The 10,000-update reference route and staircase tracing were regenerated from
source; their union reproduces 10,763 observed instruction entries. Additional
statically inferred sites are separately recorded by the builder and must not
be described as observed execution.

The normal-controller build completes the 57-action staircase route to the
outdoor section. Three candidate state bytes (game state and player X/Y) match
at all 57 endpoints against both the earlier build and the NES route. This is
**not** full RAM, every-frame, full-stage, boss or ending validation. Some moving
reference captures and game timer/sprite phases still disagree.

The route including startup takes 11,960 SNES display frames versus 11,946 before
these changes: 14 more, about 0.12%. Five selected fixed-input, render-aligned
SNES gameplay captures remain identical (286,720 pixels). The short walking
interval takes 237 display frames for 120 game updates, versus 236 before; the
other sampled intervals are unchanged at 50/50/120. **No speedup is claimed**;
this remains approximately half speed. No overclock or skipped game updates is
used.

## Reproduce

With pinned cc65 and independently built emulator cores:

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_masks.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/layer-masks
python3 tools/probe_mask_oracles.py --fceumm /path/to/fceumm_reference.so \
  --nestopia /path/to/nestopia_libretro.so --snes /path/to/snes9x_libretro.so \
  --out build/layer-disable-diagnostic
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/stair-trace \
  --out build/current --experimental-audio --audio-counters --experimental-raster-scroll
```

The ordinary interactive build omits replay and forced-interrupt test flags.
The private checkpoint includes its matching trace and exact source, so it can
be rebuilt without redoing the traced navigation. Public CI uses only authored
procedural data; no commercial ROM is uploaded to GitHub.

Window-register behavior was cross-checked against Doug Fraker's authored
[HDMA examples](https://nesdoug.com/2020/06/14/hdma-examples/). Independent cores
are pinned to FCEUmm `236ccdfc911e84c60fea6b9d0699c2d440a8de14`, Snes9x
`fae2fea08f74180759ef540ee94259213f503480`, and Nestopia
`8f00f500912a847062de432e38765c7285483e62`. See
[machine-readable evidence](layer-masks-verification.json).

## Unfinished

Cycle-faithful rendering and input scheduling, full-speed operation, sweep/DMC/
noise/expansion and exact audio timing, comprehensive game routes and physical
SNES validation remain outstanding. Unclassified execution still deliberately
halts. This checkpoint fixes specific missing rendering behavior without claiming
that the rest of the game is correct.
