# Original-instruction cycle accounting — 2026-09-26

## Provenance and boundary

The user merged PR #8 as `bd5f9689bef4cf65d70d81695ceaf1c2fb930901`,
with source tree `9ff34de2b80d4bb37737c39d2c0d5a391b709dc1`. The exact
merged Git object and all source files were restored; 351 baseline tests passed.

The preceding local-only idle-budget commit `19d2e8a...` was not present as a
complete saved workspace. Its blocked fixture upload was not retried. This is
**new, separately tested instruction-accounting work**, not a recovered copy of
that package. Its earlier test totals are not carried into this report.

This checkpoint implements a native 65C816 **instruction-cost primitive**, a
separate Python cost model, and an independently measured original-NES timing
oracle. It does not install a guest scheduler, advance the game's random state,
patch a seed, or change the production runtime. `native.s` and `build_native.py`
do not reference the new native include. No gameplay speed improvement or boss
clear is claimed.

## What is now implemented

`tools/guest_cycles.py` describes the base and conditional execution cost of all
151 documented NMOS 6502 opcodes on the NES 2A03. Unsupported opcodes fail closed;
translated 65C816 COP bytes cannot be interpreted as original instructions.
Inputs contain original bytes and **pre-instruction** registers. Indirect-Y read
costs require a captured zero-page pointer; the model performs no bus read.

Taken branches include their taken and page-cross penalties, calculated from the
post-operand PC with 16-bit wrapping. Indexed reads distinguish page crossings
from fixed-cost stores and read/modify/write instructions. The NES decimal flag
does not introduce 65C02 timing. Stack operations, BRK and both JMP forms retain
their documented instruction costs. Hardware interrupt entry is not BRK execution
and is accounted separately in the observation-window checker.

`snes/src/guest_cycles.inc` implements the same contract on an actual SNES CPU.
It consumes a 14-byte descriptor at `$1840`; `$1850..$1851` are scratch. It returns
a cost and explicit status, preserves the original descriptor, and preserves
caller A/X/Y/D/DBR/P and stack balance. The caller must own that scratch region;
this location is a fixture ABI, not an allocation in the current game runtime.
The native routine does not execute the described instruction, schedule an
interrupt, or claim that its own SNES execution time equals that guest cost.

## Independent execution evidence

The oracle does **not** use the project's cost tables. Authored NES programs
execute each selected instruction in pinned FCEUmm; a bounded read-only observer
records core timestamps before and after actual execution. The observer reads
mapped instruction bytes and zero-page RAM directly, not through emulated bus
callbacks. A separate unmodified core must reproduce RAM, image hash, video
callbacks and audio-frame counts for every case.

Fresh local acceptance:

- **379 unit and assembler tests pass** (351 baseline plus 28 new tests).
- **366 independently measured cases cover all 151 documented opcodes.** Both
  the Python model and native SNES routine match every measured duration.
  Branch tests include taken/not-taken, forward/backward and page-cross cases;
  indexed tests include noncrossing, crossing and 16-bit effective-address wrap.
  This is not every Cartesian combination of operands, flags and memory mapping.
- Native execution rejects **all 105 unsupported opcode bytes**, plus **seven
  missing indirect-Y pointer snapshots**. Caller context is verified with all
  four M/X combinations and decimal set, including accumulator high-byte,
  direct-page, data-bank and stack preservation.
- Two actual mutated native routines fail the comparisons: one discards a page
  crossing; the other undercharges base cost. Output and timestamp mutation tests
  also reject changed costs, changed context and missing observations.
- The **32-configuration retained runtime-safety matrix passes**: 4,224 records /
  16,896 register-and-flag bytes, plus 1,024 OAM bytes, with zero mismatches.

## Closing a complete instruction window

A second authored eight-frame program produces a continuous cartridge-instruction
record, including NMI handlers. Its independent handler counter records four
entries. The checker accounts for **75,143 executed instructions / 238,218
instruction cycles**, plus **28 interrupt-entry cycles**. The total equals the
observed **238,246-cycle span exactly**, with zero unexplained cycles. Sixty-four
pre-instruction snapshots from this window also pass the native accountant.
Together with the isolated cases, 430 valid native descriptors are checked.

