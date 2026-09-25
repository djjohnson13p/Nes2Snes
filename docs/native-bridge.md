# Native execution bridge — experimental playable prototype

**Performance update:** see [the measured optimization checkpoint](performance-2026-09-25.md).
The results below describe the initial playable checkpoint; the newer walking
sample is 1.567x faster but still not full speed.


This checkpoint executes original CV3 instructions on the SNES 65C816, handles selected NES hardware operations in a new host layer, and renders live game state using SNES BG/OBJ/CGRAM/DMA/HDMA. It is not a recorded animation or a screenshot viewer. **It is not yet a complete or full-speed game port.**

## Architecture

The current layout duplicates the 16 possible 16-KiB primary program banks for the two observed C000 banks (30 and 7). Each of these 32 complete CPU mappings has an unmodified data copy and a separately patched execution copy. Changing MMC5 banks switches the SNES program/data bank selection rather than copying kilobytes of program RAM. Keeping raw data separate preserves reads of bytes that were patched for execution.

Observed instruction boundaries come from the FCEUmm probe. Conservative direct control-flow expansion adds separately identified **inferred** instructions. Unknown execution traps to a diagnostic instead of silently interpreting data as code. Selected memory operations are replaced with same-size COP calls; ordinary instructions remain native. The bridge handles effective-address wrapping, arithmetic flags, memory mirrors, and the observed mapping model.

The original NMI drives game logic; original mapper IRQ routines are invoked in increasing virtual scanline order. The renderer keeps dirty nametable rows, caches converted CHR pages, constructs native objects from live NES OAM, and currently supports one HUD/playfield layer split. IRQ execution is frame-scheduled, not cycle-exact.

## Reproduced locally

- All 54 Python unit tests pass.
- A new, entirely procedural CPU/mapper ROM runs in independent FCEUmm and Snes9x cores. **180 records / 720 register-and-flag bytes match**, including RAM mirroring, zero-page wrapping, arithmetic edge cases, raw-code data reads and all 32 supported bank combinations.
- The supplied-ROM prototype passes intro/title/name entry/opening, reaches stage one, and accepts walking, jumping and attacking input. Horizontal camera movement updates the live background. A 1,350-logical-frame sequence reached this point with no unknown-code trap.
- This first renderer checkpoint is slow: the walking sample required approximately five SNES frames per logical game frame. It is a compatibility milestone, not a performance improvement over the original NES game.

## Build and verify

Use only an authorized local ROM. Commercial game data stays under ignored `original/` and `build/`.

```sh
python3 tools/trace_rom.py --core /path/to/instrumented/fceumm_libretro.so \
  --rom original/CV3.nes --out build/trace
python3 tools/extend_trace.py --core /path/to/instrumented/fceumm_libretro.so \
  --rom original/CV3.nes --trace build/trace
python3 tools/build_native.py --rom original/CV3.nes \
  --trace build/trace --out build/native
```

The trace bounds which paths are executable. Additional actual gameplay coverage may be needed when the safety guard stops at a new location. The first checkpoint's gameplay coverage also included an adaptive Start sequence that stops sending Start as soon as the game's main state reaches 4; continuing Start pulses can pause gameplay.

Public synthetic verification needs no commercial input:

```sh
python3 tools/native_fixture.py --out build/native-fixture
python3 tools/build_native.py --rom build/native-fixture/fixture.nes \
  --trace build/native-fixture --out build/native-fixture/snes
python3 tools/verify_native_cpu.py --nes-core /path/to/fceumm_libretro.so \
  --snes-core /path/to/snes9x_libretro.so \
  --fixture build/native-fixture --out build/native-fixture/verification
```

Controls in the supplied-ROM build: SNES A maps to NES A (jump); B or Y maps to NES B (attack). Start, Select and directional buttons map directly.

## Boundaries still open

Audio is absent. Full-game code coverage, all characters and routes, NES vertical nametable wrapping, additional IRQ raster effects, some PPU read-buffer corner cases, detailed APU status and cycle-exact behavior are not complete. No physical SNES/flash-cartridge verification has been performed. Performance needs substantial improvement. Unsupported code/mapping faults are intentional, not evidence that a game is fully ported.

Diagnostic WRAM: $0906 logical frames, $0908 host frames, $090A virtual IRQ calls, $090C fault PC, $090E fault bank, $090F fault type (1 unknown code, 2 unsupported operation, 3 unsupported bank).
