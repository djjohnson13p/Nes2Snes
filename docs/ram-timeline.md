# Guarded full internal RAM on the composed native timeline

## Starting point and scope

The user merged PR #12 as `7dd453c215804a273128644a4797f0beda863d0a`,
tree `172df3db2cf35e57d37fc446800e5f39bcb2e60f`. Its exact signed commit,
284 source files and passing Actions source archive were restored. All 451
baseline tests passed before this change. The published PR #12 implementation
is the baseline, not the different local-only host-context version described
in an earlier conversation response.

This checkpoint expands the **running procedural timeline** to indexed/indirect
internal-RAM operations, all 2 KiB of guest RAM and its aliases. It is not merely
an address calculator: actual instructions change evolving registers and memory,
retire their original cycle costs, enter/return from the existing sampled guest
interrupts and continue through real host NMIs. It is **not installed in the
production CV3 scheduler**. That runtime and game binary remain unchanged.

## Address resolution before execution

The explicit plan profile `memory_model: internal-2k` enables `timeline_ram.py`
and `snes/src/timeline_ram.inc`. Omitted profile retains the preceding 512-byte
prototype and its restrictions. All **100 documented memory-opcode/addressing
variants** admitted by this profile have independently executed cases.

Unindexed and indexed zero-page operands wrap within zero page. `(zp,X)` resolves
its pointer after zero-page index wrap; `(zp),Y` snapshots the original base before
adding Y. The pointer high-byte fetch independently wraps from `$FF` to `$00`.
Absolute indexing uses original 16-bit address arithmetic. The full guest
`$0000..$1FFF` range resolves to `$0000..$07FF` before operand access. This prevents
a guest alias such as `$18C0` from accessing the host's timeline scratch.

The resolver uses the original opcode/operand and PRE-instruction X/Y. Indirect-Y
base snapshots reach the existing cycle accountant before the operation changes
any registers or RAM. Therefore indexed read page crossings and fixed store/RMW
costs remain distinct. The real native ALU instruction acts on a resolved operand
buffer; stores and read/modify/write results are committed to the mapped RAM.
Guest flags remain NES binary-arithmetic flags even when its logical D bit is set.

The profile also implements the NMOS `JMP (addr)` page-wrap behavior, including
pointers at `$02FF` and mirrored `$1FFF`. Its target comes from the current guest
RAM, not an expected result table. The normal dispatcher still faults on a target
that is not an admitted original instruction boundary.

Both an indexed base/preliminary address and its final target must be internal
RAM. A final address that wraps from ROM into RAM is not enough to authorize the
operation. Unsupported target access sets status 5 **before operand execution or
retirement**. Resolving a zero-page pointer can read ordinary RAM first; no claim
is made that a rejected indirect operation performs no preliminary RAM reads.

This is a state-and-original-instruction-cost profile, **not a bus transaction
model**. Dummy reads, the first RMW write, cartridge observation of RAM traffic,
DMA/DMC interleaving and hardware-register side effects are not represented.
I/O and ROM-data operands remain unsupported. Do not silently extend this RAM
alias rule to mapper or PPU registers.

## Protected context and complete evidence

Resolver scratch `$1852..$185B` sits within PR #12's existing host-NMI snapshot.
The host worker must now leave all guest `$0000..$07FF` alone under this profile,
not merely the earlier `$0000..$01FF`. The same bounded native-mode worker,
balanced stack, two-level nesting and fault contracts continue to apply.

Each observation is **2,080 bytes: 32 bytes of register/clock/event metadata plus
all 2,048 bytes of guest RAM**. The native output bank admits 31 such endpoints;
longer requests are rejected rather than truncated. The old 544-byte observation
cannot certify a full-memory run. The NES harness is explicitly built with
`--ram-bytes 2048`; wrong or partially installed profiles are refused.

The original-NES harness remains **fixture-only after-instruction request
stimulus**, not a read-only gameplay observer or physical interrupt sampler.
Both platforms receive the authored program, declared boot state and request
schedule. No intermediate reference registers, pointers, memory or clock values
are supplied to native execution. The original NES establishes and checks the
initial state by executing its own boot program.

## Fresh local results

All **467 unit/assembler tests pass with zero skips**: 451 baseline plus 16 new
tests. A separate source snapshot also passes the unit suite and the complete
expanded execution matrix. The earlier 214-case development matrix is retained
separately; it is not added to the final totals below.

