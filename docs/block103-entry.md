# Newly authored Block 1-03 entry and indirect-CI repair — 2026-09-26

## Starting point and recovery boundary

PR #6 was merged as `0cd1df54868d9481f55c2e3388b7bd16eefc14f6`, tree
`5e9228b43fb6098b8cf1b7f9c447720ca5b2cfa0`. The restored Actions source matched
that tree exactly, and all 313 baseline tests passed locally. The private original
ROM was recovered from the user's existing checkpoint as documented in
`palette-reads.md`, with its full original SHA-256 verified before execution.

The exact earlier 117-action script remains unrecovered. The newly committed
`tools/routes/cv3-block103-entry.json` has **133 actions**, following the existing
31-step approach. Its first 70 actions preserve the outdoor route; the remaining
63 are newly authored ordinary-controller inputs. It is not a recovered, renamed,
or padded version of the missing route. The existing 84-action script remains
unchanged and deliberately retains its death/respawn coverage.

## New gameplay coverage, with fresh independent evidence

Save states were used to explore timings, not as acceptance starting points.
The selected sequence was then executed from a clean boot without RAM writes,
cheats, removed enemies, emulator overclocking, or disabled fault guards. The
final clean-boot NES RAM matches the successful exploration's entire 2 KiB.
The route crosses the rooftop, descends the opposite side, traverses the lower
passage and passes through the door into the screen labeled **Block 1-03**.
It stops at that entrance, not at a boss defeat or a stage clear.

Fresh results recorded in `block103-entry-verification.json`:

- The instrumented original-NES recording is reproduced by unmodified FCEUmm
  at all **133 endpoints: 7,626,752 pixel positions and 272,384 RAM bytes**, with
  zero differences. This validates the recording probe, not SNES graphics.
- Ordinary-controller SNES and NES runs match all **665 selected state fields /
  1,197 bytes** at those endpoints. Both runs complete with no native fault.
  These are area, game-state, camera and player-position fields, not all RAM.
- Three named waypoint predicates pass on both platforms. The final waypoint
  requires game-state 4, area bytes `0x02010100`, camera 0 and player position
  `(28,144)`, plus the observed common-RAM health byte `$003C = 8`. The preceding
  doorway waypoint and rooftop descent are checked separately. These numerical
  predicates are tied to visually inspected original-NES captures; area bytes
  alone are not claimed to be a universal HUD block-number decoder.
- The earlier 84-action route also passes with the expanded trace: **420 selected
  fields / 756 bytes**, no differences. The new contract rejects that old route
  rather than treating equal respawn endpoints as Block 1-03 completion.
- The trace unions the recovered guarded 11,214-site input with the clean-boot
  new route, adding **1,145 observed entries**, for **12,359 total**. Exploration
  traces and guessed instruction boundaries are not substituted for this clean
  recording. Full-game coverage remains false.

The new route uses 11,185 NES emulator calls/video callbacks. SNES uses 19,133
emulator calls and 19,134 video callbacks; those two counters are deliberately
not conflated. This is a longer route, not a before/after speed measurement.
The runtime source is unchanged by this checkpoint. No speed gain is claimed.
Existing raster/HUD discrepancies and approximate audio are still present.

## Destination gates instead of equal failures

`tools/route_milestones.py` checks a versioned contract bound to the exact ordered
input digest, repeated approach pattern, clock policy and step count. It requires
complete ordered captures and named state/RAM predicates, and rejects recorded
faults. Two identical but wrong destinations cannot pass merely by matching each
other. Unsafe or duplicate names, unknown fields, bool-as-integer values,
out-of-range common-RAM addresses, changed input, missing milestones and failed
prefixes are tested. The tool only reads captured RAM; it does not alter execution.

The final local suite has **327 passing tests**: 313 baseline, three additional
indirect-policy tests, and eleven destination-contract tests. These are not a
percentage-complete measure and are separate from emulator configuration counts.

## One post-merge CI failure, reproduced and repaired

The merged revision had 17 successful workflow runs and one failure. Run
`36270922954`, job `108484591266`, completed the independent indirect-X matrix's
40 configurations, then failed with `general: default ROM changed`. It still
required the corrected palette runtime to produce the pre-palette default binary
from `ad0648cf46e3a799ea55815c9b0015a765bd27ec`. The failed artifact is retained
locally, with its digest in the verification report. This is a real failing CI
run, not a claim that every merge check was green.

The ongoing indirect-X verifier now requires same-revision omitted-versus-explicit
False builds for the CPU and indirect-X fixtures. `quick_indirect_x` joins the
existing disabled-default and disabled-metadata checks. The old strict historical
comparison is still available with `--previous-root`; its one-byte failure test
remains strict. The workflow no longer invokes that historical invariant after
an intentional default-runtime correction. No register/pixel tolerance changed,
no failing runtime configuration was removed, and the downstream controller,
audio and runtime-safety suites remain required.

Fresh local execution passes **all 40 configurations / 5,440 records / 21,760
register-and-flag bytes**, covering every pointer offset, every X value and all
32 supported bank pairs. This is not their full Cartesian product. Both 4-MiB
same-source default-policy ROM pairs are byte-identical. Public CI can reproduce
these procedural checks without the commercial ROM; private game-route results
must not be attributed to public CI. Check each new commit's actual CI result.

## Reproduction and next work

Restore the private original input and the earlier trace using `palette-reads.md`.
The source-only route and milestone contract are now committed, so future
resumption does not depend on a lost interactive save state.

```sh
python3 -m unittest discover -s tests -v
python3 tools/gameplay_route.py --core /path/to/fceumm_probe.so \
  --rom original/CV3.nes --platform nes --steps 31 --clock-mode guarded \
  --actions tools/routes/cv3-block103-entry.json --base-trace /path/to/guarded-trace \
  --out build/block103/nes
python3 tools/verify_reference_route.py --core /path/to/fceumm_reference.so \
  --rom original/CV3.nes --source build/block103/nes --out build/block103/reference
python3 tools/build_native.py --rom original/CV3.nes --trace build/block103/nes/trace \
  --out build/block103/snes-build --experimental-audio --audio-counters \
  --audio-sweep --experimental-raster-scroll --no-runtime-counters \
  --native-controller --coalesced-nametable-dma --fix-fill-cache --native-inline-dispatch
python3 tools/gameplay_route.py --core /path/to/snes9x_libretro.so \
  --rom build/block103/snes-build/native-prototype.sfc --platform snes --steps 31 \
  --clock-mode guarded --actions tools/routes/cv3-block103-entry.json --out build/block103/snes
python3 tools/route_evidence.py --reference build/block103/nes \
  --candidate build/block103/snes --out build/block103/comparison.json
python3 tools/route_milestones.py --route build/block103/snes \
  --contract tools/routes/cv3-block103-entry.milestones.json --out build/block103/milestones.json
```

Next extend from the newly reproducible entrance through Block 1-03 combat and
an actual first-boss clear, then define and verify the stage-exit predicates.
Keep the failure samples and death/respawn path. Full-speed performance, broader
characters/routes/endings, DMC and remaining audio, accurate raster timing and
physical-console verification remain open. No complete-port or release claim.
