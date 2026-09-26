# Optional access counters: measured overhead removed

Continuation of `a19a87c328e47e3603e3f049b605a85693e230c9`.
This remains an incomplete, trace-bounded port, not a full-speed or perfect game.

## Implementation

`--no-runtime-counters` compiles out the per-access **profiling increments** for
CPU compatibility dispatch, indexed/indirect accesses, direct I/O and mapper
veneers. A single `CountRuntime` macro emits exactly the preceding eight-byte
increment sequence when enabled, and no instructions when disabled.

The default remains counted so existing path-execution diagnostics continue to
work. The user-facing performance preview is built explicitly counter-free.
The counted ROM rebuilds byte-for-byte identically to the preceding checkpoint.

This does **not** remove mapper validation, unknown-code traps, fault diagnostics,
game/display/render frame IDs, audio envelopes/length/sweep counters, SPC mailbox
timeouts or sprite-cache behavior. Zero profiling values mean "not collected,"
not "no compatibility calls happened." The CPU verifier distinguishes these modes
and still checks the actual CPU/register outputs in both modes.

## Measured comparison

Same original input, trace, audio/raster options, fixed game-frame input and
unmodified Snes9x core. Wall-clock CPU time is not the performance measure.

| Interval | Logical updates | Counted display frames | Counter-free display frames | Throughput ratio |
|---|---:|---:|---:|---:|
| Walking | 120 | 225 | 191 | 1.1780x |
| Jumping | 25 | 46 | 42 | 1.0952x |
| Attacking | 25 | 50 | 50 | 1.0000x |
| Settling | 60 | 114 | 106 | 1.0755x |

Walking is 17.80% faster than the preceding prototype in this sample; it still
needs 1.5917 display frames per game update. There is no overclock or skipped
game-logic update, and no claim to outperform the original NES game. The longer
staircase route improves much less overall: 13,766 vs 13,495 emulator frames.
The short walking improvement must not be generalized to the entire game.

The separate ordinary-controller benchmark measured 229 vs 199 frames for walking.
Those input/timing adapters differ from fixed replay; the two measurements are
not mixed when reporting the controlled 225-to-191 improvement.

Five presented-frame-aligned images match the old SNES renderer: 286,720 pixels,
zero differences. The 31-step approach plus 57-action staircase route completes,
with selected state/player-position fields matching at all 57 endpoints. These
are regression checks, not independent-NES every-frame or full-game proof.

## Verification

- 200 unit tests pass, including actual ca65 byte-encoding checks for both modes.
- 32 independent NES/SNES configurations pass in counted and counter-free modes:
  4,224 CPU/register records, 16,896 register-and-flag bytes, and 1,024 raw OAM bytes.
- An explicit indirect jump into valid original code absent from the classified
  trace still raises fault 1 at $A1:F800 in **both** modes. The unchecked original
  code is not allowed to run to its success marker.
- Counter-free audio/state regressions cover direct, generic and forced nested-NMI
  modes. These compare to the existing separate sound-state model and actual DSP
  output, not a cycle-accurate NES sound oracle.
- The ordinary-controller audio capture contains live output, no full-scale PCM
  samples, no SPC mailbox fault and 2,282 acknowledged DSP commands. Authentic
  timbre and exact NES sound timing are not established.

See `runtime-counter-verification.json` for build/input/core hashes and the actual
results. The test runner writes a progress file after each completed configuration;
only its final verification report claims the whole matrix passed.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_runtime_counters.py \
  --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/runtime-counter-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/trace \
  --out build/counter-free --experimental-audio --audio-counters --audio-sweep \
  --experimental-raster-scroll --no-runtime-counters
```

Omit only `--no-runtime-counters` to get the counted diagnostic build. Do not add
input-replay or interrupt-stress flags to a normal interactive build. Public tests
use project-authored procedural inputs only; the original ROM, trace and all
game-derived binaries, images and audio remain private.

## Limits and priorities

No new level or boss clear is established in this pass. Partial-row raster
mismatches, incomplete sound/DMC timing, restricted mapping and classified-code
coverage, below-full-speed gameplay and physical SNES validation remain open.
See `engineering-status.md` for the architecture diagnosis and next priorities.
