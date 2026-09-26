# Guarded native controller routine and measured frame costs

Continuation of `a4bc07ac9d5de25c879e4ede64bd26d206d4bc3a`.
This is still an incomplete, trace-bounded port, not a full-speed or perfect game.
No commercial ROM, trace, screenshots, audio or derived game binaries are added
here. Public tests use an authored procedural input.

## A whole routine, rather than another per-instruction shortcut

The opt-in `--native-controller` build recognizes a fully classified, standard
8-bit serial-controller polling routine and changes only classified JSR call
operands to a guarded WRAM wrapper. It does not hard-code a game's function
address, rewrite the original body, or make unchecked code executable. Two call
sites qualify in the current private game build.

The wrapper requires a guest NMI context and X in 0..2. Other X values can alias
the routine's scratch bytes; those calls tail-jump to the untouched original
body. Calls outside guest NMI, C0 execution and builds without direct calls also
retain the original algorithm. The existing mapper validation, unknown-code
traps, interrupt gates and audio safety remain in effect.

Within the guarded domain, the replacement samples the existing physical-input
or fixed-game-frame replay path once and constructs the same output bytes,
scratch values, final serial-shift state, accumulator, indexes and flags as the
eight polling iterations. The second controller remains disconnected in this
bridge. This does not certify peripheral timing, multiplayer, dummy bus cycles,
cycle-exact input timing or unused stack-memory contents.

Omitting `--native-controller` reproduces the prior game ROM byte for byte with
the same original input, trace and build flags. Runtime profiling is optional;
its new routine-call count at WRAM $09A0 is not a safety check.

## New measurements and a rejected experiment

`instrument_frame_costs.py` adds elapsed master-clock attribution to a clean,
pinned Snes9x dispatcher. It accounts for scanline clock rollover and reports
unattributed time separately. The attribution includes DMA, HDMA and refresh
stalls serviced inside instructions; it is not a pure opcode-cycle percentage.
Guest PCs are aggregated across the supported mappings. Do not reset or load
states within a measurement interval.

The diagnostic core reproduced the unmodified core's five selected sample images,
delivered frame tags and frame counts. Final speed comparisons below use the
unmodified core, not the diagnostic build. Calibration of selected frames does
not establish that instrumentation is harmless on every possible path.

The baseline walking window included substantial guest frame-wait work and
compatibility overhead. The guest wait loop also writes memory, so it was not
replaced as though it were a semantically empty delay. A separate word/table
sprite-conversion experiment preserved the selected images but did not improve
display-frame throughput. That experiment was removed, not advertised as a gain.

For the diagnostic window sampled after emulator returns, baseline elapsed time
was 68,614,192 master clocks over 192 display frames. The controller replacement
used 53,604,974 over 150. These boundary samples differ from presented-image
intervals below and are not mixed when calculating the published speed ratios.
The current largest individually attributed host routine is the indirect-load
handler; substantial rendering and compatibility costs remain.

## Frame-labeling correction in the verification harness

The old replay sampler associated pixels with the *previous* post-`retro_run`
value of the presented-frame ID. Faster execution exposed that heuristic: it
could attach one game's image to an adjacent game's frame number. That produced
16,964 apparent changed pixels in the initial comparison.

The sampler now captures the runtime's presented-frame ID **in the video
callback**, when the corresponding image is delivered. A duplicate-frame callback
does not relabel old pixels. Unit tests exercise the callback boundary and reject
mixing old/new tagging methods. Both baseline and candidate were recaptured with
the new method. No image tolerance was increased and no mismatched rows were
excluded: all five whole images then match exactly.

This corrects the sampling association; it does not resolve the port's already
known NES-versus-SNES rendering differences.

## Verification performed locally

- **242 unit tests pass**, including recognition guards, scratch aliases, refused
  incomplete classification, call-only patching, callback tagging and diagnostic
  instrumentation checks.
- **25 independent NES/SNES configurations, 1,650 CPU/register records and 6,600
  register-and-flag bytes match with zero differences.** Eighteen button
  combinations, changing carry/overflow state, X=0..7/127/254/255, second-port
  state, scratch bytes, post-poll serial reads, counter-free mode, disabled
  replacements, disabled direct calls, C0, outside-NMI, slow-ROM and forced
  nested-NMI restore configurations are exercised. Opposite directions are not
  requested because frontends sanitize them differently. Execution counters
  confirm use of the new routine in the designated counted cases.
- The retained 32-configuration safety matrix passes: **4,224 comparison records,
  16,896 register-and-flag bytes, 1,024 raw OAM bytes**, unknown-code fault guards
  and the existing direct/generic/nested-NMI audio checks. These fixtures retain
  the default polling path unless their input contains the recognized routine.
- The retained 11-configuration indexed-memory matrix passes: **1,425 records /
  5,700 register-and-flag bytes**, zero differences.
- Five correctly tagged game captures match the preceding SNES renderer:
  **286,720 pixels, zero differences**. This is not an independent NES all-frame
  comparison.
- Fresh ordinary-controller runs complete the existing **31-step approach plus
  57-action staircase route** in both builds. All 57 selected player-position and
  game-state endpoints match. No new boss, character, stage or ending is certified.

Machine-readable, non-asset summaries are in `native-controller-verification.json`.
Each verification case writes progress; only the final matrix report claims all
configurations passed.

## Performance

Same private input and trace, audio/counter/sweep/raster settings, fixed logical
input sequence and unmodified Snes9x core. Both use `--no-runtime-counters`.

| Interval | Game updates | Previous display frames | Native poll display frames | Throughput ratio |
|---|---:|---:|---:|---:|
| Walk | 120 | 191 | 149 | 1.2819x |
| Jump | 25 | 42 | 39 | 1.0769x |
| Attack | 25 | 50 | 44 | 1.1364x |
| Settle | 60 | 106 | 74 | 1.4324x |

Walking is **28.19% faster** in this sample, but still needs **1.2417 display
frames per logical update**. Attacking still needs 1.76. This is not full speed,
not faster than the NES original, and uses no overclock or skipped logic frames.

The longer ordinary-controller route takes **12,540 rather than 13,495 emulator
frames**, a **7.62% throughput improvement**. That smaller result matters: the
walking improvement is not a whole-game speed figure. Approximate audio still
follows the game's execution speed; authentic timing/timbre is not established.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_native_controller.py \
  --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/controller-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/trace \
  --out build/native-poll --experimental-audio --audio-counters --audio-sweep \
  --experimental-raster-scroll --no-runtime-counters --native-controller
```

The first two commands need no commercial input. Do not add replay or stress
flags to the ordinary interactive build. The user requested no further partial
download packages; only source and scoped evidence are published to GitHub.

For profiling, use Snes9x `fae2fea08f74180759ef540ee94259213f503480`, apply
`python3 tools/instrument_frame_costs.py /path/to/snes9x`, then build its libretro
core. `profile_frame_costs.py` accepts `--core`, `--rom`, `--symbols`, `--start`,
`--end` and `--out`. Profile a fixed-input test build, not live human input.

## Outstanding

The whole game is not verified. Restricted mapping, unclassified code, incomplete
DMC and sound timing, existing raster/partial-row disagreements, below-full-speed
execution and physical-SNES testing remain open. This pass demonstrates one
useful whole-routine replacement; it does not prove that all remaining overhead
can be removed without further correctness work.
