# Guarded native inline-table dispatch

Continuation of `3bb9a9ceb7d1805bb355857defa051b48212a9d3`.
This remains an incomplete, trace-bounded NES-to-SNES compatibility bridge.
No intermediate game download is being issued. Original ROMs, assets, audio,
private instruction traces and generated game binaries remain outside this repo.

## Implementation

The optional `--native-inline-dispatch` build recognizes one completely classified
6502 inline-table dispatch idiom in the fixed final program bank. Only classified
JSR operands are redirected. It does not hard-code the supplied game's function
address or remove the original routine. Eight calls qualify in the tested game
input. A generated WRAM wrapper executes in the caller's program bank while the
data bank still selects the separate unmodified original-ROM mapping.

The wrapper accepts only guest-NMI context and a return-address/table base in
$8000..$FF00. In that domain both indirect reads are ordinary native ROM reads;
the two separate per-instruction compatibility entries are unnecessary. It
re-emits the original algorithm directly, retaining selector and INY wraparound,
all four scratch bytes, accumulator/index/status behavior, and consumption of
the inline-table JSR return address. Unsupported contexts tail-jump to the original
body. C0 execution and builds without direct calls retain the original path.

The optional profiling counter at $09B0 records wrapper entries. Disabling
profiling still removes it without removing unknown-code stops, mapper checks,
interrupt safety, frame counters, or actual audio-state counters. The option is
off by default. A procedural ROM built with the option omitted is byte-identical
to the baseline built with the same input and settings.

This is a small whole-routine replacement, not a complete native-engine rewrite.
The separate unpublished indirect-load flag-merge experiment is not included.

## Independent tests completed

GitHub run `36258742764` passed on tested integration commit
`872fa58060073e85f1cbd055038fe63f8865c2cb`. Its archived source was downloaded and
all eight implementation, test, and integration files matched the locally tested
bytes exactly.

- **283 unit tests passed**, including actual assembler/build option checks.
- **45 independent NES/SNES configurations passed: 1,992 records and 7,968
  register-and-flag bytes, zero mismatches.** All 256 selector values occur
  across the supported map pairs; this is not every Cartesian combination of
  CPU state, selector, table address, map, and stack position.
- Cases check scratch output, relative stack balance, selector wrap, original
  data reads, counter-free builds, disabled/no-direct paths, outside-NMI and C0
  fallback, slow ROM, two extra stack depths, and forced interrupt stress.
- Table bases $FEFF/$FF00 take the shortcut; $FF01/$FFF7 correctly use the
  original routine. These boundary fixtures leave the NES interrupt vectors
  intact. All 24 boundary records match independent NES execution.
- An indirect jump to original code absent from the classified trace still
  stops with fault 1 at the authored test target $A1:F780, both with the option
  enabled and disabled. Its success marker is not reached.
- The retained independent runtime-safety suite passed **32 configurations,
  4,224 records, 16,896 register-and-flag bytes, and 1,024 OAM bytes**. Existing
  counter-free and audio/interrupt stress checks also passed. These are scoped
  event/CPU tests, not cycle-accurate sound or graphics certification.

The first stack test compared absolute cross-platform stack positions inside
interrupts. The preceding runtime failed the same eight comparisons because the
native interrupt frame includes a bank byte. The corrected fixture measures the
stack change across the dispatch call on each platform and requires that change
to be zero. Both failing captures were retained locally; the test was not changed
to tolerate a leak. A later matrix expectation was corrected for the actual C0
map selected without its alias flag; that case properly uses the original path.

## Fresh private gameplay regression

With identical private trace, fixed game-frame inputs, counter-free execution,
native controller, experimental audio/counters/sweep/raster, fill correction,
coalesced background uploads, and the unmodified Snes9x core:

| Interval | Game updates | Baseline display frames | Dispatch option enabled |
|---|---:|---:|---:|
| Walking | 120 | 149 | 147 |
| Jumping | 25 | 39 | 39 |
| Attacking | 25 | 44 | 44 |
| Settling | 60 | 74 | 72 |

Walking throughput improves **1.36%** and settling **2.78%**. Jumping/attacking
are unchanged. Walking still takes **1.225 display frames per game update**.
This is not full speed, a speedup over the original NES, or a whole-game result.
No emulator overclock or skipped game-logic update was introduced.

Five selected captures match the preceding SNES renderer. A separate callback-
tagged comparison matches hashes at **all 231 consecutive presented frame IDs
916..1146: 13,246,464 pixel positions**. This is baseline-SNES versus candidate-
SNES regression, not evidence that every pixel agrees with the original NES.
Existing raster discrepancies are not fixed by this change.

Fresh ordinary-controller runs also complete the **31-step approach plus 84
named outdoor/respawn actions** on the original NES and both SNES builds. Each
SNES result matches all five selected area/camera/player fields at every endpoint:
**420 field values and 756 bytes, zero differences**. The candidate takes
**15,124 display frames versus 15,242** in the baseline, approximately **0.78%
higher throughput** on this route. That result must not be replaced by the
shorter benchmark's improvement. No new boss clear or later-stage completion
is claimed. Route fields are not full-memory, pixel, or audio equivalence.

This pass's trace unions the earlier 10,763-entry private trace with the freshly
recorded guarded route, yielding 11,214 classified entries. The prior 11,553-
entry union also included a different legacy-clock run. These input sets must
not be confused with each other or treated as full-game coverage.

## Reproduction and limits

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_native_dispatch.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --previous-root /path/to/source-3bb9a9c \
  --out build/native-dispatch
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/private-trace \
  --out build/native-dispatch-game --experimental-audio --audio-counters \
  --audio-sweep --experimental-raster-scroll --no-runtime-counters \
  --native-controller --coalesced-nametable-dma --fix-fill-cache \
  --native-inline-dispatch
```

The first two commands use only authored procedural data. The last requires the
user's original ROM and matching private trace; do not add replay or stress flags
for ordinary play. The workflow independently builds pinned unmodified FCEUmm
and Snes9x sources, saves partial progress on failure, and publishes integration
to its development branch only after the checks pass.

First-boss and full-game coverage, full-speed operation, exact raster and sound
timing, sampled DMC audio, other unimplemented sound behavior, and physical-SNES
validation remain outstanding. Unused stack-memory contents and arbitrary
interrupt/stack-wrap cases are not certified by these tests. Unknown code can
still deliberately stop. No completed project is ready for user verification.
