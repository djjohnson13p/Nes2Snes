# Bank-qualified MMC5 PRG execution on the protected timeline

## Source and integration boundary

Starting revision: the user's PR #14 merge,
`4c255f9754d8d1033223535a4cfd7003054b42a8`. Its Git tree
`16393811c94834b37aed8fab72ab73cb86cd8b5d` was reconstructed from the verified
source artifact, the exact signed merge object was restored locally, and all
483 baseline tests passed before editing. This is new work on that published
source, not recovery of a previous local-only experiment.

The new explicit **`mmc5-prg-rom`** profile connects MMC5 program-bank state to
the protected native timeline. It supports PRG-ROM modes **1, 2 and 3**, with
power-of-two original ROM sizes from 4 through 128 8-KiB banks. It does not
implement PRG RAM, graphics banking, ExRAM, mapper-generated interrupts, expansion
audio, DMA/DMC, or physical event/pin timing. Production `native.s` and
`build_native.py` are unchanged; this is not yet the live CV3 scheduler.

## What executes, rather than just being calculated

Authored original instructions write `$5100` and `$5114..$5117` using `STA abs`.
The native prototype updates its own mapper registers and effective slots, then
executes subsequent instructions using that state. A program's execution identity
is now **(physical PRG bank, original CPU address)**. Two banks can contain
*different* instructions at the same CPU address without the dispatcher confusing
them. Unknown bank/address combinations fault; a known address in some other bank
does not authorize execution.

The original immutable PRG image remains separate from translated code. Data
reads, indirect-pointer reads, instruction dispatch, and interrupt-vector reads
all use the current mapping. A `$5117` write can change the next instruction and
the vectors used by the next sampled interrupt. Calls and returns retain the
original evolving stack and obey whatever mapping the program has left active;
there is no automatic, incorrect restoration of a previous mapper bank.

The independent scenarios include switching between different functions at the
same address, changing the bank currently executing, interrupt entry through the
new bank's vectors followed by `RTI`, and fallthrough across an 8-KiB boundary.
The data matrix covers all 42 admitted cartridge-read opcode/addressing forms in
each supported PRG mode, every ROM-selector byte `$80..$FF` in the mode-2 lower
pair, both polarities of the final register's ROM/RAM bit, and six ROM sizes.
This is not the complete Cartesian product of every mode, register, operand,
interrupt phase and mapping.

## Explicit supported and refused operations

Mode 1 aligns the lower and upper 16-KiB pairs; mode 2 aligns the lower pair and
selects two independent upper 8-KiB banks; mode 3 selects four 8-KiB banks. Physical
ROM-size masking is applied after the mode's alignment. `$5117` always selects
ROM regardless of its high bit. Ignored mode bits do not change the mode number.

This profile deliberately refuses mode 0 and any `$5114..$5116` write selecting
PRG RAM, even if that register is inactive in the present mode. It also refuses
ROM writes, mapper-register reads, other hardware registers and unsupported
bank/address execution. These are **prototype guards**, not claims that the NES
hardware itself faults on these operations. Refused accesses do not retire or
mutate guest RAM/registers/clock/effective mapping. Resolving an indirect address
can first read ordinary guest zero page; zero preliminary reads are not claimed.

Only explicitly described original code is translated. Physical code ranges
cannot overlap, even through multiple virtual aliases; code crossing a bank or
vector boundary is rejected. Sparse bank data cannot overwrite admitted code,
authored boot code, or the final bank's vectors. Other banks can contain explicit
authored vectors for remapping tests. The test boot writes the known initial
mapper state before the recording window; hardware power-on register values are
not inferred from those declared inputs.

## Reference boundary: mode zero is not silently accepted

The pinned FCEUmm source's mode-0 path selects `PRGBanks[1]` (`$5115`), while the
MMC5 documentation assigns the 32-KiB ROM bank to `$5117`. The authored diagnostic
writes different selectors and independently observes effective banks **4,5,6,7**
in that core, rather than the documented **28,29,30,31**. A duplicate authored
code tail keeps execution defined after that discrepant switch; the emulator's
mapping code is not modified. Its observed and unmodified builds still agree.

This discrepancy is saved separately and is **not** counted as a correct mapping
case. The native profile rejects mode 0 before its register changes, rather than
copying the reference behavior or weakening a comparison. Supporting mode 0
requires resolving this oracle gap with an independently established reference.

