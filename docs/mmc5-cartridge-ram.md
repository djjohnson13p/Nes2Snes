# Banked MMC5 cartridge RAM on the protected timeline

## Provenance and execution boundary

Base: the user's PR #15 merge, `f08f634ab2120281851bd0871b5d79ed1956f740`,
source tree `4b4ad48d85d84b9ec6356c7157f69078524a650e`. The exact signed merge
object was restored locally and the 309-file source tree reconstructed from its
verified predecessor CI archive. All 508 baseline tests passed before changes.

The explicit `mmc5-prg-ram32` profile adds an EWROM-like **single 32-KiB RAM chip**
to the existing bank-qualified execution prototype. Four physical 8-KiB pages
are distinct. This is not a claim of every MMC5 board's RAM wiring, save-file
persistence, or production CV3 integration. The ordinary MMC5 ROM profile keeps
its prior guards and binary output. No commercial-game replay was performed.

## What now executes

Original `STA abs` writes to `$5102`, `$5103`, and `$5113` update the prototype's
own protection/page state. The already supported `$5100` and `$5114..$5117`
registers also permit supported cartridge-RAM selection in this new profile.
Modes 1/2 align the lower 16-KiB RAM pair; mode 3 selects the 8-KiB windows
independently. `$6000..$7FFF` follows `$5113`. Multiple CPU windows can alias the
same physical page, and remapping a window does not discard its prior contents.

The two low protection bits matter: writes are enabled only when `$5102 & 3 = 2`
and `$5103 & 3 = 1`. Upper bits do not create another lock mode. **A write while
locked is ignored, not faulted.** Read/modify/write operations still calculate
their original flags and retire their instruction cost while suppressing the
final memory write. This is architectural state behavior under the existing
no-within-instruction-event policy, not a reproduction of both RMW bus writes.

All 61 admitted external-memory opcode/addressing forms are exercised with both
writable and locked RAM. Indexed and indirect operations use actual evolving
registers and zero-page pointers, including wrapping and page crossings.
Indirect JMP can read a RAM-backed pointer and preserves the NMOS within-page
high-byte fetch. A RAM-derived destination still must select admitted ROM code;
**executing cartridge-RAM bytes as code remains unsupported and faults**.

Selectors for the absent second chip (bit 2 set in the RAM selector) are refused
before mapper mutation, even for currently inactive registers. That guard is not
an implementation of open bus. Mode 0, ROM writes, other hardware registers and
unadmitted code remain guarded. The final PRG window is always ROM. This profile
does not enable CHR, ExRAM, mapper-generated IRQ/audio, DMA/DMC or physical guest
interrupt sampling.

## State placement and host interruption

Physical cartridge RAM occupies `$7E:8000..FFFF`, outside CPU RAM, host scratch,
the host stack and bank-$7F capture output. The protection bits and `$5113` page
fit the previously unused `$1876..$1877`; the target-kind byte at `$1859` is also
inside the existing 132-byte host-NMI snapshot. Original cartridge RAM itself
is persistent guest state, not scratch for the host callback to overwrite.
The callback's existing restriction against changing guest memory still applies.

Real emulated SNES vblank interrupts remain enabled in host tests. Free-running
runs are supplemented by cost, clock, capture and nested-worker rendezvous.
Those waits are test instrumentation, not added original-NES cycles or a measured
production performance cost. Host scratch must match fresh no-host executions.

## Independent reference and exact snapshot scope

An authored NES 2.0 header declares 32 KiB of volatile PRG RAM explicitly, avoiding
the reference core's legacy-header RAM-size heuristics. The original NES boot
routine fills all four pages through real mapper writes; the native boot creates
the same declared initial data. Only boot inputs and program/event bytes enter
native execution. No expected intermediate register, page, seed or memory does.

The mapper observer does not replace CPU, mapper, write-protection or interrupt
logic. Physical bank tags come from live mapped pointers, not this project's
selection formula. A small read-only getter exposes the core's actual protection
and RAM-page state. The usual test request harness still applies events after
instructions; it is not a physical interrupt-pin model.

