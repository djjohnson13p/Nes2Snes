# Queued-video performance checkpoint — 2026-09-25

**This is an improved early-game SNES prototype, not a complete CV3 port.**
It remains silent and slower than the original game's intended update rate.
The public repository contains source and test fixtures, not the supplied game
ROM, its graphics, generated game binaries, screenshots or memory dumps.

## Measured improvement

The controlled comparison holds the input script, logical input frames, source
ROM, execution trace and independent Snes9x core constant. Captures are aligned
to the logical game frame actually presented, not merely the most recently
started guest NMI. The baseline is `46e7469` with only the same input replay and
presented-frame counter instrumentation added. Its original dispatch, rendering
and blocking upload remain unchanged.

| Fixed-input interval | Game updates | Previous SNES frames | New SNES frames | Relative speed |
|---|---:|---:|---:|---:|
| Walk right | 120 | 386 | 242 | 1.595x |
| Jump right | 25 | 87 | 56 | 1.554x |
| Attack | 25 | 87 | 50 | 1.740x |
| Settle | 60 | 190 | 120 | 1.583x |

Walking is **59.5% faster than the previous checkpoint**, requiring 37.3% fewer
SNES frames. It still consumes **2.017 SNES frames per logical game update**.
This is not full speed, and it is not a speedup over the NES original.

All five selected replay images match the previous renderer exactly:
**286,720 RGB pixels checked, zero mismatches**. These are selected captures,
not a comparison of every displayed frame or every game state.

An ordinary build, with test-input substitution absent, independently completes
the controller-driven startup/walk/jump/attack route. Its walking interval is
242 SNES frames versus the previous live benchmark's 388; the new idle, jump,
attack and settle intervals are 120, 56, 50 and 120 frames respectively. That
benchmark samples input at host callback boundaries; changing performance can
change the game frame that consumes a button transition. It is therefore a
separate smoke/performance test, not the pixel-equivalence oracle. Do not mix
its 388-frame baseline with the controlled replay's 386-frame baseline.

The final interactive ROM is 4,194,304 bytes, SHA-256
`306d081db9cc7c32eacb48ffb8daca0a945628cc15bcd3b396dbdd524904ae62`.
It is generated privately from the supplied ROM. This is not the replay ROM.
Exact input/core/ROM hashes, counts and source hashes are in
[pipeline-verification.json](pipeline-verification.json).

## Implemented changes

- Prepare graphics buffers without blocking until the following vertical blank.
  A subsequent host NMI uploads the completed buffers before starting another
  guest NMI. Immutable snapshots cover the live scroll, fine-X, display mask and
  sprite CHR-bank fields used by presentation. The frame ID is recorded only
  after presentation. Large transfers retain forced-blank protection.
- Reuse unchanged converted sprites. Cached raw OAM entries are compared against
  new entries; changing sprite size or pattern selection invalidates the cache.
- Bypass the generic full-context COP interpreter for supported PPU stores and
  selected status/controller/mapper accesses. The existing PPU write handlers
  retain their register semantics. Unsupported cases keep the generic path.
- Add per-game-frame test input, a presented-frame counter, a reproducible old
  renderer build and a comparison tool that refuses mismatched input/core/frame
  identities. Replay input is compiled out of interactive builds.
- Retain `--synchronous-video`, `--no-object-cache`, and `--no-quick-ppu` controls
  for isolating changes. The earlier CPU fast-path disable controls also remain.

The scheduling change introduces a queued presentation stage. No claim is made
that input latency improved, or that the bridge reproduces cycle-exact NES
interrupt timing. Reduced waiting, not a higher emulated console clock, drives
the measured gain. Instruction-frequency profiling guided the changes but is
not presented as cycle-percentage attribution.

## Verification executed

- **75 Python unit tests passed.**
- Independent FCEUmm versus Snes9x CPU/mapper/PPU comparison:
  **1,130 records / 4,520 register-and-flag bytes, zero mismatches**. This includes
  the base 180-record fixture, eight 107-record fast-path seeds and two 47-record
  buffered-PPU seeds. The eight raw-OAM copies also match: 2,048 bytes.
- The PPU cases cover register aliases, buffered reads, increment-by-32,
  palette aliasing, status-latch reset, disconnected controller 2 and preservation
  of store registers/flags. Rendering is disabled in that fixture; it is not a
  raster-accuracy test.
- An independently coded sprite-format model checked **160 completed frames /
  81,920 converted OAM bytes**, with zero differences. All four size/pattern
  combinations ran, along with flip, priority, visibility and position changes.
  Both conversion and cache-reuse counters must be nonzero or the test fails.
- A generic/synchronous build with all CPU quick paths and sprite caching off
  passed the 47-record PPU oracle as well.
- The ordinary controller build and deterministic replay were both executed in
  the pinned unmodified Snes9x core. Test-only profiling was not the oracle.

A proposed automatic-joypad-completion wait produced a live-startup fault and
was rejected before the final build. This is why successful fixed-input tests
are not treated as a substitute for testing the actual interactive ROM. That
experiment does not establish a diagnosis of all interrupt-timing corner cases.

## Reproduce

The assembler, emulator revisions and local ROM/trace preparation are described
in [toolchain.md](toolchain.md) and [native-bridge.md](native-bridge.md).

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_native.py --rom original/CV3.nes --trace build/trace --out build/live
python3 tools/benchmark_native.py --core /path/to/snes9x_libretro.so \
  --rom build/live/native-prototype.sfc --out build/live/benchmark

python3 tools/replay_native.py --write-input build/replay-input.bin
python3 tools/build_replay_baseline.py --rom original/CV3.nes --trace build/trace \
  --replay build/replay-input.bin --out build/replay-old
python3 tools/build_native.py --rom original/CV3.nes --trace build/trace \
  --input-replay build/replay-input.bin --out build/replay-new
for version in old new; do
  python3 tools/replay_native.py --core /path/to/snes9x_libretro.so \
    --rom "build/replay-$version/native-prototype.sfc" \
    --out "build/replay-$version/captures"
done
python3 tools/compare_replays.py --baseline build/replay-old/captures \
  --candidate build/replay-new/captures --out build/replay-comparison.json
```

The baseline builder requires the existing local Git history for `46e7469`.
It makes an isolated temporary source tree and does not modify the checkout.
Public CI runs procedural fixtures only; it does not download or publish CV3.

## Remaining limitations

Audio is unimplemented. Full-game, character, route, death/restart and unusual
raster/vertical-scroll behavior are not established. The prototype deliberately
halts on unsupported code or mapping rather than silently executing guesses.
No physical SNES or flash-cartridge validation has been performed. Further CPU,
PPU and scheduling work is still necessary to approach the intended game rate.
