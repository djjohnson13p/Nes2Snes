# Guarded update clocks and outdoor/respawn coverage

Baseline source: `8428ab0321c7f55b15950ed3e80acd79095465a7`.
This checkpoint improves test alignment and observed gameplay coverage. It does
not modify the native runtime, establish a speedup, or complete a stage/boss.
All commercial ROM bytes, execution arrays, emulator states, images and sound
remain outside this public repository. The route contains controller inputs only.

## Why the previous paired route diverged

The old NES route adapter counted entry to the NMI handler. The original handler
has a busy/reentrancy check before its full-update path. Counting an entry that
takes the skip branch as an update is not the same as counting a full update.
The old adapters also used different startup waits: 120 NES display frames versus
waiting for the first native update and then advancing 120 game updates.

A longer route exposed the distinction. At named checkpoint 67 the screen-space
player coordinates agreed, but the candidate horizontal-camera field differed
by 45. The old comparison of player X/Y alone missed this. A diagnostic timing
offset eliminated the differences on the reached prefix, but that offset was
not retained as a solution, and neither the original ROM nor guest RAM was edited.

The new explicit `--clock-mode guarded` recognizes the first straight-line
`LDY zp / BNE forward / INC same-zp` guard in the fixed-bank original NMI handler.
It counts entry to the guard-clear path rather than every interrupt entry. For
the supplied original this is `$E064`, not NMI entry `$E053`. Unknown control flow,
a changed guard, or an out-of-range branch is rejected. This is deliberately a
narrow recognizer, not a proof that any arbitrary game's guard means one update.
Both guarded adapters start from their first update and then advance 120 updates.
The SNES adapter continues using the existing game-update counter. No manual
per-game offset, ROM patch, guest-memory edit or removed fault guard is involved.
The default remains `legacy` so earlier reports can still be reproduced. Never
mix legacy and guarded results when making a paired state comparison.

## New reproducible route and trace coverage

`tools/routes/cv3-outdoor-respawn.json` retains the 57 staircase actions and adds
27 outdoor actions, following the existing 31-step approach. Candidate actions
were explored with ordinary buttons and saved-state planning in the NES reference,
then the accepted sequence was replayed from clean boot on both systems. The
acceptance evidence does not resume the game from a planning state.

Two real unknown-code stops were retained: `$AC:8E5A` with the original trace,
and `$AF:8B57` after the first expansion. Original NES execution added 613 and
then 177 observed instruction entries: **10,763 to 11,553, an increase of 790**.
The normal classification/unknown-code guard remains enabled. Extending observed
coverage is not evidence that every byte is understood or the entire game works.

With guarded alignment and the expanded trace, both runs finish all **84 named
checkpoints**. Five selected fields match at every endpoint: game state, four
candidate area bytes, two camera bytes, and player X/Y. That is **420 field values
covering 756 bytes**, not a whole-RAM or every-frame equivalence test. The paired
route exercises an outdoor death-and-respawn sequence and finishes back at the
room's start with player X=16, Y=167. It does **not** establish a successful next-room
crossing, first-boss clear or game completion. Some action names were retained
from exploration and should not be interpreted as evidence of their intended goal.

The legacy comparison is retained as a failing diagnostic: eight mismatched
checkpoints among 75 comparable endpoints, with an incomplete native run.
`route_evidence.py` cannot report success for a matching but failed/empty prefix.
It rejects mismatched inputs or clocks and compares camera/area state as well as
player position. A synthetic camera-only difference is a required negative test.

## Evidence and what each oracle proves

- **272 unit tests pass**, including strict guard recognition, input/marker
  validation, camera-only failure, incomplete-prefix rejection and atomic-write
  failure. Existing actual assembler checks were run, not skipped.
- An entirely authored alternating-guard NES fixture passes **two initial-guard
  cases and eight snapshots**. Counts at the recognized entry agree with the
  independent program's update counters; total interrupt counts demonstrably
  overcount. All **16,384 NES RAM bytes** match the unmodified reference core.
  This checks instrumentation/clock selection, not cycle accuracy for CV3.
- Replaying the exact recorded host-frame inputs in unmodified FCEUmm reproduces
  the instrumented NES's **84 images (4,816,896 pixels) and 172,032 RAM bytes**,
  with zero differences. These are **NES-versus-NES** instrumentation checks,
  not a claim that the SNES renderer matches those images.
- The independent NES-versus-SNES route result is the narrower **84-endpoint,
  756-byte selected-field comparison** described above. Sound, pixel accuracy,
  all-frame RAM identity and hardware timing are not certified by that result.
- The retained procedural runtime/CPU/fault/audio-stress suite is rerun separately.
  See `route-clock-verification.json` for its counts, hashes and scopes.

The public CI workflow runs the authored fixture, unit suite and retained safety
checks without a commercial ROM. Private game-route measurements are recorded
separately and must not be described as having run in public CI.

## Durable progress

The route runner atomically replaces `progress.json` after each complete approach
step and each named action. It retains input segments, completed endpoints, clock
policy and fault location. A final report is written on success or a caught
failure; trace-export failure is also a failed result. Atomic replacement prevents
truncated JSON from masquerading as a completed checkpoint. It does not prevent
a service interruption, automatically resume computation, or diagnose ChatGPT's
missing-response incidents. Partial progress never counts as a passing route.

## Reproduce with the original private inputs

Use Python/NumPy/Pillow, ca65/ld65 and the pinned cores from `docs/toolchain.md`.
The old private 10,763-site trace is needed for the two-pass coverage expansion.

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_update_clock.py --probe-core /path/to/fceumm_probe.so \
  --reference-core /path/to/fceumm_reference.so --out build/update-clock

# Capture both historically explored timing paths; original ROM is read-only.
python3 tools/gameplay_route.py --platform nes --core /path/to/fceumm_probe.so \
  --rom original/CV3.nes --steps 31 --actions tools/routes/cv3-outdoor-respawn.json \
  --base-trace /path/to/old-trace --out build/legacy-reference
python3 tools/gameplay_route.py --platform nes --core /path/to/fceumm_probe.so \
  --rom original/CV3.nes --steps 31 --actions tools/routes/cv3-outdoor-respawn.json \
  --clock-mode guarded --base-trace build/legacy-reference/trace --out build/reference
python3 tools/build_native.py --rom original/CV3.nes --trace build/reference/trace \
  --out build/native --experimental-audio --audio-counters --audio-sweep \
  --experimental-raster-scroll --no-runtime-counters --native-controller \
  --coalesced-nametable-dma --fix-fill-cache
python3 tools/gameplay_route.py --platform snes --core /path/to/snes9x_libretro.so \
  --rom build/native/native-prototype.sfc --steps 31 \
  --actions tools/routes/cv3-outdoor-respawn.json --clock-mode guarded --out build/native-route
python3 tools/route_evidence.py --reference build/reference \
  --candidate build/native-route --out build/selected-state-comparison.json
python3 tools/verify_reference_route.py --core /path/to/fceumm_reference.so \
  --rom original/CV3.nes --source build/reference --out build/unmodified-reference
```

## Still open

This pass changes no runtime instruction handler and makes no new speed claim.
Full-speed operation, precise raster/audio behavior and DMC, complete levels,
characters, bosses, restart paths and endings, and physical-console validation
remain unfinished. A correctly aligned death/respawn test is real additional
coverage, but it is not a replacement for a first-boss completion route.
