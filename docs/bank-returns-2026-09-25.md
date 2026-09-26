# Bank returns, indirect loads and a longer route

This continues source revision `21c62a3dd8ac1f26f85dc9b57664945cfe698e65`.
It is still an incomplete, approximately half-speed port with approximate audio.

## New CPU paths

Classified STA/STX/STY writes to the three supported live PRG selectors can now
use WRAM veneers. The veneer preserves full A, P, X, Y, D and stack balance,
updates DBR, and extends the near-JSR return frame with the newly selected PBR.
RTL then resumes at the original continuation in the new ROM mapping. Execution
bank C0 keeps the existing COP path because its low memory is not WRAM-mirrored.
Unsupported C000/fixed selectors retain a deliberate diagnostic halt.
`--no-bank-direct` disables this optimization.

A host NMI now rejects a saved guest PC inside a WRAM veneer before touching the
saved guest context. This matters after CODEBANK has changed but before the
veneer returns: using the new PBR to resume that old WRAM PC can enter unmapped
memory in bank C0. The test-only `--stress-bank-switch` delay forces interrupts
inside precisely that window. The positive fixture completes all 197 register
and stack records; removing only the early-PC gate produces a fault at C0:11F5
after 50 direct bank calls. The delay is absent from interactive builds.

The common LDA (zero-page),Y path has a separate load-only handler. It retains
zero-page pointer wrapping, 16-bit effective-address wrapping, 2-KiB RAM aliases
and the existing hardware fallback. It updates only N/Z, leaving the saved high
accumulator byte and other flags intact. `--no-specialized-indirect` restores the
shared arithmetic/load path. No CPU overclock or game-update skipping is used.

## Verification performed locally

- 109 unit tests passed.
- 2,603 independent NES/SNES CPU/PPU/mapper records, containing 10,412 compared
  register-and-flag bytes, matched. This includes three 197-record mapper/stack
  fixtures, three 90-record indirect-load fixtures, the interrupt-stressed bank
  fixture, legacy fallback checks and the prior opcode/PPU/mapper regressions.
- 160 animated object frames (81,920 object bytes) matched the procedural model.
- The four existing audio configurations passed: enabled, silent, legacy direct
  calls and forced nested NMI. These are tone/mute tests, not full APU fidelity.
- All five selected render-aligned gameplay images matched the previous build:
  286,720 pixels, zero mismatches. This is regression against the previous SNES
  renderer, not proof of every-frame agreement with the NES original.
- A fresh ordinary-controller audio build completed the early gameplay route;
  its captured output had no mailbox fault and no full-scale PCM samples.

## Measured frame intervals

Same logical-frame input, same unmodified Snes9x core, compared to a fresh build
of 21c62a3. Numbers are emulated console frames, not host-machine wall time.

| Interval | Game updates | 21c62a3 | This checkpoint |
|---|---:|---:|---:|
| Walk right | 120 | 237 | 228 |
| Jump right | 25 | 50 | 48 |
| Attack | 25 | 50 | 50 |
| Settle | 60 | 120 | 118 |

Walking throughput improves about 3.95%; it still takes 1.9 SNES frames per game
update. A separate live-controller benchmark measured 232 walking frames; its
input/presentation phase differs, so it is not substituted into the fixed-input
comparison. Neither result is full speed or faster than the original NES game.

## Longer gameplay route

The previous classified trace stopped at guest AF:831C, logical frame 2394, after
reaching room 1-02. A new original-NES execution trace observes that instruction
and 216 other previously unobserved instruction entries. The merged trace has
8,928 observed entries; it is not complete recovered source.

With that evidence added, the SNES build completes 100 route steps / 10,000
additional game updates after startup without a diagnostic halt. The run uses
20,805 SNES frames including startup. Much of the route remains in room 1-02;
it does **not** establish complete-level, boss, death/restart or full-game
coverage. The trace and game-derived screenshots/states remain private.

`tools/gameplay_route.py` reproduces this bounded route and merges only observed
instruction counts/CPU addresses from the NES oracle. It rejects conflicting
physical-to-CPU mappings and marks retained I/O summaries as base-pass data.

```sh
python3 tools/gameplay_route.py --platform nes --core /path/to/fceumm_probe.so \
  --rom original/CV3.nes --base-trace build/trace --out build/route-nes --steps 100
python3 tools/build_native.py --rom original/CV3.nes --trace build/route-nes/trace \
  --out build/route-native --experimental-audio
python3 tools/gameplay_route.py --platform snes --core /path/to/snes9x_libretro.so \
  --rom build/route-native/native-prototype.sfc --out build/route-snes --steps 100
```

## Remaining limitations

Full-speed operation, faithful envelopes/length counters/sweep/noise/DMC audio,
all rooms/characters/bosses/endings, more complete mapper/raster behavior and
physical-console validation remain outstanding. Continued gameplay can still
reach an unclassified path and halt. Tests are evidence for their stated scope,
not a certification of a perfect port.

Machine-readable local evidence: [bank-returns-verification.json](bank-returns-verification.json).
The CPU manufacturer reference consulted for return/interrupt semantics is the
[WDC W65C816S datasheet](https://www.westerndesigncenter.com/wdc/documentation/w65c816s.pdf),
particularly sections 7.11 and 7.23. Runtime tests use independent emulator cores.
