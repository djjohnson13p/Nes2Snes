# Idle-state audit and fault-aware route comparison — 2026-09-26

## Recovery and scope

The verified starting source is merged `ad442ebb320ee079001090135e1d3449d6d19623`,
tree `3c513142e19975a1a76133212159cc53f53f4445`. The Actions source archive was
restored and matched that tree exactly. All 327 baseline tests passed locally.
The original private ROM and earlier trace were recovered using the existing
checkpoint procedure in `palette-reads.md`; the full original ROM hash matched.

The preceding conversation reported a local-only `b175bdd...` commit, a 298-action
first-boss route, and 361 tests. That workspace and those source files were **not
available in this continuation's mounted files, repository branches, or searched
Library files**. No recovery of that commit or fresh first-boss clear is claimed.
The committed 133-action entrance route is recovered unchanged. This checkpoint
reconstructs the fault check and adds new, independently calibrated diagnostics;
it does not silently treat missing local work as verified source.

## Fixed: equal captures no longer override a recorded fault

`route_evidence.compare_routes` rejects a non-null `fault` on **either** side,
including a malformed falsey value such as `{}`, `0`, `false`, or an empty string.
The source status and both fault payloads remain in the result. `complete_routes`
reports capture completeness separately from `fault_free` and `passed`.
`verify_reference_route.py` also rejects a fault-bearing source before loading
an emulator. Mutation tests retain matching captures but insert faults to prove
that this changes acceptance, not only report wording.

The optional repeated `--ram-byte` flag compares up to 32 explicit, unique bytes
of common NES RAM. Addresses must be integers in 0..2047; duplicate, boolean and
out-of-range addresses and insufficient captures are rejected. These checks have
separate counts and mismatch records. The original five-field selected-state
comparison is not renamed into whole-RAM equivalence.

## New: read-only tick/sample observer

`instrument_idle_observer.py` patches the pinned FCEUmm and Snes9x instruction
loops. The shared C/C++ header observes instruction visits and reads selected
common-RAM bytes directly; it never reads a bus register, alters emulated clocks,
writes guest memory, or changes a random seed. SNES host/veneer instructions are
excluded. Tick and sample PCs are explicit parameters, not hard-coded game code.
Measurements are for uninterrupted sessions; reset, state loads and game changes
are not supported during a capture.

The bounded buffer holds at most 32,768 samples of up to 16 RAM bytes. Overflow,
empty captures, changed ABI, and invalid ordering reject measurement acceptance.
Invalid reconfiguration disables and clears an old observer. The first sampled
interval is labeled partial. NES bank is unavailable (reported as 0), while the
SNES bank is its execution-map bank; they are not compared as equivalent mapper
identifiers. The private game measurements here use fixed-bank instruction PCs.
Ticks are **instruction visits, not CPU cycles or elapsed-time attribution**.

`observe_route_idle.py` replays the exact recorded host-input timeline and compares
every endpoint's image and full available RAM with the source capture. A passed
observer replay means noninterference on the **same** platform. It preserves a
failed/faulted source as `source_route_passed: false`; it cannot turn matching
failures into a successful gameplay route. Failed-source final RAM is checked too.

## Independent procedural calibration

An authored, redistributable MMC5 fixture changes a byte in a free-running loop.
An independently executing NMI logs the byte and a 24-bit iteration counter.
Both observer cores reproduce their respective unmodified cores: full final RAM,
all frame-image hashes, emulator/video-frame counts and audio-frame counts match.
All **64 sample records (32 per platform)** match the independently executed
NMI logs, including the full counter rather than only its low 16 bits. Tests
reject a one-tick change, a high-word count change, a changed byte, missing rows,
and overflow. C99 and C++11 builds verify the same 48-byte record ABI.

This intentionally does **not** require NES and SNES idle-state values to match:
the timing difference is the object of the measurement. It is not an accuracy
oracle for the port's idle timing. The final local unit/assembler suite contains
**351 passing tests**; this is not a completion percentage.

## Fresh private game evidence

