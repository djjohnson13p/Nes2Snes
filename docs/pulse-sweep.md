# Pulse sweep checkpoint

This is an unfinished native CV3 port, not a perfect conversion or a full-speed
result. This change completes a new, opt-in pulse-sweep implementation against
source revision `65c371bfce6cc08d5402d07af7e24a5dcb02ff29`.

## What changed

`--experimental-audio --audio-counters --audio-sweep` adds pulse timer sweeps,
channel-specific negative arithmetic, divider and repeated-control-write reload
behavior, and target-overflow muting (including with sweep enable cleared).
The actual swept period is separate from the last-written register shadow.
Low/high timer writes preserve the other half of the swept period. The existing
length/envelope/linear-counter model and original SPC driver remain in use.

The new state occupies previously unused WRAM `$0AF2..$0AFF`; it does not overlap
the saved guest context at `$0B00`. Direct, generic and C0 fallback paths all
process the same write events. Sweep is optional. Omitting `--audio-sweep` yields
a byte-identical ROM to the preceding rendering/audio checkpoint using the same
trace and options.

The interrupted transfer at `6db9f89` contained only part 1 of 4 and could not be
validated as a complete patch. No unsupported claim is made that it was applied.
This checkpoint uses a freshly implemented and freshly tested module instead.

## Verification executed locally

- **170 Python unit tests passed**, including exhaustive sweep target arithmetic
  over both channels, 2,048 periods and all eight shifts with both signs.
- **54 independently executed NES/SNES cases, 108 pulse period values**, matched.
  The NES oracle is the pinned, unmodified FCEUmm core; its tagged FCS sound state
  supplies the actual internal periods. Fixtures use explicit five-step reset
  clocks, with NOPs exceeding the write delay and no automatic guest NMI. This
  establishes event semantics, not cycle-accurate periodic timing.
- **486 length/status/store-flag records (1,944 bytes)** matched the independent
  NES core with sweep enabled across direct, generic and C0 paths.
- **420 completed audio updates, 11,760 state bytes**, matched a separately
  implemented Python model in direct, generic and forced nested-NMI cases.
  Actual SNES DSP output is audible in the designated tone window and all-zero
  in six designated silence windows per case. The Python model is not itself an
  independent NES hardware oracle.
- **Five selected gameplay images, 286,720 pixels**, match the prior SNES
  renderer after matching presented game frames. These are not all-frame tests.
- The ordinary-controller startup/walking/jumping/attacking route passes with
  live sound. Its 15.87-second PCM capture has no full-scale samples and no SPC
  mailbox fault. This establishes output, not authentic timbre.
- The existing **31-step approach plus 57-action staircase route** completes.
  Game-state and candidate player X/Y bytes match the previous SNES checkpoint
  at all 57 endpoints. This is neither a boss clear nor whole-game validation.

Raw game-derived images, traces, audio and ROMs stay outside the public repository.
Machine-readable measurements are in `pulse-sweep-verification.json`.

## Performance

Identical logical-frame input, trace and independent Snes9x core:

| Segment | Game updates | Previous renderer/audio | Sweep enabled |
|---|---:|---:|---:|
| Walk | 120 | 237 SNES frames | 239 SNES frames |
| Jump | 25 | 50 | 50 |
| Attack | 25 | 50 | 50 |
| Settle | 60 | 120 | 120 |

Walking throughput is about **0.84% lower**. This is a sound-behavior improvement,
not a speedup. The port still runs near half speed in this sample.

## Reproduce

With Python, NumPy/Pillow, ca65/ld65 on PATH, and the pinned independent cores:

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_sweep_matrix.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/sweep-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/trace \
  --out build/sweep --experimental-audio --audio-counters --audio-sweep \
  --experimental-raster-scroll
```

The matrix needs no commercial ROM. The interactive build requires the user's
original ROM and matching trace. Do not enable test replay or stress flags in
the interactive build.

Reference checked: the authored sweep, frequency-mute, register-write and state
serialization implementation in FCEUmm `src/sound.c` at
`236ccdfc911e84c60fea6b9d0699c2d440a8de14`. The new assembly/model are original;
no emulator implementation was imported into the runtime.

## Still unfinished

The bridge advances approximate sound clocks per game update, not per original
CPU cycle. Exact APU timing, phase/retrigger behavior, noise waveform/rates,
DMC samples, expansion sound and nonlinear mixing remain incomplete. Partial-row
raster/mask differences and the documented reference-emulator disagreement remain
unresolved. Full-speed gameplay, all routes/characters/bosses/endings and physical
SNES verification remain outstanding. Unclassified execution can still halt.
