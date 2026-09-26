# Background transfers and a stale fill-mode cache

Continuation of `73a572064fc0447f71307cd45d007c106f170f0c`.
This remains an incomplete, trace-bounded port. Both changes below are opt-in;
no new full-speed, boss-clear, whole-game or physical-console claim is made.
The user requested no further intermediate download packages.

## Changes

`--coalesced-nametable-dma` joins adjacent dirty background rows into a single
SNES DMA transfer. Clean gaps terminate a run; the bottom and HUD source regions
are scanned separately. It copies exactly the same bytes as the existing row
uploader and retains the caller's forced-blank and completed-frame ownership
rules. Sparse alternating rows remain separate transfers. Dense 160-row input
uses two launches instead of 160; five ordinary 30-row tables use five instead
of 150. This is a measured launch-count reduction, not a measured game speedup.

`--fix-fill-cache` repairs a separately discovered correctness error. The old
renderer can leave a stale background after MMC5 fill tile/color writes to
$5106/$5107 when $5105 routing and physical nametable contents are unchanged.
The new frame-level cache detects changes to the tile and effective two-bit
palette and refreshes fill-routed tables, including the separately converted HUD.
Its state occupies unused WRAM $0D6A..$0D6D. Ordinary nametable row invalidation
and the old uploader remain available.

The fill test uses non-extended-attribute mode ($5104=0) and steady output after
a register change. Mid-scanline fill changes, extended attributes and complete
MMC5 behavior are not certified. Neither option modifies original gameplay code.
With both options omitted, fresh procedural and private-game builds are
byte-identical to the preceding source using the same inputs and settings.

## Executed local checks

- **259 unit tests pass**, including actual ca65 option/symbol checks.
- The actual old and new uploaders run in an authored standalone SNES harness:
  **842 configurations and 55,181,312 full-VRAM bytes**, zero differences from
  the independent individual-row copy specification. Empty/disabled maps,
  individual rows, adjacent pairs, table/HUD boundaries, non-Boolean dirty flags,
  alternating rows and seeded sparse/dense masks are covered. Sentinel values,
  dirty-map clearing, stack/direct-page/width state and transfer counts are checked.
- A deliberately shifted HUD source in the test-only harness fails with **2,041
  VRAM-byte mismatches**. The candidate source is not modified by that control.
- **32 changed-fill configurations** match the pinned unmodified Nestopia NES
  core: **1,835,008 black/white pixel classes**, zero differences. Both uploaders
  also match **153,600 expected tilemap words**. The actual preceding source
  fails the first changed-fill screen with **43,008 of 57,344 differing pixels**.
- The retained independent CPU/runtime-safety runner passes **32 configurations,
  4,224 register records, 16,896 register-and-flag bytes and 1,024 OAM bytes**.
  Its existing unknown-code and audio/interrupt stress checks remain intact;
  it uses default renderer options, not every combination of these new options.
- With both new options and forced interrupt-restore stress enabled, the authored
  object-cache test passes **160 frames and 81,920 OAM-encoding bytes**.
- In the private fixed-input gameplay comparison, all five selected images match
  the preceding SNES renderer (286,720 pixels). A separate callback-tagged run
  matches RGB hashes for **all 231 presented game frames 916 through 1146**,
  covering **13,246,464 pixels**. This is a bounded SNES regression comparison,
  not independent-NES all-game visual equivalence.
- Fresh ordinary-controller runs finish the existing 31-step approach and
  57-action staircase route. All 57 selected game-state/player-position endpoints
  match. No additional stage or boss completion is established.

## An independent reference disagreement was not hidden

The first fill-matrix run against FCEUmm disagreed on the upper-bit $5107 case.
For value $FE, the pinned FCEUmm renderer and Nestopia differ at **26,880 pixels**.
The new SNES output agrees with Nestopia and the documented low-two-bit palette
behavior. The pinned FCEUmm mapper code expands the unmasked byte with
`V | (V << 2) | (V << 4) | (V << 6)`, allowing upper bits into other quadrants.
The second reference is therefore the primary renderer for this matrix, while
FCEUmm's discrepancy is retained explicitly as a non-passing diagnostic.
No image tolerance or excluded-row mask was introduced to erase the difference.
This is source/documentation-backed evidence, not a hardware measurement.

References: https://www.nesdev.org/wiki/MMC5 (fill-mode registers);
FCEUmm `src/boards/mmc5.c` at `236ccdfc911e84c60fea6b9d0699c2d440a8de14`;
Nestopia at `8f00f500912a847062de432e38765c7285483e62`.
The project implementation is original; emulator implementations are not copied
into the SNES runtime.

## Performance: no improvement claimed

Same matching private trace, fixed game-frame inputs, native-controller option,
counter-free execution, audio/counter/sweep/raster options and unmodified Snes9x:

| Interval | Game updates | Baseline display frames | Both new options |
|---|---:|---:|---:|
| Walk | 120 | 149 | 149 |
| Jump | 25 | 39 | 39 |
| Attack | 25 | 44 | 44 |
| Settle | 60 | 74 | 74 |

The longer ordinary-controller route takes **12,547 rather than 12,540 display
frames**, seven more frames (approximately 0.056% longer). The changes are not a
CV3 throughput win in these samples. Reduced dense DMA setup cannot be substituted
for measured whole-game speed. Full-speed operation remains unfinished.

## Reproduce

Requires Python with NumPy/Pillow, ca65/ld65 and the pinned independent cores.
The first three checks use only project-authored procedural data:

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_nametable_dma.py --core /path/to/snes9x_libretro.so --out build/dma-matrix
python3 tools/verify_fill_mode.py --nes-core /path/to/nestopia_libretro.so \
  --snes-core /path/to/snes9x_libretro.so --fceumm-core /path/to/fceumm_reference.so \
  --previous-root /path/to/source-73a5720 --out build/fill-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/private-trace \
  --out build/renderer-candidate --experimental-audio --audio-counters --audio-sweep \
  --experimental-raster-scroll --no-runtime-counters --native-controller \
  --coalesced-nametable-dma --fix-fill-cache
```

The final command needs the authorized original ROM and matching private trace.
Those inputs, game-derived ROMs, captures and sound stay outside the public repo.
The CI workflow independently rebuilds the procedural tests and archives the
exact tested source. Local evidence is not described as CI success before that
workflow actually completes. See `nametable-dma-verification.json` for the local
results and the associated workflow artifact for independently reproduced results.

## Remaining work

Full-game coverage, first-boss validation, faster gameplay, exact raster and sound
timing, sampled DMC audio and physical SNES testing remain open. The existing
partial-row rendering discrepancies are not resolved by this fill-cache fix.
The earlier unpublished indirect-load flag experiment is not part of this change.
