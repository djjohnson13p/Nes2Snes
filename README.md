# Nes2Snes

A source-only NES-to-SNES reverse-engineering and porting workspace, initially targeting the supplied MMC5 version of CV3.

**An experimental native-execution build now reaches CV3 stage one with live walking, jumping, attacking and horizontal scrolling. It is slow, silent and trace-bounded—not a complete game port or universal converter.** See [native bridge](docs/native-bridge.md).

The independently tested graphics viewer and frozen title renderer remain available.

## Implemented and tested

- Strict iNES/NES 2.0 parsing, ROM hashing, PRG-bank extraction, and lossless NES CHR conversion to SNES 2bpp and 4bpp.
- A native 65C816/LoROM viewer with DMA uploads, automatic controller reads, 32 pages of the supplied ROM's graphics, and diagnostic palette switching.
- A headless libretro test frontend and optional FCEUmm execution/I/O probe.
- A repeatable input script that reaches the original NES game's early first stage.
- Trace-guided disassembly of all 32 PRG banks. Only observed instructions are marked as code; other bytes remain unclassified byte tables. All banks reassemble exactly, and the resulting NES file matches the input SHA-256.
- 54 unit tests plus independent Snes9x checks of all 8,192 converted tiles: 524,288 pixel indices checked with zero mismatches. Controller next/previous, wraparound, held-button behavior and palette switching also passed.

- A native frozen title-screen renderer using BG1, OBJ and CGRAM, matching 57,344 pixels after color-precision conversion. An independent procedural sprite/attribute scene also matches. This does not execute original gameplay.

See [frozen scene details](docs/scene-renderer.md), [verified results](docs/status.md), [ROM metadata](docs/rom-analysis.json), [runtime findings](docs/runtime-findings.md), [port plan](docs/port-plan.md), and [toolchain provenance](docs/toolchain.md).

## Quick start

Requirements: Python 3.10+, cc65 (`ca65`, `ld65`, `da65`). Emulator tests additionally need NumPy, Pillow, and a separately built Snes9x libretro core. No emulator or commercial ROM is bundled.

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_viewer.py --synthetic --out build/synthetic
# Open build/synthetic/chr-viewer.sfc in an SNES emulator.
```

For the supplied game, place your own authorized ROM at `original/CV3.nes`:

```sh
python3 tools/analyze_rom.py original/CV3.nes --out build/analysis
python3 tools/build_viewer.py --rom original/CV3.nes --out build/cv3
python3 tools/verify_viewer.py --core /path/to/snes9x_libretro.so \
  --sfc build/cv3/chr-viewer.sfc --rom original/CV3.nes \
  --out build/cv3/verification
```

Viewer controls: **Left/Right or L/R** change the 256-tile page; **B** cycles diagnostic palettes. The page number is zero-based hexadecimal. These palettes are not recovered in-game colors. NES CHR alone does not contain the scene's palettes, tilemaps or game behavior.

## Runtime tracing and matching reconstruction

The optional instrumentation targets the FCEUmm source revision in `docs/toolchain.md`. It must be rebuilt locally; the public repository does not include patched emulator binaries.

```sh
python3 tools/instrument_fceumm.py /path/to/libretro-fceumm
make -C /path/to/libretro-fceumm -f Makefile.libretro -j2
python3 tools/trace_rom.py --core /path/to/libretro-fceumm/fceumm_libretro.so \
  --rom original/CV3.nes --out build/trace
python3 tools/analyze_rom.py original/CV3.nes --out build/analysis --trace build/trace
```

The output includes bank assembly, da65 classification files, hardware-access sites, a rebuilt NES file and a byte-comparison report. **Matching bytes does not establish complete reverse engineering.** A byte table also rebuilds exactly; the runtime trace is what supplies evidence about observed code.

## Repository boundaries

`original/` and `build/` are ignored. Do not commit commercial ROMs, extracted tiles, screenshots of game content, generated game-derived binaries or reconstructed commercial game source. Public CI uses original procedural graphics only. All supplied-ROM artifacts are generated privately from the user's input.

This work was implemented, assembled, executed, debugged and tested from the ChatGPT conversation. GitHub Actions bootstrapped the external tools and runs public synthetic checks; no Codex/Work handoff was used.

No physical SNES validation, end-to-end gameplay port, audio port, or measured game-performance improvement is claimed.
