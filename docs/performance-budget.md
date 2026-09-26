# Performance-budget checkpoint — 2026-09-26

Baseline source: `712b68783f5ea0291d37a091bbce8780e66099bf`.
This checkpoint changes measurement tools and the completion roadmap, NOT the
SNES runtime. It claims no additional game speedup, boss clear or release.
See [completion gates and priorities](completion-roadmap.md).

## Fresh baseline, not a collection of unrelated earlier numbers

The original input, fixed-input adapter and recovered 10,763-entry private trace
are held identical. Enabled options are native controller, inline-table dispatch,
counter-free access bookkeeping, experimental audio/counters/sweep/raster, fill
correction and coalesced nametable DMA. This is a bounded early-game replay; the
trace is not the larger union used in other coverage reports.

| Interval | Tagged game frames | Display frames | Extra display frames | Per-update display spacing |
|---|---:|---:|---:|---|
| Walking | 120 | 147 | 27 | 93 one-frame, 27 two-frame |
| Jumping | 25 | 39 | 14 | 11 one-frame, 14 two-frame |
| Attacking | 25 | 44 | 19 | 6 one-frame, 19 two-frame |
| Settling | 60 | 72 | 12 | 48 one-frame, 12 two-frame |

All 231 consecutive presented tags are captured in the video callback. There are
no missing tags or changed images under repeated tags in this run. One-display-
per-tag is a provisional short-test target, not proof that every original NES
update is intended to occur that way. Final speed qualification must use paired
original-NES update timing and preserve original intentional behavior.

## New caller-aware cost attribution

The diagnostic Snes9x patch now attributes completed COP interception spans to
the ORIGINAL execution bank and CPU address. The preceding flat profile could
identify an expensive host helper but not distinguish which banked game callers
paid its cost. That information is needed for whole-block replacement instead
of repeatedly tuning an isolated instruction handler.

The walking diagnostic window attributes 53.72% of elapsed master clocks to host
code, 37.97% to guest code and 8.30% to WRAM wrappers; 8,820 clocks are unassigned
out of 52,890,094. Guest code includes a state-changing wait loop, not entirely
useful workload or safely removable idle time.

There are 8,081 completed COP calls consuming 10,623,786 attributed master clocks
(20.09% of the window). This is an OVERLAPPING view of the flat costs, not another
20.09% to add to the host/guest/wrapper totals. The busiest individual host helper,
QuickLDA_IY, occupies 6.35%; ConvertSingleObject and ConvertObjects together occupy
7.64%. These are flat symbol-range attributions, not full call-tree percentages.

The probe retains bank identity, rejects overlapping starts, keeps partial spans
out of completed-call totals, and handles short nested-interrupt returns without
ending a COP span prematurely. It includes serviced DMA/refresh and dispatched
nested interrupts, not just base opcode cycles. It does not yet attribute direct
JSL wrappers to original callers or provide a full semantic call graph.

Post-retro_run diagnostic windows and callback presentation windows differ:
walking/jumping/attacking/settling diagnostics span 148/38/45/72 display frames;
presented-image intervals span 147/39/44/72. These boundaries are labeled and never
mixed to claim a speed change.

## Verification completed locally

- 299 unit tests pass, including a compiled and executed C++ test of COP span
  accounting, nested returns, changed return banks, partial spans and reset.
- The diagnostic and unmodified SNES core produce identical image hashes, tags
  and delivery-frame positions for all 231 frames: 13,246,464 pixel positions.
  This is diagnostic calibration, NOT NES-versus-SNES visual equivalence.
- An authored CPU fixture passes 180 independent NES-versus-SNES records on each
  core. The plain and diagnostic SNES cores also match all 131,072 WRAM bytes,
  frame count, image hash and audio-frame count at fixture completion. The probe
  observes 36 complete COP calls with no overlaps. This validates the fixture,
  not the accuracy of every future measurement or physical-console behavior.
- The current game replay has CPU overclocking disabled and sprite-flicker
  reduction disabled. No new native runtime or gameplay code is introduced.

Game-derived data, detailed banked callsite profiles and cadence recordings remain
in ignored build directories. Public CI uses only authored procedural fixtures.
`performance_budget.py` rejects mixed ROMs, missing/duplicate frame tags,
nonincreasing delivery positions and invalid clock accounting. Its serial cost
projection is explicitly not a scheduling forecast.

## Reproduce

Build a diagnostic core from a clean copy of the pinned Snes9x revision; do not
apply V2 over V1 or load/reset states during measurement. Keep an unmodified core
for the actual cadence and independent reference checks.

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_frame_costs.py /path/to/clean-pinned-snes9x
make -C /path/to/clean-pinned-snes9x/libretro -j2
python3 tools/verify_cost_probe.py --nes-core /path/to/fceumm.so \
  --plain-core /path/to/plain-snes9x.so --probe-core /path/to/probe-snes9x.so \
  --out build/probe-calibration
python3 tools/performance_budget.py --core /path/to/plain-snes9x.so \
  --rom /path/to/private-fixed-replay.sfc \
  --build-manifest /path/to/private-native-build.json --out build/cadence.json
```

The actionable next performance step is to identify and replace the largest
proven block among the costly callers, then remeasure walking AND combat. A first-
boss clear remains the next coverage gate. The full roadmap is not marked done
by this tool/test checkpoint.
