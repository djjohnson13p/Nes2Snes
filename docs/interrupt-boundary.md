# Sampled interrupt entry — 2026-09-26

## Recovered baseline and scope

Published `main` was verified at `ad9b58ed735acae43d0ffa062f5deb81b85df60a`,
with tree `04929c73e1e8d56f35c5173f2a8c24e6106e06bc`. The original signed Git
commit object and all 255 source files were restored exactly from public records
and the checked Actions source artifact. All 379 baseline tests passed freshly.
The local repository is explicitly shallow at that commit, not a recovered full
history.

The previously reported local-only `c7d5eed...` block-execution checkpoint was not
found in the mounted workspace or the Library results examined. Its blocked
source upload was not retried. This is new interrupt-entry work based on published
source, not a recovery or republication of that package. Its 410-test total is not
carried forward. The earlier missing 117- and 298-action routes remain unrecovered.

## What executes natively now

`snes/src/guest_interrupt.inc` resolves an IRQ/NMI request at a completed original
instruction boundary and creates the three-byte NES interrupt stack frame. Inputs
include the original completed opcode, flags before and after it, already sampled
IRQ level/NMI latch, logical stack pointer, return PC and vector addresses.

The routine gives NMI priority, preserves the IRQ level, consumes the NMI latch
only when serviced, pushes return-PC high/low and status with B clear and bit 5
set, wraps the logical stack pointer within page one, sets I, and returns the
selected vector and seven-cycle entry cost. No accepted interrupt means no guest
state change or cycle charge. CLI/SEI/PLP use pre-instruction I for the IRQ decision;
RTI uses restored I. BRK and undocumented opcodes are rejected, not guessed.

The separate Python model returns immutable result buffers. Actual native tests
check the entire guest stack page and descriptor, plus host A/X/Y/D/DBR/P and stack
balance under all four M/X combinations with host decimal set. The caller must
own `$1860..$187F` and the guest stack page, use native mode and keep its host stack
separate. That ABI is not allocated inside the current game runtime.

**The routine is not linked into `native.s` or `build_native.py`.** Production
runtime bytes are unchanged. This does not install a scheduler or predict the
safe cycle budget required by future block execution.

## Independent oracle and its limitations

`interrupt_fixture.py` creates original NES programs using real completed
instructions. `instrument_interrupt_probe.py` adds two explicit test hooks to
pinned FCEUmm. At the selected instruction's completion, the harness may assert
an external IRQ or an NMI latch through existing emulator APIs. It captures state
before the request and at the next instruction boundary. The original emulator's
interrupt selection, register/stack writes and vector fetch code are unchanged.

**This harness is stimulus injection, not a read-only gameplay observer.** It is
used only for authored tests. It never writes expected guest RAM, registers or
stack results. Native inputs are built solely from the before-entry capture;
after-entry state supplies comparison results, never execution input. All 300
no-request cases also match a separately built unmodified NES core's full RAM,
image hash, video-callback count and audio-frame count.

Requests are deliberately resolved at emulator instruction boundaries. This does
not establish physical pin polling, late branch-edge behavior, NMI detector delay,
interrupt hijacking, or delivery during DMA/DMC. In particular, the caller must
supply a correctly sampled request; this routine cannot turn an arbitrary pending
PPU/mapper event into one. At least one actual guest instruction must complete
before another boundary call. A production scheduler must enforce that ordering.

## Fresh results

- **402 unit/assembler tests pass, zero skipped:** 379 baseline plus 23 new tests.
  These include actual assembled native entry, compiled C99 test-harness checks,
  strict hook installation and malformed-evidence rejection.
- **1,712 valid native entry calls** cover 150 documented completed opcodes (BRK
  excluded), two flag setups per opcode, IRQ/NMI combinations and every one of
  the 256 logical stack positions. All match independently executing NES entry:
  27,392 descriptor bytes, 438,272 stack bytes and 20,544 caller-context bytes.
- Observed decisions are 451 no-entry, 405 IRQ and 856 NMI. All accepted entries
  consume seven original cycles; no-entry decisions consume none.
- **112 invalid native inputs** reject BRK, all 105 undocumented opcode bytes and
  malformed request/reserved fields without changing guest state or charging time.
- Two actual broken native executables fail: using post-I for CLI's delayed mask,
  and setting B in the pushed interrupt status. Unit mutations also reject changed
  state, stack, context, timestamps and incomplete captures. A new run removes a
  stale passing summary before it starts.
- All **32 retained runtime-safety configurations** pass: 4,224 records / 16,896
  register-and-flag bytes plus 1,024 OAM bytes. Existing fault guards and audio
  stress remain enabled.

The first short native capture allowance proved insufficient for the full batch
of stack copies and was rejected as incomplete. A bounded completion-marker loop
replaced that assumption; partial runs are not counted as passes. The completed
matrix and saved captures passed the final strict evidence checker.

## Private gameplay regression

The authorized original input was restored from the user's saved checkpoint;
its complete recorded ROM hash matched before use. A fresh 84-action guarded
trace followed by the 133-action entrance route reproduces the established build
hash `0f4ac141190f4b7e0c3bbc1a691938c21872b133560e33bb4256f57c5b66f0ac`.

The clean-boot NES/SNES route matches all 133 endpoints: 665 selected state fields /
1,197 bytes and 133 separately counted health bytes. All three Block 1-03 waypoint
predicates pass. An unmodified NES replay reproduces the ordinary recording;
this is not a NES-to-SNES pixel equivalence claim. The external-request test core
is not used for any of these private gameplay runs.

The explicit random-state comparison still **fails at 131 endpoints**. No seed,
spawn, game input or comparison tolerance was changed to hide it. No gameplay
speedup or new boss clear is claimed. Private ROM, trace, captures and binaries
remain outside the public source repository and public CI.

## Reproduce and next integration

```sh
python3 -m unittest discover -s tests -v
# Preserve a plain pinned FCEUmm build before installing the fixture-only harness.
python3 tools/instrument_interrupt_probe.py /path/to/fceumm
# Rebuild the test core separately.
python3 tools/verify_interrupt_boundary.py --nes-plain /path/to/plain.so \
  --nes-probe /path/to/request-test.so --snes-core /path/to/snes9x.so \
  --out build/interrupt-boundary
```

The workflow archives exact tested source, full independent captures and native
outputs, negative controls and runtime-safety evidence. Verify the actual candidate
CI revision before requesting the user's merge; local execution is not remote CI.

Next connect verified original-cycle accounting to event deadlines, sampled
interrupt requests and protected handler transitions. The existing frame-driven
game scheduler cannot simply call this routine on host NMI and become cycle
accurate. Branch polling, late NMI/IRQ edges, DMA/DMC and vector hijacking need
separate evidence before any live-game timing replacement is accepted.

References: NESdev's CPU interrupts documentation
(https://www.nesdev.org/wiki/CPU_interrupts) and the pinned original FCEUmm dispatch
(https://github.com/libretro/libretro-fceumm/blob/236ccdfc911e84c60fea6b9d0699c2d440a8de14/src/x6502.c).
