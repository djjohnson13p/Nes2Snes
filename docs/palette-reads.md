# PPUDATA palette correction and recovery ledger — 2026-09-26

## What was actually recovered

The remote starting point was `a209aaf64f707913e028af43cd7dd6bf9459c63a`,
tree `e77bf541f0efefd5f43970490f8ab6bebce58dba`. Its exact Actions source bundle
was restored and the local tree matched that Git tree before changes. All
**299 baseline unit tests** passed freshly. The README's 242-test native-controller
headline was historical, not the current repository revision. The previous
runtime milestone is the native-dispatch merge `712b687`; `a209aaf` adds roadmap
and calibrated diagnostic tooling, not another speedup.

The available Library oam-offset/counter-free checkpoints supplied private
reproduction inputs and a preceding playable build. The original ROM was recovered
from the oam-offset build's deliberately separate raw-data banks and matched the
entire original SHA-256 from `rom-analysis.json` exactly. No replacement ROM was
obtained from the internet. These bytes, private traces, RAM, and game images
remain outside the public repository.

The **exact previously reported palette correction and 117-action Block 1-03
route were not found** in the checked current source, branch references, or
available private checkpoints. The `development/extended-route-20260926` branch
at `d0f117b` contains only the older staircase route in `tools/routes`; its latest
change retrieves credited public controller recordings for research. Those
recordings are not the user's missing 117-action script. This continuation does
not claim to recover, reproduce, or validate that missing route, and does not
rename or pad the existing 84-action script to resemble it.

The palette correction below is therefore a **new reconstruction with fresh
independent evidence**, not an assertion that unfinished prior local work was
committed. The separate previously discussed indirect-read experiment remains
outside this change.

## Corrected behavior

`native_ppudata.inc` implements palette reads through the existing compatibility
handler. The access returns six palette bits, applies PPUMASK grayscale selection,
and preserves the upper two bits of the PPU I/O latch. The full returned byte
updates that latch. At the same time, the delayed read buffer is refreshed from
the nametable address beneath the original mirrored palette address. Palette
aliasing must not turn that nametable lookup into a different address.

The address resolver now has an entry that accepts an address without replacing
live PPU `v`. Buffer refill therefore does not accidentally step or overwrite
`v`; the original +1/+32 increment occurs once. CIRAM and MMC5 fill reads reuse
the same resolved-memory helper. Rendering-time PPU fetch interactions, decay of
open-bus bits, and DMC interference are not modeled or certified by this fixture.

## Fresh local evidence

- **307 unit tests pass**, including actual assembler/build tests and strict
  fixture validation. Truncated observations, duplicate records, and silently
  discarded result bits are rejected by the new comparison helpers.
- **16 independent palette configurations pass: 2,368 records / 9,472 bytes,
  zero mismatches.** They contain 37 address cases each, full A/X/Y and C/Z/V/N
  observations, all palette entries, selected mirrors, grayscale, bus prefixes,
  consecutive reads, shadow-buffer refill, +1/+32 increments and address wrap.
  CIRAM 0/1, MMC5 fill, register aliases, indexed/indirect reads, generic fallback,
  full write context, counter-free execution and nested-host-interrupt stress
  are included. This is not every Cartesian combination or timing condition.
- The **unchanged `a209aaf` baseline fails 130 of 148 records** on the same first
  fixture. The corrected build passes all 148. This is an executed negative
  control, not a source-only inspection or self-consistency claim.
- Acceptance uses **unmodified Nestopia** at the pinned revision in the workflow.
  Unmodified pinned FCEUmm disagrees with Nestopia on **91 of 148** diagnostic
  records. Those complete differences are retained separately, not masked away
  or counted as successful two-oracle agreement. FCEUmm's palette branch does
  not implement the same I/O-latch behavior.
- The retained **32-configuration runtime-safety suite passes**: 4,224 CPU/PPU/APU
  records, 16,896 register/flag bytes and 1,024 OAM bytes. It retains counted and
  counter-free behavior, mapper returns, interrupt stress, and unknown-code
  fault tests. These are scoped event tests, not cycle-accurate sound validation.

Two bounded command invocations timed out during the retained suite. Their partial
prefixes were not counted as passes. A monitored complete rerun finished all 32
configurations successfully before publication. This observed execution-window
limit is not asserted to explain unrelated past conversation failures.

## Fresh private gameplay regressions

The saved 10,763-entry trace was extended by fresh original-NES executions of the
existing route: the legacy-clock pass produced 11,376 entries; the subsequent
guarded pass produced **11,553**. This union includes both paths and must not be
confused with the historical 11,214-entry guarded-only union. No guessed code
boundaries were used to replace the missing route.

The clean-boot **31-step approach plus 84 named actions** completed on the original
NES and both SNES builds. For each SNES build, all **420 selected state fields /
756 bytes** match the NES at the 84 endpoints. These fields are game state, area,
camera and player coordinates, not all gameplay memory. Unknown-code fault
handling remains enabled.

The original-NES probe route was independently replayed in unmodified FCEUmm:
**172,032 RAM bytes and 4,816,896 pixel positions** match at its 84 endpoints.
That comparison verifies the NES recording, not SNES graphics fidelity.
Separately, all 84 baseline-SNES versus corrected-SNES endpoint images match.
Both SNES runs consume **15,124 display frames**; no route speed gain is claimed.

The fixed-input regression also matches all **five render-aligned captures /
286,720 pixel positions** between baseline and corrected SNES. Measured intervals
are unchanged: walking 147 display frames per 120 updates; jumping 39 per 25;
attacking 44 per 25; settling 72 per 60. These renderer-regression comparisons
are not a claim that every SNES pixel matches the NES original.

## Publication and resumption

`palette-reads-verification.json` records the local evidence, hashes and scope.
The `Palette reads and retained runtime safety` Actions workflow independently
rebuilds pinned unmodified emulators, repeats the 16-configuration palette matrix
and 32-configuration safety suite, and archives its **exact tested revision**.
The initial source-transfer commit is staging, not the integrated tested runtime.
Only after all checks pass may its integration commit be pushed to the development
branch; final main-branch status must be checked separately.

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_palette_reads.py --nes-core /path/to/nestopia_libretro.so \
  --snes-core /path/to/snes9x_libretro.so --fceumm-core /path/to/fceumm_reference.so \
  --previous-root /path/to/source-a209aaf --out build/palette-reads
python3 tools/verify_runtime_counters.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/palette-safety
```

For private input recovery, the saved oam-offset SFC has the original PRG in the
first 16 KiB of each 32-KiB LoROM slot 1..16; original CHR occupies file offsets
`0x268000..0x287fff`. Prepend the recorded original header and require the full
`rom-analysis.json` hash before treating the result as the original input. This
layout is specific to that checkpoint, not a generic SFC extraction guarantee.
Restore its `rebuild-input/trace`, then regenerate the legacy and guarded routes
using `gameplay_route.py`, `--steps 31` and `tools/routes/cv3-outdoor-respawn.json`.

The next coverage task is to recover the exact 117-action script from a genuine
saved source, or author and clearly label a new clean-boot Block 1-03/boss route.
First-boss completion, broad character/stage/restart/ending coverage, full-speed
operation, existing raster discrepancies, DMC/remaining audio behavior, precise
scheduling, and physical-SNES testing remain open. This checkpoint is not a
completed port or a release for final user acceptance.
