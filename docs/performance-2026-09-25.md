# Measured native-bridge performance checkpoint — 2026-09-25

This is an optimization of the existing early playable prototype, **not a
complete or full-speed CV3 port**. Audio remains absent. No physical-console
validation has been performed.

## Measured result

The same pinned, unmodified Snes9x recovery core ran both builds. The benchmark
paces input by guest NMI counts and counts emulated SNES video frames, not the
host computer's wall time. Source input, coverage trace and test route were held
constant. The baseline was freshly rebuilt from the recovered `ac738df` source;
`bfe12bc` adds only the session-recovery report.

| Sample | Guest frames | Baseline SNES frames | Updated SNES frames | Speed ratio |
|---|---:|---:|---:|---:|
| Stage idle | 60 | 303 | 190 | 1.595x |
| Walk right | 120 | 608 | 388 | 1.567x |
| Jump right | 25 | 132 | 87 | 1.517x |
| Attack | 25 | 130 | 88 | 1.477x |
| Settle | 60 | 302 | 191 | 1.581x |

The walking sample is approximately **56.7% faster than the previous prototype**
(or 36.2% fewer SNES frames). It still takes about **3.23 SNES frames per guest
frame**, so it is substantially slower than the original game's intended rate.
This is not a claim of a speedup over the NES original.

Five selected final captures compared exactly: **286,720 RGB pixels checked,
zero mismatches**. This does not establish frame-by-frame or full-game equivalence.
Hashes and exact counts are in `performance-results.json`. Game screenshots,
ROMs, RAM dumps and extracted content remain in ignored local build directories.

## Changes implemented

- Enable FastROM and execute host interrupt/compatibility code through its fast
  bank mirror. Synthetic guest interrupt return frames retain the correct bank.
- Add indexed-zero-page fast paths that explicitly wrap the effective address
  and execute the native operation while preserving guest registers and flags.
- Add range-checked indirect-read fast paths for ordinary RAM and raw original
  ROM. Hardware addresses fall back to the existing compatibility code.
- Add narrow serial-joypad-read and supported MMC5 bank-write fast paths. A bank
  write updates both the data bank and the saved program bank for the return.
- Avoid unchanged nametable scans, palette reconversion and unnecessary uploads.
  OAM/palette upload routines now set their source bank independently.
- Copy NES RAM-backed sprite pages using the SNES CPU's WRAM-to-WRAM block move.
- Intercept indexed RAM accesses whose base can cross the NES 2-KiB mirror boundary.
- Add reproducible benchmark comparison and optional host instruction profiling.
  The profiling core is not used as the independent correctness oracle.

## Verification

- **58 Python unit tests passed.**
- Existing independent NES/SNES CPU+mapper fixture: **180 records / 720 bytes**,
  zero mismatches.
- Eight deterministic stress seeds: **856 records / 3,424 register-and-flag bytes**,
  zero mismatches; **2,048 OAM-copy bytes**, zero mismatches.
- Stress checks require counters proving the enabled fast paths actually ran.
- Regression cases cover live bank changes from switchable code, index/pointer
  wrapping, input serialization, hardware fallback and memory-result flags.
- The slow-ROM build with all COP fast paths disabled also passed the independent
  fixture comparison; the generic path is retained for diagnosis.
- The gameplay benchmark reaches early stage one without an unknown-code fault.
  It does not test every level, character, route, death or restart sequence.

Two assembler pitfalls were found and corrected during development: indexed
loads used for raw ROM lookup must be explicitly absolute (`a:`), and immediate
bank values in ca65 block moves use `#`. Failed experimental builds were not
adopted as the final checkpoint. The OAM regression would reject the incorrect
bank encoding, and live bank-switch regressions reject a stale return bank.

## Reproduce locally

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_native.py --rom original/CV3.nes --trace build/trace --out build/native
python3 tools/benchmark_native.py --core /path/to/snes9x_libretro.so \
  --rom build/native/native-prototype.sfc --out build/native/benchmark
python3 tools/fastpath_fixture.py --seed 0 --out build/stress
python3 tools/build_native.py --rom build/stress/fixture.nes --trace build/stress --out build/stress/snes
python3 tools/verify_native_cpu.py --nes-core /path/to/fceumm.so \
  --snes-core /path/to/snes9x_libretro.so --fixture build/stress --out build/stress/verification
```

For controlled fallback testing, `build_native.py` accepts `--slowrom`,
`--no-quick-zp`, `--no-quick-indirect`, and `--no-quick-io`.

Optional profiling: run `tools/instrument_snes9x.py` against the pinned Snes9x
source in `toolchain.md`, rebuild that separate core, and pass `--labels
build/native/native.lbl` to `benchmark_native.py`. The reported instruction
frequencies are not cycle percentages or complete performance attribution.

Remaining work includes tighter frame scheduling, more hardware-operation
translation, broader gameplay coverage, raster/vertical-scrolling corner cases,
and a sound implementation. Original hardware accuracy is not inferred merely
from passing these emulator tests.
