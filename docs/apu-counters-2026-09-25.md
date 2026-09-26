# Optional audio envelopes and note counters — 2026-09-25

This continues tested revision `5656d453416b0e800c774c2009f5719d4918a43e`.
The port is still incomplete and roughly half speed. This is an audio-correctness
increment, **not** a performance improvement or a claim of a perfect port.

## Implemented

`--experimental-audio --audio-counters` enables pulse/noise envelope decay,
constant-volume selection, envelope looping and restart, all 32 length-table
entries on four channels, length-halt bits, disable/reload semantics, and the
triangle linear counter. Every high-register write is processed, including a
repeat of the same value. Enabling a previously disabled channel does not reload
its old length. `$4015` reads return the modeled length-active bits 0..3.

Both direct WRAM veneers and generic COP writes invoke the same event handler.
The direct handler preserves guest A (including the high accumulator byte), X,
Y, P, D, DBR and stack balance. C0 execution continues through the existing COP
fallback. Source-only diagnostic counters occupy previously unused WRAM
`$0AA0..$0AF1`; the saved guest context at `$0B00` is unchanged.

The feature is deliberately **opt-in**. Without `--audio-counters`, an audio
replay build is byte-for-byte identical to a build of the prior source using
the same input/trace/options. The silent and legacy-audio fallbacks remain.

## Important timing boundary

The bridge does not track original CPU cycles. It advances four sequencer
opportunities after each logical game NMI. Four-step mode clocks Q/QH/Q/QH;
five-step mode clocks Q/QH/Q/none/QH. A five-step `$4017` write immediately clocks
Q/H in this model rather than reproducing the hardware's CPU-cycle delay.
This contract makes notes decay and stop; it does not establish accurate
inter-write timing, exact tempo, or NES waveform equivalence. Audio still follows
the slowed game. Frame/DMC IRQ status and DMC-active status are not implemented.
Sweep, accurate noise mode/rates, DMC, expansion sound, mixer nonlinearity and
oscillator phase/retrigger fidelity remain incomplete.

## Fresh tests

- **127 unit tests passed**, including explicit envelope-divider, looping,
  restart, constant-volume, triangle and mode-transition expectations.
- **486 independent NES/SNES register records (1,944 compared bytes)** matched
  across direct, generic and C0 execution. The original procedural fixture tests
  every length value, expiry, halt, disable, no-resurrection, repeated writes and
  store flags. It repeatedly requests explicit five-step clocks, with NOPs longer
  than the real reset delay. This is an event-semantic oracle, not a periodic
  cycle-accuracy test.
- **324 completed audio updates / 6,480 state bytes** matched the separately
  implemented Python counter contract in direct, generic and nested-NMI stress
  cases. Actual SNES DSP PCM confirms fading, retriggered output, and all-zero
  output in eight selected silence windows. The direct fixture's loud-envelope
  RMS is about 2,543 versus 1,047 in the later soft window. Signal levels alone
  do not establish authentic timbre.
- **Five selected gameplay captures / 286,720 pixels** match the prior renderer.
- The ordinary-controller startup/walk/jump/attack route passes. A fresh
  15.37-second stage capture has SPC ready=1, fault=0, 2,282 command acknowledgments
  and no full-scale PCM samples. It records live DSP output, not a soundtrack
  played by the ROM.
- The existing longer route completes **100 steps / 10,000 additional game
  updates**, taking 20,977 SNES frames including startup, without a diagnostic
  halt. Much remains in room 1-02; this is not full-stage or whole-game coverage.

## Performance cost

Identical trace, fixed input and unmodified independent Snes9x core:

| Interval | Guest updates | Prior audio build | Counter-enabled audio |
|---|---:|---:|---:|
| Walking | 120 | 228 | 236 |
| Jumping | 25 | 48 | 49 |
| Attacking | 25 | 50 | 50 |
| Settling | 60 | 118 | 120 |

Walking throughput is about **3.4% lower**, not faster. The new work costs CPU
time and remains optional. The ratio is 1.967 display frames per game update.
No emulator overclock or game-logic frame skipping was used.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_apu_matrix.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/apu-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace build/route-nes/trace \
  --out build/counter-audio --experimental-audio --audio-counters
```

The matrix uses original procedural input only. Game-derived ROMs, screenshots,
traces and audio remain private. `--input-replay` and the stress flags are testing
options and are not present in the supplied interactive build.

The length/status oracle is the separately built, unmodified FCEUmm core; the
SPC output oracle is the separately built, unmodified Snes9x core, at the pinned
revisions in `toolchain.md`. Counter-event behavior was cross-checked against
FCEUmm's authored `src/sound.c` implementation. No emulator implementation code
was copied into the new 65C816 module.

See [machine-readable evidence](apu-counters-verification.json).

## Remaining work

The largest remaining gaps are full-speed execution, cycle-faithful audio and
mapper/raster timing, comprehensive routes/characters/bosses/endings, and actual
console validation. Unclassified execution can still halt. This checkpoint
reduces several specific sound errors; it is not a completed CV3 conversion.
