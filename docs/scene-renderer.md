# Frozen native scene renderer

A second SNES executable reconstructs a captured CV3 title screen with native BG1 tiles, tilemap palette attributes, 4bpp OBJ tiles, converted OAM and CGRAM uploads. It is **not a screenshot bitmap**, but it is **a frozen scene, not an executing game**. Start does not enter gameplay. No original game logic, animation, sound or collision executes on SNES.

The title capture at NES frame 271 matches all 57,344 pixels in the 256x224 SNES image after converting the reference RGB colors to SNES color precision. Before normalization, 3,738 pixels have small RGB differences. The comparison uses FCEUmm's selected RGB palette and Snes9x's RGB565 output; it is not a claim about physical analog-video color reproduction.

An independent procedural scene exercises background attributes, 8x16 sprite splitting, both pattern tables, horizontal/vertical flips, sprite palettes and foreground/background priority. It also matches all 57,344 pixels against a software NES-style pixel oracle in Snes9x.

## Reproduce the title test

Refresh and rebuild the FCEUmm probe, including its added palette/scroll exports:

```sh
python3 tools/instrument_fceumm.py /path/to/libretro-fceumm
make -C /path/to/libretro-fceumm -f Makefile.libretro -j2
python3 tools/capture_scene.py --core /path/to/fceumm_libretro.so \
  --rom original/CV3.nes --out build/title-capture
python3 tools/build_scene.py --snapshot build/title-capture --out build/title-scene
python3 tools/verify_scene.py --core /path/to/snes9x_libretro.so \
  --sfc build/title-scene/frozen-scene.sfc --snapshot build/title-capture \
  --out build/title-scene/verification
```

## Current limits

One zero-scroll nametable only; the tool rejects nonzero captured scroll and unsupported PPUMASK values. It does not capture or translate mid-frame CHR banking, IRQ splits, palette changes or scrolling. Sprite conversion does not reproduce NES scanline overflow/flicker. Matching one static title frame does not prove other scenes or gameplay work.

The next rendering step is an IRQ-aware HUD/playfield split and scrolling, integrated with original game-state updates rather than recorded frames.