- **244 authored plans**: two initial variants per memory opcode, 30 additional
  high-index cases, 12 sampled-interrupt/stack cases and two indirect-jump cases.
  These are not all Cartesian combinations of addresses, flags and data.
- Each plan passes both no-host and free-running host-NMI execution. Another
  24 scenarios interrupt loaded operands, unsaved ALU results, clock updates and
  nested workers. In total **512 native scenarios / 15,872 dependent boundaries**
  match **33,013,760 bytes**: 32,505,856 guest-RAM bytes and
  507,904 metadata bytes, with zero mismatches.
- **268 host-enabled scenarios** witness **9,764 hardware-emulated host NMIs**,
  584 deliberate wait returns and 372 nested interruptions. Their final
  protected scratch also matches fresh no-host controls. Host waits are stress
  instrumentation, not guest cycles or a gameplay performance measurement.
- All **232 no-request NES plans** match a separately built unmodified NES core's
  complete final RAM/image hashes and video/audio frame counts. Sampled guest
  entries in the primary reference plans total 21 IRQs and 12 NMIs.
- Three actual wrong native binaries complete but fail exact comparison:
  unwrapped pointer fetch, a wrong RAM-alias mask, and a stale indirect-Y timing
  pointer. Their mismatches are retained, not hidden by result tolerances.
- Four actual access faults cover crossing into PPU space, wrapping from ROM,
  and indirect PPU/ROM targets. All retain the entire 2 KiB of guest RAM and the
  previous registers, requests, PC and cycle clock; failed prefixes cannot pass.

The full previous host-NMI matrix also passes: **65 scenarios / 7,280 boundaries**,
1,024 standalone register contexts, clock-origin tests, corruption controls and
the nesting guard. That suite reruns the original 18-scenario timeline matrix.
All **32 retained runtime-safety configurations** pass: **4,224 records / 16,896
register-and-flag bytes plus 1,024 OAM bytes**, retaining fault guards and audio
stress. These retained totals are separate from the new full-RAM matrix.

All **18 default procedural native builds are byte-identical** to independently
built outputs from the exact merged baseline. There is no hidden default opt-in.

## Fresh private CV3 regression

The existing authorized original input was restored and its full recorded hash
verified. Fresh guarded 84-action and 133-action recordings recreate the 12,359
observed-entry trace. Clean-boot NES/SNES runs on the 133-action route match all
**665 selected fields / 1,197 bytes plus 133 health bytes**; all three destination
checks pass. The private build remains exactly
`0f4ac141190f4b7e0c3bbc1a691938c21872b133560e33bb4256f57c5b66f0ac`.

An unmodified NES core reproduces all 133 recorded endpoints: **7,626,752 pixel
positions / 272,384 RAM bytes**, zero differences. This validates the NES recording,
not NES/SNES pixel identity. Explicit RNG comparison still **fails at 131 endpoints**.
The RAM-profile fixture stimulus is never used in those gameplay runs. No seed,
spawn or tolerance change conceals the failure, and no new boss clear or recovered
117/298-action route is claimed. Private gameplay is local evidence, not public CI.

## Reproduce and continue

```sh
python3 -m unittest discover -s tests -v
# Preserve a separately built plain FCEUmm core first; use the pinned revision.
python3 tools/instrument_timeline_probe.py /path/to/clean/fceumm --ram-bytes 2048
# Rebuild the separate full-RAM stimulus core.
python3 tools/verify_ram_timeline.py --nes-plain /path/to/nes-plain.so \
  --nes-probe /path/to/nes-ram.so --snes-core /path/to/snes9x.so \
  --out build/ram-timeline
```

The workflow archives exact tested source, authored plans, generated assembly,
full original/native captures, mutants and access-fault evidence. Public artifacts
contain no commercial ROM, private game trace, image or game-derived executable.
Check that exact commit's CI before requesting the user's merge. Local success
must not be relabeled as an unseen remote CI result.

Next integrate ROM mapping and hardware-I/O handlers with the protected timeline,
while establishing physical NES event/stall timing separately. The current
instruction dispatcher is diagnostic, not a demonstrated full-speed solution.
Production CV3 scheduling and the random-state mismatch remain open.

References: [NES CPU memory map](https://www.nesdev.org/wiki/CPU_memory_map) and
[addressing modes](https://www.nesdev.org/wiki/Addressing_modes), plus original
execution in pinned FCEUmm `236ccdfc911e84c60fea6b9d0699c2d440a8de14` and native
execution in unmodified Snes9x `fae2fea08f74180759ef540ee94259213f503480`.