Every instruction endpoint compares **2 KiB of internal CPU RAM plus 32 bytes of
register/clock/request/mapping state**. The observer separately saves **all 32 KiB
of cartridge RAM at the first and final recorded boundaries**. Full cartridge
RAM is compared once per run at the final boundary, not falsely counted at every
intermediate instruction. A compiled observer test changes RAM after recording
ends and proves that the final snapshot does not follow later host-frame writes.
No-request cases additionally compare an unmodified core's complete final CPU-RAM
and image hashes, video callbacks and audio-frame counts.

The guard cases compare cartridge RAM to an independently executed original
prefix ending immediately before the refused operation, not to a guessed host
state. Internal RAM, logical context, effective slots and protection/page state
must also remain unchanged. Faulted prefixes do not count as completed runs.

## Development failure retained

The first host-enabled attempt stopped before its first guest instruction. The
32-KiB native initialization spanned a frame before the normal host-metadata
clear, so the sampler encountered the SNES core's initial `$55` bytes as a fault.
The new profile now clears the host metadata **before** that long initialization.
It does not ignore enabled-host faults or change acceptance tolerances. The
failed capture and log remain local evidence; a source-order regression and the
actual host-enabled matrix exercise the corrected path.

## Fresh local acceptance

All **533 unit/assembler tests pass without skips**, including an independent
run from a clean source archive. The new matrix passes **196 authored plans /
404 native scenarios / 12,524 dependent instruction boundaries**. It compares
**26,049,920 internal-state bytes** at those boundaries and **13,238,272 cartridge
RAM bytes** in the separate final snapshots. Those two sampling scopes are not
conflated. All 61 admitted external-memory forms execute in the tests.

The **195 no-request controls** match an unmodified NES core. The **208 host-enabled
scenarios witness 7,401 emulated hardware vblank NMIs**; protected scratch also
matches no-host controls. All three executable mutants and all six unsupported
access/code guards are rejected as intended.

The full retained MMC5-ROM matrix passes **656 scenarios / 20,336 boundaries /
42,298,880 state bytes**, with its prior controls and guards retained. All 32
runtime-safety configurations pass: **4,224 records / 16,896 register-and-flag
bytes plus 1,024 OAM bytes**, including existing unknown-code and audio stress.
A fresh build comparison confirms **681 older-profile binaries** remain identical
across the merged baseline and this source: 18 default, 244 internal-RAM,
97 fixed-cartridge and 322 MMC5-ROM fixtures. That is build identity, not fresh
execution of every older profile.

Four representative clean-source emulator reruns (protected writes, cross-page
RMW under nested host interruption, handler-driven relocking, and an indirect
RAM pointer) reproduce complete saved captures and native binaries exactly.
These are four reruns, not a second complete new execution matrix. Public CI
must establish its own results for the actual published commit.

## Verification and resumption

Measured results and scope are in `mmc5-cartridge-ram-verification.json`; the pull
request records the exact published commit and its actual CI run separately.
The new matrix retains executable negative controls for a locked write, a wrong
physical RAM page, and ignored protection-bit masking. It also keeps native
refusals for absent-chip selection, mode 0, ROM writes, RAM execution, and an I/O
crossing. All older profiles are rebuilt independently from the merged baseline
and compared byte-for-byte; that build check is not extra emulator execution.

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_wram_timeline.py /path/to/pinned/fceumm
# Rebuild separately, retaining an unmodified original core.
python3 tools/verify_wram_timeline.py \
  --nes-plain /path/to/unmodified-fceumm.so \
  --nes-probe /path/to/wram-observed-fceumm.so \
  --snes-core /path/to/unmodified-snes9x.so \
  --out build/wram-timeline
```

The workflow archives the exact source, full authored inputs, generated assembly,
initial/final cartridge snapshots, per-instruction captures, mutations and guards,
plus retained mapper/runtime-safety reports. Production `native.s` and
`build_native.py` remain unchanged. The historical CV3 random-state mismatch is
not fixed, and no speed gain, boss clear or physical-console validation is claimed.

Next integration work remains PPU/MMC5 graphics and required I/O, independently
established event/stall timing, and an efficient production execution path. This
RAM profile does not make the diagnostic instruction dispatcher a speed solution.

References: the hardware-derived [MMC5 documentation](https://www.nesdev.org/wiki/MMC5)
and the [pinned original mapper implementation](https://github.com/libretro/libretro-fceumm/blob/236ccdfc911e84c60fea6b9d0699c2d440a8de14/src/boards/mmc5.c).
