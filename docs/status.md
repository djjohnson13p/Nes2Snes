# Verified status — 2026-09-25

## Latest measured update: direct accesses, interrupt safety and audio preview

The opt-in SPC700 preview now produces two pulse voices, triangle and noise from
the running game's APU register state. It is **not a faithful NES APU port**:
envelopes, length/linear-counter timing, sweep, DMC and expansion audio remain
unimplemented. Sound tempo follows the slowed game logic.

The ordinary-controller build passes startup, walking, jumping and attacking.
An interrupt-context corruption bug exposed by changed timing is fixed, with a
forced nested-NMI regression and a failing negative control. 90 unit tests,
1,322 independent CPU/PPU records (5,288 bytes), 160 animated sprite frames and
four procedural audio/mute/fallback/stress cases pass. Five selected game images
still match the prior checkpoint (286,720 pixels, zero differences).

The fixed-input walking interval is 240 SNES frames per 120 game updates;
jumping is 50 per 25. This remains approximately half speed on the tested route.
See [new results and limitations](direct-audio-2026-09-25.md) and
[machine-readable evidence](direct-audio-verification.json).

## Previous measured update: pipelined video

The controlled fixed-input walking comparison improves from 386 to 242 SNES
frames for 120 logical game frames: **1.595x the previous checkpoint speed**.
The ordinary controller-driven benchmark independently completes with 242 frames
(previous checkpoint: 388). These two measurements use different sampling/input
methods and must not be mixed when claiming pixel identity.

Five render-aligned replay captures match exactly (286,720 pixels). There are
75 passing unit tests, 1,130 independent CPU/PPU records with zero differences,
and 160 verified animated sprite frames. See [new measured results and limits](performance-pipeline-2026-09-25.md)
and [machine-readable evidence](pipeline-verification.json).

The prototype remains about two SNES frames per game update in the walking
sample. Audio, complete-game coverage and physical-console validation remain
outstanding. The older [fast-path checkpoint](performance-2026-09-25.md) is retained
for history; the sections below describe earlier milestones.

**Update:** the new [native bridge](native-bridge.md) now executes original gameplay in an experimental, slow, silent build. The viewer/frozen-scene findings below remain valid, but the earlier "Not implemented" section describes the pre-bridge checkpoint.

## Working

The native SNES viewer assembles with ca65/ld65, has a valid LoROM header and checksum, boots in Snes9x, displays the uploaded ROM's converted CHR and responds to controller input. It executes new 65C816 viewer code, not the original CV3 game logic.

The supplied-ROM build is 262,144 bytes. Its SHA-256 is `f52945b5c12ee8213afdc5bd5c680187dcabebd5c73eac3a7b8d9f10bacf1411`.

All 32 pages, containing 8,192 tiles, were compared against the NES source pixel indices: 524,288 indices checked, zero mismatches. Next/previous, page wraparound, held-button debouncing and diagnostic palette selection passed. The synthetic fixture independently passed 65,536 pixel-index comparisons.

The Python unit suite passed 43 tests. Details are reproducible using `make test`, `make verify-synthetic` and `make verify-viewer`.

## Frozen native scene

A second native SNES ROM reconstructs the captured title using native background and sprite layers, not a screenshot bitmap. All 57,344 visible pixels match the reference after SNES color-precision conversion. The independent procedural scene also passes all 57,344 pixel comparisons, including sprite flip and priority cases. See `scene-renderer.md` and `scene-verification.json`. This scene remains frozen: no original game logic executes.

## Reverse engineering

A 2,126-frame scripted FCEUmm run observed 19,746,734 instruction executions at 5,194 distinct PRG instruction-entry offsets. The run visits intro/title/name entry/opening and early stage one. It does not cover every level, character, ending, menu or death/restart path.

The observed instructions occupy 10,933 PRG bytes. The other 251,211 PRG bytes remain unclassified in this pass. These are not necessarily all data: they also include unvisited code.

Each of the 32 disassembled PRG banks was assembled and linked, then compared against the original bank. All matched. The reconstructed full NES file also matches the original SHA-256. Unclassified bytes are preserved verbatim, so this is a **partially classified, byte-exact reconstruction**, not complete recovered source.

## Historical pre-bridge limitations (superseded)

At the earlier graphics-only checkpoint, no original game logic executes in the SNES build. Game-state scheduling, NES PPU command translation, MMC5 bank/IRQ behavior, dynamic sprite updates, collision, enemies, music and sound effects are not ported. No full-game speedup or reduced gameplay flicker has been measured. No physical SNES or flash-cartridge test has been performed.

The next milestone is IRQ-aware scrolling/HUD rendering and a validated original gameplay path, not cosmetic polishing of the viewer.
