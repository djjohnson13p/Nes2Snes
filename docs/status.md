# Verified status — 2026-09-26

## Current: guarded whole-controller-routine replacement

The opt-in native controller path passes 25 independent NES/SNES configurations
and 242 unit tests. Walking takes 149 rather than 191 display frames for 120
logical updates; the longer existing route improves from 13,495 to 12,540 frames.
All 57 selected endpoints and five tagged images preserve the baseline. The
video callback now supplies exact presentation tags instead of a prior-poll
heuristic. No new boss or full-speed result is claimed.
See [implementation, measurements and limits](native-controller.md).


## Previous: OAM destination wrapping integrated with counter-free execution

See [sprite-DMA correction and scoped independent tests](oam-offsets.md).
216 unit tests and 531 scoped OAM configurations pass. All 256 offsets are
checked in counted and counter-free modes. The 32-configuration runtime safety
matrix also passes. The combined preview retains 191 display frames per 120
walking updates. The counter-free optimization below is retained. This correction does not
establish full-game coverage, perfect rendering/audio or physical-console success.


## Previous: profiling overhead separated from gameplay

The explicit `--no-runtime-counters` build removes per-access debug increments,
not safety traps or actual game/audio counters. Fixed-input walking takes 191
SNES display frames per 120 game updates instead of 225 (17.80% higher
throughput); attacking is unchanged. The counted build is byte-identical to
the previous checkpoint. 200 unit tests and the independent 32-configuration
CPU/PPU/APU/mapper matrix pass. Both modes retain the unknown-code fault guard.
The previously tested staircase route still completes. This is not a new boss
clear, full-speed result or a perfect port.

See [results and limitations](runtime-counters.md) and
[architecture diagnosis/resumption guide](engineering-status.md).

## Historical checkpoints below

# Verified status — 2026-09-26
## Current: memory fast paths and sprite-DMA latch correction

190 unit tests and 29 independent configurations pass: 1,953 CPU/register/flag
records plus 4,864 raw OAM bytes match. The old DMA path fails two PPU-latch
readback records; both now pass. The controlled walking sample improves from
235 to 225 display frames per 120 game updates. Selected replay pixels and all
57 tested staircase endpoints still match the prior SNES checkpoint. OAMADDR
rotation, active-rendering/stack-page DMA, full-game coverage and full speed are
not certified. See [complete scope and evidence](memory-followup.md).

## Previous: indexed memory and PPU dummy-read correction

The runtime now preserves tested side effects of intermediate indexed NES reads.
The previous runtime fails 60 of the new bus fixture's 131 records; the corrected
runtime matches all of them. 178 unit tests and 1,425 records across 11 new
independent configurations pass. Selected gameplay images and the 57 staircase
endpoints still match the preceding checkpoint. Walking takes 235 display frames
per 120 game updates (previously 239): a small gain, still near half speed.
See [changes, evidence and limitations](indexed-bus.md).

## Previous: optional pulse sweeps

The opt-in audio sweep module passes 170 unit tests, 54 independent period
cases, 486 length/status/store-flag records and 420 quantized audio updates.
The 57-action staircase route still completes; all five selected replay images
match the prior renderer. Walking is slightly slower (239 vs 237 display frames
for 120 game updates). This remains an incomplete, approximately half-speed port.
See [sweep results and explicit limits](pulse-sweep.md).

## Previous: independent left-edge masks and HUD layer control

The renderer now clips background and sprites independently in the leftmost
eight pixels and uses the HUD's own layer-enable snapshot. 150 unit tests and
32 whole-frame procedural scenes pass: 1,835,008 binary pixel classes match.
Partial-row timing remains inexact; a rendering-disable split disagrees across
reference emulators and is explicitly reported as unresolved. The 57-action
staircase route still completes. This is not a speedup or a completed port.
See [current results and limits](layer-masks-2026-09-25.md).

## Previous: staircase coverage and experimental raster correction

The expanded trace observes 10,763 instruction entries. The ordinary-controller
build follows 57 new staircase actions to the outdoor section, matching candidate
player positions at all 57 endpoints. It is not a complete stage or boss run.

The opt-in `--experimental-raster-scroll` corrects the tested live-PPU-address
reload and 240-line wrap. 140 unit tests and 419 extra independent CPU/PPU records
pass. Seven authored raster cases match 397,824 stable pixels, but retain 546
aggregate differences on two partial transition rows. Some moving gameplay
captures still differ. No perfect-port or new performance gain is claimed.

See [full report](stair-raster-2026-09-25.md) and
[machine-readable evidence](stair-raster-verification.json).

## Earlier checkpoints

The dated sections below describe the state at their respective checkpoints;
their "latest" descriptions and test counts are historical, not current totals.


Latest continuation: [optional audio envelopes and note counters](apu-counters-2026-09-25.md).
127 unit tests, 486 independent length/status records, and 324 modeled audio updates pass.
The new audio mode costs about 3.4% walking throughput and remains opt-in.
The 10,000-update early-room route passes; a complete, full-speed port is not claimed.

Previous continuation: [bank-switch returns, indirect loads and the extended room-1-02 route](bank-returns-2026-09-25.md). Still not full speed or a complete port.

## Latest: conservative native RAM and shorter simple-I/O handlers

The optional audio build passes the ordinary-controller early-stage route. Fresh
checks pass 102 unit tests, 1,438 independent CPU/PPU records (5,752 bytes),
160 animated object frames and all four audio/stress cases. Five selected replay
images still match. Walking takes 237 display frames per 120 game updates, down
from 240 in the first audio checkpoint and 242 in the prior silent pipeline.
This remains roughly half speed; audio fidelity and whole-game coverage remain
unfinished. See [current report](safe-addresses-2026-09-25.md) and
[evidence](safe-address-verification.json).

## Previous measured update: direct accesses, interrupt safety and audio preview

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