The clean-boot 84-action source recording and 133-action Block 1-03 route were
regenerated. The expanded trace has the same 12,359 entries as the committed
entrance checkpoint. The native runtime source and builder are unchanged, and
the resulting private SNES binary has the recorded entrance-checkpoint hash:
`0f4ac141190f4b7e0c3bbc1a691938c21872b133560e33bb4256f57c5b66f0ac`.

The NES/SNES entrance route still matches all **665 selected fields / 1,197 bytes**
at its 133 endpoints with no fault. Player health `$003C` also matches all 133
endpoints. However, including random-state byte `$001F` makes the comparison
**fail at 131 of 133 endpoints**. This exposes a previously excluded state field;
it is not a new runtime regression introduced by the diagnostic tools.

The observer records the free-running loop's entry `$E047` and samples before the
guarded NMI-update instruction `$E064`:

| Measurement | NES | SNES |
|---|---:|---:|
| Guarded-update samples | 11,174 | 11,174 |
| Loop-entry visits between first and last sample | 9,889,410 | 17,470,785 |
| Median loop-entry visits per sampled interval (first excluded) | 884 | 1,823 |
| Sampled intervals with zero loop visits (first excluded) | 0 | 5 |

At those aligned samples, frame counter `$001A`, game state `$0018`, reentrancy
byte `$0051`, and player health `$003C` all match. Random state `$001F` differs
at **11,129 of 11,174 samples**, already at the first sample during startup.
The initial values are 87 on NES and 151 on SNES. Equal guarded update counts
therefore do not establish equal idle-state evolution.

Observer replay preserves all **133 captures per platform** exactly: 7,626,752
pixel positions per platform, 272,384 NES RAM bytes, and 17,432,576 SNES WRAM
bytes. These are same-platform observer-vs-source comparisons, **not cross-platform
pixel/full-RAM equivalence**. The report distinguishes all acceptance scopes.

No forced seed, spawn-direction override, patched game timing, new boss-clear
claim or speed improvement is included. Correcting the engine requires a timing
model that accounts for state-changing idle execution and interrupt placement;
copying observed seeds or deleting the wait loop would conceal the discrepancy.

## Reproduce and resume

Read `block103-entry.md` to restore the authorized inputs and regenerate the NES
and SNES 133-action capture directories. Preserve independent plain cores. Build
the observer variants from the pinned sources in `toolchain.md`:

```sh
python3 -m unittest discover -s tests -v
python3 tools/instrument_idle_observer.py /path/to/fceumm --platform nes
python3 tools/instrument_idle_observer.py /path/to/snes9x --platform snes
# Rebuild both using their documented libretro makefiles.
python3 tools/verify_idle_observer.py --nes-plain /path/to/nes-plain.so \
  --nes-probe /path/to/nes-observed.so --snes-plain /path/to/snes-plain.so \
  --snes-probe /path/to/snes-observed.so --out build/idle-calibration
python3 tools/observe_route_idle.py --core /path/to/nes-observed.so \
  --rom original/CV3.nes --source build/block103/nes --out build/idle-nes \
  --tick-pc 0xe047 --sample-pc 0xe064 \
  --ram-byte 0x1f --ram-byte 0x1a --ram-byte 0x18 --ram-byte 0x51 --ram-byte 0x3c
python3 tools/route_evidence.py --reference build/block103/nes \
  --candidate build/block103/snes --ram-byte 0x1f --ram-byte 0x3c \
  --out build/idle-comparison.json
# The final command intentionally exits nonzero on the current timing divergence.
```

Use the observed SNES core with its SNES ROM and captured SNES directory for the
second replay. Do not reuse the NES host-frame timeline as SNES input. Public CI
contains only the authored calibration and retained runtime-safety tests. It does
not contain the private commercial ROM or certify the gameplay measurements.

Next: use this reproducible startup-to-entrance witness when implementing an
original-clock/interrupt scheduling correction. The missing local 298-action
script must be recovered from a real saved source or explicitly re-authored;
no new route should be represented as that missing artifact. Preserve source
on a named remote branch rather than leaving the only copy in an ephemeral
workspace. When CI passes, request the user's merge explicitly.