The observed and unmodified cores match the entire final RAM hash, all eight
frame-image hashes, video-callback count and audio-frame count. Missing records,
wrong next PCs, unexplained gaps, negative timestamps and unknown opcodes reject
window acceptance. The window begins at its first recorded instruction; reset
entry and partial-frame extrapolation are not asserted.

**This accounts for observed interrupt entry; it does not predict the interrupt
polling point or decide when to deliver it.** The fixture disables maskable IRQs,
DMC and rendering. CLI/SEI/PLP polling subtleties, interrupt hijacking, mapper IRQ
phase and real PPU/NMI deadlines remain scheduling work.

An authored OAM-DMA negative control makes the boundary explicit. Its STA has a
four-cycle instruction cost, while the pinned FCEUmm core reports 516 elapsed
cycles. The checker rejects the extra 512 cycles rather than calling them idle
work or silently accepting the mismatch. This describes that core's DMA helper,
not a validation of real-hardware 513/514-cycle DMA alignment. DMA/DMC bus stalls
must be modeled and verified independently before supplying a live event-free
budget to an idle-loop optimization.

## Fresh private regression

The original input was recovered from the existing authorized checkpoint and its
full recorded SHA-256 verified. A fresh guarded 84-action trace followed by the
133-action route recreates the 12,359-entry trace and the unchanged SNES binary:
`0f4ac141190f4b7e0c3bbc1a691938c21872b133560e33bb4256f57c5b66f0ac`.

Clean-boot ordinary-controller NES/SNES runs still match all 133 checkpoints:
665 selected state fields / 1,197 bytes, plus 133 independently counted player
health bytes. All three Block 1-03 destination predicates pass. Explicit RNG
comparison still fails at 131 endpoints. That failure is preserved: the new
accountant is not installed in the game scheduler and cannot fix it by itself.
These private runs are local evidence, not public CI gameplay coverage. No ROM,
private trace, commercial images or game-derived executable is published.

## Reproduce and resume

Read `engineering-status.md` and `idle-state-audit.md` as well. The new public
workflow builds the pinned plain/observed NES cores and plain SNES core, runs the
full matrix, window and negative controls, retains runtime-safety checks, and
archives the exact tested source and machine-readable evidence. The observation
window is archived compressed for inspection; no partial run counts as a pass.

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_cycle_observer.py /path/to/pinned/fceumm
# Rebuild that core, retaining the independently built plain copy.
python3 tools/verify_guest_cycles.py --nes-plain /path/to/nes-plain.so \
  --nes-observed /path/to/nes-observed.so --snes-core /path/to/snes9x_libretro.so \
  --out build/guest-cycles
python3 tools/verify_guest_cycle_windows.py --nes-plain /path/to/nes-plain.so \
  --nes-observed /path/to/nes-observed.so --snes-core /path/to/snes9x_libretro.so \
  --out build/guest-cycle-windows
```

Next integrate original-cycle accounting into trace-bounded blocks and handler
transitions, with explicit DMA/DMC and interrupt polling/deadline models. Calling
this primitive on every original instruction is not a demonstrated performance
solution. Preserve fault guards and use the startup-to-Block-1-03 RNG mismatch as
an acceptance test; never copy expected seeds or infer full speed from test counts.
The missing 117/298-action source artifacts and a verified SNES boss clear remain
separate open coverage work. Request the user's merge only after the actual new
pull request's checks pass.

Timing references: NESdev's [6502 cycle times](https://www.nesdev.org/wiki/6502_cycle_times),
[CPU interrupts](https://www.nesdev.org/wiki/CPU_interrupts), and the pinned
[FCEUmm instruction implementation](https://github.com/libretro/libretro-fceumm/blob/236ccdfc911e84c60fea6b9d0699c2d440a8de14/src/x6502.c).
