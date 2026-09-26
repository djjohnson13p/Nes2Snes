# Staircase coverage and optional live-V raster scrolling

This continues source revision `1919c0ece573e5c30cd0664a0badb45504c9b4e1`.
It is not a completed, full-speed or pixel-perfect CV3 SNES port. Commercial
ROMs, game screenshots, execution traces and audio are not stored in this public
repository. The new public fixture and graphics are procedural original work.

## A genuinely longer gameplay path

`tools/routes/cv3-stair-room.json` supplies 57 named actions (3,332 logical
updates) after 21 repetitions of the existing startup/walking pattern. It
navigates room 1-02's staircases, attacks the encountered enemies and reaches the
outdoor section above the stair room. It does not finish the stage or a boss.
No cheats, invulnerability, emulator overclock or game-update skipping are used.
Some waits and missed attacks are retained to preserve the tested enemy phase.

The older trace halts at A8:B5F6 during the first climb. New observation adds
1,835 instruction-entry offsets, bringing the merged total to 10,763. These are
observed instruction entries, not a recovered-source completion percentage.
The expanded native build completes the 57 actions without a diagnostic halt.
The game-state byte and candidate player X/Y bytes match at all 57 endpoints.
This is a narrow state check, not equivalence of all game RAM or rendered frames.
The complete run including startup uses 11,946 SNES display frames.

The instrumented NES route now records the **exact actual emulator-call input
timeline**, separately from logical-NMI counts. Replaying that timeline in the
unmodified FCEUmm core matches all 57 reference RGB images and 2-KiB RAM snapshots:
3,268,608 pixels and 116,736 RAM bytes, zero differences. This validates the NES
reference observations. It is **not** a NES-versus-SNES full-state comparison.

## Rendering error and experimental correction

The old renderer derived vertical scrolling from the final temporary PPU address
`t`. On the tested staircase path the original IRQ routine reloads live `v` via
PPUADDR, then overwrites temporary `t` while leaving that live vertical reload in
effect. Using the final `t` loses the intended vertical position.

`--experimental-raster-scroll` records that IRQ-time live-address reload and
uses it for the playfield. A native HDMA vertical-offset change skips the two
padding tile rows when wrapping a 240-line NES nametable inside the 256-line
SNES tilemap allocation. It also recognizes one temporary all-zero-CHR background
interval below the HUD. This recognition inspects converted cartridge bank
content; it does not hard-code CV3's particular blank-bank number. Sprites remain
available while the background is suppressed.

This is a **frame-scheduled approximation**, not an emulation of every PPU dot.
The supported reload timing contract is a write taking effect at requested IRQ
line + 1. The new fixture deliberately fixes that delay. Arbitrary reload code,
multiple disjoint blank intervals and out-of-range coarse-Y tricks are not
certified by these tests. Moving game captures still show presentation-phase
and sprite/HUD differences. The option corrects the large observed background
displacement; it does not make every screenshot identical.

The authored NESdev [split-scrolling reference](https://www.nesdev.org/wiki/User:Bregalad/Split_Scrolling)
describes live-v versus temporary-t writes and the coarse-Y row-29 wrap. The
implementation here is original and tested against independent emulator output.

## Fresh checks and explicit error accounting

- **140 unit tests passed.** New tests cover action-script bounds, safe output
  names, contradictory controls and deterministic procedural fixture creation.
- With raster support enabled, **419 additional independent CPU/PPU/mapper
  records (1,676 register-and-flag bytes)** match: 180 CPU, 47 PPU and 192
  all-bank direct-write checks. These do not certify all CPU cases.
- Seven procedural Y positions (0, 1, 7, 8, 63, 178, 239) compare black/white
  pixel geometry in unmodified NES and SNES cores. **397,824 stable pixels match**.
  Two partial transition rows (32 and 48 in the cropped frame) are reported
  separately: **546 full-frame pixel mismatches remain in aggregate**. They are
  not hidden, counted as matches or described as perfect. This check measures
  binary pattern geometry, not physical-console RGB color fidelity.
- The prior renderer, used as a negative control on the Y=178 fixture, differs
  at 24,535 stable pixels. The new renderer has zero stable-pixel differences
  on that same fixture while retaining the documented partial-row differences.
- An ordinary-controller build with experimental raster and counter-based audio
  completes startup, walking, jumping and attacking. Its early walking interval
  uses 237 display frames per 120 game updates: roughly half speed. No new
  performance improvement is claimed. Sound output has no mailbox fault or
  full-scale PCM samples; it remains the coarse four-voice preview.
- Disabling raster support and using the earlier trace reproduces the previous
  counter-enabled interactive ROM byte-for-byte (SHA-256
  `1bf5bbfd14e1e761ec298f457c1e18330cd2588f1a610a77d0aa397748ea9b88`).

The tested new interactive audio ROM SHA-256 is
`b6895590ccd0ebf3d68139a31dc173127c624d5bcfc8343b7a04ce113bd9e029`.
It uses live controls, not the input-replay or interrupt-stress modes.
See [machine-readable evidence](stair-raster-verification.json).

## Reproduce the authored raster test without a commercial ROM

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_raster.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/raster-matrix
```

The test exit status checks the explicitly defined stable region. Inspect the
full-frame and transition-row counts in `raster-verification.json` as well.
The pinned external source revisions are in `toolchain.md`.

## Reproduce the private supplied-game route

Use your authorized local ROM and the preceding compatible trace (available
in the prior private checkpoint, not in this public repository):

```sh
python3 tools/gameplay_route.py --platform nes --core /path/to/fceumm_probe.so \
  --rom original/CV3.nes --base-trace build/base-trace \
  --steps 21 --actions tools/routes/cv3-stair-room.json --out build/stair-nes
python3 tools/verify_reference_route.py --core /path/to/fceumm_reference.so \
  --rom original/CV3.nes --source build/stair-nes --out build/stair-reference
python3 tools/build_native.py --rom original/CV3.nes --trace build/stair-nes/trace \
  --out build/stair-snes --experimental-audio --audio-counters \
  --experimental-raster-scroll
python3 tools/gameplay_route.py --platform snes --core /path/to/snes9x_libretro.so \
  --rom build/stair-snes/native-prototype.sfc --steps 21 \
  --actions tools/routes/cv3-stair-room.json --out build/stair-snes/check
```

Omit `--experimental-raster-scroll` for the preceding renderer. Omit both audio
flags for silence. Never distribute input-replay or stress-test builds as an
interactive release. Starting from a clean boot avoids old-save-state mismatches.

## Unfinished

Full-speed execution, cycle-faithful audio/PPU/mapper timing, all rooms and
characters, bosses/endings/death/restart paths and physical SNES validation remain
open work. Later unclassified paths can still halt. The two partial scanlines
and moving-frame differences explicitly preclude a perfect-port claim.
