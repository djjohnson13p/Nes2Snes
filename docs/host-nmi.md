# Host NMI context protection for the running timeline prototype

## Starting revision and purpose

The user merged PR #11 as `c53188e01a31f00eec331860be7f429e268ca9d6`,
with source tree `5fa2e0e1898fd5551cddc2e6bee28af862874149`. The exact signed
commit object and its complete source were restored. All 427 baseline tests
passed before implementation. The current local repository is shallow at that
merge; it is not presented as a complete historical clone.

The composed prototype previously disabled **SNES host NMI**. That left a real
integration prerequisite untested: host work must not corrupt partially updated
original-game registers, software interrupt frames, cycle-accounting scratch or
capture state. This checkpoint enables the SNES vblank NMI in the prototype and
provides a preserving entry/return envelope. It does not replace the original
NES event model or connect the prototype to the CV3 production scheduler.

## Implementation and explicit worker contract

`snes/src/timeline_host_nmi.inc` saves full native A/X/Y, including the hidden
accumulator high byte when M=1, plus D and DBR. The hardware interrupt frame
preserves P, PC and PBR. The envelope snapshots 132 bytes of live scratch onto
the native stack: `$1840..$187F`, `$18C0..$18DF`, `$1B02..$1B05`, and
`$1C00..$1C1F`. It restores those regions in reverse order and returns with RTI.
Each nested invocation owns its own stack snapshot; there is no single global
backup buffer to overwrite.

The fixture's host worker deliberately uses all four protected regions and
clobbers register widths, decimal state, A/X/Y, D and DBR. It **must** remain in
native mode, balance its stack, and leave original guest `$0000..$01FF`, output
bank `$7F`, the caller stack, and unrelated memory alone. Its only unprotected
writes are explicitly designated host service counters. This is a bounded
worker contract, not a sandbox for arbitrary interrupt handlers.

Two simultaneous host entries are supported. A third records an explicit host
fault before taking another scratch snapshot; the whole verification fails.
The worker's stack/time bounds matter: reserve at least 160 bytes of free native
stack per supported level, in addition to ordinary caller/worker needs. Tests
check low/high canaries and the lowest SP after the envelope snapshot. That
sample is not claimed to be continuous observation of every worker stack access.
Standalone tests also verify exact returned native SP.

`timeline_program.create_native(..., host_mode=...)` enables this only for the
procedural prototype. Omitted or explicit `None` keeps the previous generated
program unchanged. The production `native.s` and `build_native.py` do not import
or include the new code. No emulation-mode support or live renderer integration
is asserted by this checkpoint.

## Real host interrupts versus guest test requests

The host NMIs originate from the SNES vblank source in **unmodified Snes9x** after
enabling `$4200`. They are not software calls to the handler and are not injected
through emulator request APIs. The envelope acknowledges `$4210`.

Free-running tests let these interrupts occur without a deliberate stop. Separate
native WAI rendezvous expose loaded guest registers, unsaved ALU results, partial
register saves, cost-accounting work, partially pushed guest interrupt frames,
low-word clock updates, and a prepared capture header. Another mode waits for a
second vblank inside the first host worker, exercising nested hardware entries.
Wait-return PC witnesses and service/completion counters must prove that the
specified interruptions actually happened. A run with matching guest results
but zero host interrupts cannot pass this suite.

These WAI instructions are host-only stress instrumentation. They do not alter
the original authored guest program, feed expected states into it, or contribute
cycles to the original-game clock. They intentionally consume host display
frames and are not performance measurements.

The **guest** IRQ/NMI requests retain PR #11's authored after-instruction policy.
The separate fixture-only NES harness still supplies that test stimulus, while
original NES execution supplies the comparison states. Host NMI testing does
not turn this policy into physical NES pin sampling, PPU/mapper deadlines, or a
DMA/DMC timing model. The request harness is never used in private CV3 gameplay.

## Fresh local acceptance

The suite contains **451 passing unit/assembler tests**, with zero skips: the
427-test baseline plus 24 new tests. The new tests assemble every host mode and
all standalone register configurations, check invalid settings, and reject
incomplete, fault-bearing, malformed or vacuous observation reports.

The emulator matrix passes **65 host-interrupted scenarios**, comparing all
**7,280 dependent instruction boundaries / 3,960,320 guest-state bytes** with
fresh independent NES execution. The final protected scratch adds **8,580 exact
byte comparisons** against freshly executed no-host native controls. These runs
service **5,542 host NMIs**, including **672 nested entries**. **3,944 deliberate
wait-return sites** are witnessed separately from nested-worker returns.

