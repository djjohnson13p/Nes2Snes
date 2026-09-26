# Roadmap to a complete, faithful CV3 SNES port

Baseline reviewed: `712b68783f5ea0291d37a091bbce8780e66099bf`.
This plan is for the supplied CV3 ROM on a standard SNES, not a universal NES
converter. It does not require a Codex handoff. No intermediate user download is
issued. The original ROM, private trace and derived game assets stay out of Git.

## What counts as progress

There are three independent tracks: **performance, gameplay coverage, fidelity**.
A passing test count is not a completion percentage. A coverage or correctness
checkpoint is not a speed improvement. A feature that the observed game never
uses is not a CV3 optimization. A baseline-SNES image comparison detects
regressions; only an aligned NES reference can support original-game fidelity.

The current bridge is useful scaffolding and a fallback. The plan is to remove
frequent instruction-by-instruction interception from proven hot game routines,
not to assume that many tiny handler optimizations inevitably yield full speed.
The native controller replacement already demonstrates the whole-routine method;
the smaller native dispatch replacement demonstrates why each result must be
measured rather than inferred from code size or processor capabilities.

## Completion gates

| Gate | Required deliverable | Evidence required to close it |
|---|---|---|
| G0: one reproducible performance baseline | Fixed ROM/trace/options/core hashes; short action intervals and a growing stress corpus; deadline/cadence and caller costs | Repeatable plain-core runs; calibrated diagnostic core; no mixing callback timing with post-emulator-return sampling |
| G1: full-speed first-stage slice | Opening, movement, combat, scrolling, first boss clear, stage transition and death/restart | Clean-boot paired NES/SNES routes; actual boss/exit predicates; no unknown-code stops; no additional port-induced lag in the required intervals |
| G2: complete game coverage | Every stage, route, character, boss, ending, password/menu and restart path | Versioned deterministic routes and state invariants; measured stress intervals; retained failures; explicit uncovered cases |
| G3: graphics and sound fidelity | HUD/playfield, scrolling, priorities, transitions, color behavior; all used voices/effects including DMC | Original-NES comparisons at correct event/frame boundaries; documented output conversion; no silently discarded rows, missing sounds or relaxed thresholds |
| G4: release qualification | Reproducible final build and complete documented test corpus | Two independent SNES emulators, long sessions, reset/controller checks, no unresolved release-blocking defects; physical-console status stated separately |

G0 now has caller-aware diagnostics and a per-presented-frame cadence measurement.
It is NOT finished for the entire game: heavy/boss/later-stage workloads are not
represented by the short opening replay. G1 remains open: a boss clear has not
been verified. G2-G4 remain open. A previous locally reported 91-action route is
not silently treated as merged or reproducible by this source checkpoint.

## Performance work: an explicit decision loop

1. Freeze the current candidate options and inputs. In the reviewed replay these
   include counter-free access bookkeeping, native controller and inline dispatch,
   experimental sound/counters/sweep/raster, fill correction and coalesced
   background uploads. Retain the default and fallback builds for comparisons.
2. Measure both total cadence and the costly callers. `performance_budget.py`
   records each delivered tag in the video callback. `profile_frame_costs.py`
   attributes elapsed master clocks and now retains the execution bank and PC
   of completed COP spans. These are two different measurement boundaries.
3. Select a block that actually dominates a failing interval. Near-term candidates
   are repeated indirect-read/compatibility sequences and the sprite/background
   preparation pipeline. Follow caller addresses to classified game routines;
   do not call an address a sound/player routine without semantic evidence.
4. Replace the whole operation when its preconditions are understood. Possible
   techniques are guarded native routines, larger-block translation that keeps
   address calculations/register state across several operations, and incremental
   graphics preparation that avoids repeated scans/conversions. Keep the original
   body or generic handler for unsupported contexts. Branch relocation, flags,
   raw-data reads, aliasing, bank changes and interrupts are correctness hazards
   to test, not reasons to skip validation.
5. Measure the target and regression corpus with an unmodified emulator. Retain a
   candidate when it removes a demonstrated correctness blocker or measurably
   improves the critical workload without violating behavior. A tiny improvement
   may be retained, but it does not close a full-speed gate. Two unsuccessful
   implementations of the same small tactic trigger a change of tactic, rather
   than an indefinite sequence of equivalent micro-optimizations.
6. Advance a speed gate only with matched original-NES update cadence. Do not
   overclock the emulator, skip required logic/render updates, disable sound,
   remove enemies, or replace a state-changing wait loop with a no-op. Intentional
   original timing/slowdown must be distinguished from port-induced delay.

The new short-replay baseline is 147 display frames / 120 tagged walking frames,
39/25 jumping, 44/25 attacking, and 72/60 settling. Attacking, not walking, is the
worst of these samples. Against the provisional one-display-per-tag target,
walking needs 18.37% less elapsed time (22.5% more throughput); attacking needs
43.18% less elapsed time (76% more throughput). These are arithmetic deficits,
not promised optimization gains or a whole-game frame-rate estimate.

One host indirect-load routine accounts for about 6.35% of the diagnostic walking
window. Halving its fixed-work cost would remove about 3.18% of that window in a
serial cost model. Scheduling and waiting can change nonlinearly; this projection
is not a hardware-speed ceiling or a forecast. It explains why a small helper
should not be our only performance plan. COP-span costs overlap the flat host
cost view and must NOT be added to it.

## Coverage work runs alongside speed work

The next coverage target is a real first-boss clear, not another arbitrary number
of checkpoints. Continue the route through room transitions, combat, boss defeat
and the following stage. Add code classification only from verified evidence;
keep unknown-code faulting active. Assert destination/boss/restart predicates,
not merely that two sessions stopped with equal positions. Preserve the original
reference trace and reproduce it in unmodified NES execution. After the first
stage is a reliable vertical slice, expand the same method to all route/character
combinations, with focused tests for new mechanics rather than redoing all tools.

Do not wait for perfect speed before extending coverage: new scenes reveal missing
mechanics. Do not wait for all-game coverage before improving a measured hot
subsystem: performance and coverage are parallel tracks with a shared regression
corpus. A faster incorrect result and a correct half-speed result both fail the
final gate.

## Fidelity work

Close the known raster/mask transition errors using event/scanline timing and
original-NES captures. Validate background and sprite priority, scrolling and HUD
behavior, and any overscan/color conversion explicitly. Agreement between two
versions of the SNES renderer is not enough. Reference-emulator disagreements
remain open investigations, not an opportunity to select whichever one passes.

Complete DMC playback and the used APU channel behaviors; improve event timing,
noise/phase/retrigger behavior and mixing. Move appropriate synthesis/sequencing
work to the SPC700 only when measured to help and independently checked. Musical
tempo must not be merely "correct for a slowed game." Different output hardware
means that bit-identical analog/PCM waveforms are not a sensible implicit promise;
any fidelity tolerance must be specified and justified, not invented after a fail.

## Release and reporting

A software-complete candidate must pass the recorded game corpus in at least two
independent SNES emulators, match intended gameplay timing, have no missing game
content or known release-blocking audiovisual defect, and rebuild from exact
source and private input hashes. Real-console testing cannot be claimed from
emulators; it requires access to hardware and is an explicit final verification
item. "Perfect" is not established by a finite fixture count.

Every checkpoint report states: track advanced; changed behavior; fresh measured
result; baseline and oracle; unchanged/failed gates; and published versus local
revision. Infrastructure work must name the optimization or defect it enables.
No more unrelated addressing-mode additions are prioritized over observed CV3
hotspots. No timeline or guarantee of uninterrupted chat execution is implied.