References: [MMC5 banking specification](https://www.nesdev.org/wiki/MMC5) and
[pinned FCEUmm MMC5 implementation](https://github.com/libretro/libretro-fceumm/blob/236ccdfc911e84c60fea6b9d0699c2d440a8de14/src/boards/mmc5.c).

## Independent evidence design

The original NES executes the authored program and performs its own mapper
writes. Its normal CPU, mapper and interrupt dispatch remain unchanged. A small
read-only addition to the existing fixture observer records the effective ROM
banks directly from the core's mapped memory pointers—not from the project's
bank-selection model. Each endpoint contains all 2 KiB of guest RAM and a 32-byte
register/clock record, now including four mapped slots and the next execution
bank. Their values are strictly compared and bounds-checked.

Only declared boot inputs, cartridge bytes, code entries and the existing authored
request schedule enter native execution. No intermediate expected bank, register,
seed, stack, PC, memory or timing result is supplied. No-request plans additionally
compare the observed core against a separately built unmodified core. Each native
build's full original PRG region is checked against its corresponding NES input.

The existing real SNES vblank protection also encloses mapper registers and
address-resolution scratch. Free-running host-interrupted cases compare every
endpoint and the final protected scratch to no-host runs. Targeted cost, clock,
capture and nested-worker waits remain separate from original guest time. These
are unmodified-Snes9x hardware NMIs, not physical-console measurements or a new
original-NES physical interrupt scheduler.

A development smoke test found that the first draft placed mapper state at
`$1870`, already used by interrupt-class scratch. The strict per-instruction map
comparison failed. Mapper registers now occupy `$1871..$1875`; the test suite
pins the non-overlap with `GI_CLASS`, and dependent execution checks the result
again after every instruction. That failed run is not an acceptance pass.

See `mmc5-timeline-verification.json` for measured totals and the accompanying
pull request for the exact published commit and its actual CI status. Local
results and remote workflow results must not be conflated.

## Completed local acceptance

All **508 unit and assembler tests pass, zero skipped**, including the clean-source
run. The full mapper matrix passes **322 authored plans / 656 native scenarios /
20,336 instruction boundaries / 42,298,880 state bytes**. This comprises 322
ordinary runs, 322 free-running host-NMI runs and 12 targeted host-stress runs.
The 334 host-enabled scenarios witness **11,878 emulated SNES vblank NMIs**.
The 319 no-request plans also match an unmodified NES core. The original
observations contain 827 effective-slot changes; those are mapping observations,
not a cycle-cost or speed measurement.

All three actual executable mutations are rejected: PC-only dispatch, incorrect
16-KiB pair alignment and a stale NMI vector. Four actual guards reject mode 0,
PRG-RAM selection, a ROM write and execution in an unadmitted physical bank. Each
refused operation preserves all 2,048 guest-RAM bytes, 14 logical context bytes
and the four effective bank slots from the preceding endpoint. The known mode-0
oracle disagreement remains a separately recorded, non-passing accuracy result.

The retained NROM matrix passes **206 scenarios / 6,386 boundaries / 13,282,880
bytes**; the retained RAM matrix passes **512 scenarios / 15,872 boundaries /
33,013,760 bytes**. Both retain their executable corruption and access guards.
All 32 runtime-safety configurations also pass: **4,224 records / 16,896
register-and-flag bytes plus 1,024 OAM bytes**. The 359 previous-profile fixture
builds are byte-identical to separate builds from the merged baseline.

The final clean source revalidates every mapper capture and negative control.
Four representative emulator reruns, including remapped vectors under nested
host interruption and a 1-MiB cartridge, reproduce their complete original and
native captures and generated binary bytes. These are four new reruns, not a
second complete new emulator matrix. None of these procedural totals is private
CV3 gameplay evidence. Remote CI must still validate the published candidate.

## Reproduction and next work

```sh
python3 -m unittest discover -s tests -v
# Keep an unmodified reference core, and an ordinary 2048-byte timeline core.
python3 tools/instrument_mmc5_timeline.py /path/to/pinned/fceumm
# Rebuild to a separate mapper-observation core.
python3 tools/verify_mmc5_timeline.py \
  --nes-plain /path/to/nes-plain.so --nes-probe /path/to/nes-mmc5.so \
  --snes-core /path/to/snes9x_libretro.so --out build/mmc5-timeline
```

The workflow executes the mapper matrix and its guards/mutants, retains the fixed
ROM and RAM matrices and runtime-safety suite, and archives the exact tested
source plus complete authored captures and generated assembly. Commercial ROMs,
private traces, game images and game-derived executables are not included.

No fresh commercial-game replay is claimed here. The previous 133-action route
results remain historical; the known random-state mismatch is not fixed. The
next integration gates are required MMC5 RAM/I/O and graphics state, independently
verified event/stall deadlines, and an efficient live execution path. The current
instruction-by-instruction diagnostic dispatcher is not a demonstrated speed
solution, and there is no new boss-clear, full-game or physical-console claim.
