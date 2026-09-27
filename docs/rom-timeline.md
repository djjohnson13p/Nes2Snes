# Immutable cartridge reads on the protected timeline

## Starting point and scope

This work is based on PR #13's exact published RAM-profile source,
`efb4eafbd564cdd5a3fa7d4e864d72d3b5b4434b`, tree
`32cb380688fc8ed09b9151e92b465f300899edd6`. Its 292 archived files reconstruct
that tree, and a fresh baseline run passed 467 tests. PR #13 was not silently
modified while adding this follow-up. Its previously pending pulse-sweep workflow
was rerun on the same source; all ten of its workflows then reported success.

The new explicit `nrom-32k` profile adds **immutable NROM-256 data reads** to the
procedural execution prototype. It is a fixed mapping, **not MMC5 bank switching**
and not a change to CV3's production scheduler. It is separate from both the
omitted original profile and the `internal-2k` profile. The profile's original
cartridge program/data is authored input, never expected execution output.

## Implementation

The original 32-KiB cartridge image is stored at SNES `$01:8000`, separate from
translated execution code in bank zero. It includes the same authored program,
data, boot code and vectors supplied to the NES reference. Every fixture checks
that these original bytes match exactly. Reading program bytes as data therefore
does not accidentally read their translated counterparts.

`TimelineResolveROM` admits mapped RAM and immutable cartridge data for the 42
covered read opcode/addressing forms. RAM mirrors resolve to the existing 2-KiB
region before access. Indexed/indirect reads use the actual pre-instruction
registers and zero-page pointer; the original indirect-Y base also supplies the
existing conditional-cycle accountant. An address wrapping from ROM into RAM is
allowed only when both its preliminary region and final target are supported.
Unmapped and hardware-register regions remain guarded.

Indirect jumps can read their pointer from RAM or original ROM. The pointer high
byte follows the NMOS within-page wrap, including the `$xxFF` case. The resulting
execution target still has to be an admitted original instruction entry. This
does not permit execution of unobserved data or arbitrary generated code.

Stores and read/modify/write instructions targeting ROM stop with status 5 before
guest mutation or retirement. This is an unsupported-operation guard, **not a
claim that an original NROM cartridge faults on writes**. No mapper write,
bus-conflict, open-bus, dummy-read or first-RMW-write behavior is emulated here.

Sparse fixture data has strict address, encoding, total-size and overlap checks.
It cannot overlap the original code, the authored boot region, or vectors.
The added address-mode/write scratch remains inside the existing host-NMI
snapshot. The routine uses the prototype dispatcher's address/register contract;
it is not a standalone caller-preserving API.

## Fresh execution evidence

The complete local matrix passes **97 authored plans and 206 native scenarios**:
97 ordinary native runs, 97 free-running host-NMI runs and 12 targeted host-stress
runs. At **6,386 dependent instruction boundaries**, all **13,282,880 bytes**
match independent original-NES execution. Each boundary includes all 2,048 guest
RAM bytes and the existing 32-byte register/clock/request record.

The cases cover two variants of each of 42 ROM-read forms, sampled guest
interrupts, reads of original code and vector bytes, both halves of the cartridge,
16-bit effective-address wrapping, high indices, and two indirect-ROM jumps.
The 93 no-request reference plans also match a separately built unmodified NES
core's final RAM/image hashes and video/audio frame counts.

The **109 host-enabled scenarios witness 4,037 SNES vblank NMIs** in unmodified
Snes9x. Tests exercise loaded values, unsaved arithmetic state, cycle accounting,
and nested host workers. Final protected scratch matches the corresponding
no-host native controls. These are emulated host hardware interrupts, not
physical-console results.

Three actual broken executables are rejected: reading translated rather than
original code, selecting the wrong ROM half, and disabling the write guard.
Five unsupported-access cases stop after exactly two completed instructions;
each preserves all 2,048 guest-RAM bytes and 14 logical register/clock/request
bytes from the last completed endpoint. Faulted prefixes do not pass acceptance.

All **483 unit and assembler tests pass without skips**. Separate builds from
PR #13 and this source produce **262 byte-identical retained-profile binaries**:
18 original-profile and 244 internal-RAM-profile fixtures. Build identity is
separate from execution comparisons and is not counted as additional gameplay.
The 32-configuration runtime-safety matrix also passes: 4,224 records / 16,896
register-and-flag bytes plus 1,024 OAM bytes, with fault guards and existing audio
stress retained. Additional clean-source/retained-matrix results are recorded in
`rom-timeline-verification.json` and the pull-request evidence ledger.

## What remains unchanged

`native.s` and `build_native.py` are unchanged. **No new CV3 replay was performed
for this checkpoint**; prior private route results remain historical evidence,
not fresh tests of this profile. The previously recorded random-state mismatch
is not fixed, and no speed improvement, boss clear or recovered missing route
is claimed. The default and internal-RAM executable-identity checks above concern
authored test programs, not a newly rebuilt commercial game.

The guest interrupt policy remains the explicitly authored after-instruction
request stream used by the preceding prototype. It does not establish physical
NES pin sampling, PPU/mapper deadlines, interrupt hijacking or DMA/DMC interleaving.
Matching state and instruction cost is not a claim of matching external bus cycles.

## Reproduction and next integration

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_rom_timeline.py \
  --nes-plain /path/to/unmodified-fceumm.so \
  --nes-probe /path/to/2048-byte-timeline-fceumm.so \
  --snes-core /path/to/unmodified-snes9x.so \
  --out build/rom-timeline
```

The workflow builds the pinned reference/stimulus cores, executes the new ROM
matrix and retained RAM/runtime-safety matrices, and archives exact tested source,
authored inputs, generated assembly, raw authored PRG, captures and negative
controls. No commercial ROM, trace, image or game-derived executable is included.
A new workflow result must be checked for its actual commit before requesting merge.

Next add checked mapper state and transitions to this separation of original data
from translated execution, with independent mapping tests. Hardware-I/O handlers
and independently established original event/stall timing remain required before
this profile can become a CV3 scheduler. The per-instruction diagnostic dispatcher
has not demonstrated a full-speed implementation.