Four standalone configurations test all 256 native P values, both bank-$00 and
bank-$80 execution, and single/nested host entry: **1,024 contexts**, covering
**13,312 register/context bytes plus 135,168 scratch bytes**, with zero differences.
All four M/X combinations, decimal and interrupt-mask states, nonzero D, both
DBR values, accumulator high byte, index widths, PBR and returned SP are checked.
These are declared boot inputs followed by actual execution, not injected
expected after-states.

Two additional clock-origin runs interrupt between the low-word addition/store
and carry propagation. They pass **224 dependent boundaries**, including a
nonzero high word. Only the declared original-clock origin is rebased; every
other state byte remains exact. This is counter-arithmetic verification, not a
new physical timing claim.

Three actual wrong binaries fail as intended: missing GT scratch restoration,
discarding the high accumulator byte, and disabling the host NMI source. The
last one still matches the original guest stream, demonstrating why equality
alone is insufficient. A separate real third-level nesting test reports the
expected fault while preserving the stack canaries. Faulted prefixes are never
counted as passing scenarios.

The first expanded local invocation found a sampler error: an uninitialized host
metadata byte in the **no-host control** was mistaken for a host fault. The run
was rejected. The control sampler now explicitly declares that it does not own
host metadata; NMI-enabled sampling still stops on that fault, and a no-host
report cannot be accepted as host-interrupt evidence. A regression test covers
both paths. Earlier failed output is retained locally and excluded from totals.

The existing complete 18-scenario timeline suite, its independent no-request
controls, clock-origin tests, executable mutants and native fault guards are
rerun by the new matrix. All **32 retained runtime-safety configurations** also
pass: **4,224 records / 16,896 register-and-flag bytes plus 1,024 OAM bytes**,
retaining unknown-code guards and audio stress. These are scoped tests, not a
percentage-complete metric or proof of arbitrary interrupt timing.

## Default and private gameplay regressions

All 18 default procedural native builds are byte-identical to separate builds
from the exact original merged source. The new optional feature does not silently
change the disabled path.

The authorized private original was restored from the saved raw-data checkpoint
and its full SHA-256 verified. Fresh guarded 84-action and 133-action NES runs
recreate the 12,359-entry observed trace. Fresh clean-boot NES/SNES comparisons
match all **665 selected fields / 1,197 bytes plus 133 health bytes** on the
133-action route, and all three destination checks pass on both platforms.
Unmodified NES replay reproduces all **7,626,752 pixel positions and 272,384 RAM
bytes** from the recording. This is a NES-probe check, not NES/SNES pixel identity.

The game binary remains
`0f4ac141190f4b7e0c3bbc1a691938c21872b133560e33bb4256f57c5b66f0ac`.
The explicit RNG comparison still **fails at 131 endpoints**. No random seed,
enemy spawn or mismatch tolerance was changed. No new boss clear, recovered
missing route, production scheduling fix, speed gain or physical-console result
is claimed. Private gameplay evidence is local, not public CI game coverage.

## Reproduce and continue

```sh
python3 -m unittest discover -s tests -v
# Build the pinned plain NES core, preserve it, then install only the existing
# fixture timeline harness and rebuild its separate stimulus core.
python3 tools/instrument_timeline_probe.py /path/to/fceumm
python3 tools/verify_host_nmi_matrix.py --nes-plain /path/to/nes-plain.so \
  --nes-probe /path/to/nes-stimulus.so --snes-core /path/to/snes9x.so \
  --out build/host-nmi
```

The new workflow archives the exact tested source, complete captures, generated
assembly, authored register inputs, mutation outputs and fault evidence. Existing
success summaries are removed when a new run starts. Check the actual candidate
revision's CI before asking the user to merge; a local result is not that CI run.

Next address physical original-NES event/stall timing and broaden mapping/I/O
transitions under an explicit experimental gate. This envelope removes the
prototype's host-NMI-disabled assumption within the stated worker contract; it
does not establish safe access patterns for the production renderer or fix the
known random-state divergence. Preserve this boundary rather than installing a
synthetic request schedule in the game.

Primary implementation references: the pinned Snes9x `cpuops.cpp` NMI/RTI paths
and `cpuexec.cpp` vblank event dispatch at revision
`fae2fea08f74180759ef540ee94259213f503480`, and the WDC W65C816S native-mode
programming model. The independent emulator outputs, not a copied table of
expected interrupt results, supply this checkpoint's execution evidence.
