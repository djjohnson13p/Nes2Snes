# Blanked sprite-memory ports on the palette execution profile

## Verified starting source and recovery boundary

The starting revision is the user's merged PR #21,
`a9a7408e95ff58e1da9615668dd76a9abc360ace`, tree
`039fc32dfd8fac8f320eba6db88c543f71ed6ecf`. The 362-file CI archive reconstructs
that exact tree; its 639 baseline tests were rerun successfully. The signed base
Git object was reconstructed and hash-verified before creating the new branch.
The preceding local-only CHR-set and OAM workspaces were not present in the
current mounted workspace. No recovery or acceptance of those commits is claimed.

This is new source on that published baseline. It creates the explicit
`mmc5-oam-blank` adapter over `mmc5-palette-blank`, rather than changing the old
profile's OAM refusals. Production `native.s` and `build_native.py` are unchanged.
There is no fresh commercial-game replay, game-timing correction or boss-clear
claim. The historical 117-action route is not recovered by this work.

## Executed behavior

The new adapter accepts original absolute LDA/STA accesses to OAMADDR/OAMDATA and
their mirrored PPU register addresses. OAMADDR writes set the sprite-memory
address and full PPU I/O latch. OAMDATA writes retain the full written latch byte,
store the physically present attribute bits, and increment the address once
with byte wrapping. OAMDATA reads update the latch but do not increment the
address. A read of the write-only address port returns the shared latch.

The 256-byte OAM image is separate guest memory at `$7E:5900`. The address uses
`$1C3B`, formerly the temporary byte in the compact CHR context. Only this adapter
relocates the CHR register writer's temporary to existing protected `MR_VALUE`.
CHR initialization still initializes that context; OAM initialization clears
its image through a native loop. Original NES initialization uses ordinary
OAMADDR/OAMDATA instructions. Neither side receives expected intermediate data.

This reuse avoids increasing the existing nested host-NMI stack frame. No stack
watermark or canary requirement is relaxed. The address is captured in byte 13
of this profile's 16-byte PPU endpoint record; prior profiles retain zero padding
there. Interleaved CHR, palette and scroll tests check that one port family cannot
accidentally overwrite another's persistent state.

The hardware contract is the ordinary forced-blank behavior described in
[NESdev's OAM port reference](https://www.nesdev.org/wiki/OAMDATA) and
[OAM storage layout](https://www.nesdev.org/wiki/OAM_internals). The implementation
does not model OAM decay, revision-dependent OAMADDR corruption, rendering-time
sprite evaluation or sprites on screen. DMA remains a translation refusal; no
unverified DMA cost is added to the guest clock. PPUSTATUS reads, rendering,
PPU-generated NMI and live CHR-size changes remain refused in the inherited
profile. Those refusals are supported-profile limits, not hardware fault claims.

## Independent observations and comparison scope

Unmodified Nestopia at `8f00f500912a847062de432e38765c7285483e62` executes the
authored boot/program to a stable self-jump. Raw NST states are retained. The
existing bounded OAM decoder reads the actual 256 OAM bytes, OAMADDR and latch.
The pinned core already masks nonexistent attribute storage bits on writes; this
adapter compares its raw OAM bytes and rejects snapshots containing those bits.
It does not clear CPU-result bits to force an agreement. The OAM and palette
parsers must independently agree on their common latch field.

Each completed independent endpoint compares **5,430 bytes**: the preceding
5,173-byte CPU/PPU/palette/CIRAM/mapper/ExRAM endpoint plus 256 OAM bytes and one
address byte. Final CPU, PPU, mapper and OAM-address fields must equal their last
retired native record. All OAM and external-memory contents are checked at the
final endpoint, not after every instruction.

Native per-instruction CPU/PPU/CHR records establish host-interrupt noninterference
only. They do not establish independent NES instruction timing. The guest has no
authored IRQ/NMI request stream in this endpoint profile. Real emulated SNES
vblank interruptions, including targeted nested workers, are tested separately.
The host worker is not permitted to modify guest OAM or other guest memories.

A bounded optional read-only memory-snapshot hook was added to the existing
native capture helper. Its default output is unchanged. Tests reject malformed
ranges, reads outside the core's memory and attempts to overwrite an existing
result field. No execution or emulator behavior is replaced by this hook.

## Acceptance and retained failures

The deterministic main sweep contains 514 distinct programs: all 256 address
positions, all 256 attribute values (one duplicate program removed), and three
CHR/palette/scroll interleavings. Every program runs without host interruptions
and with free-running host interruptions: 1,028 potential accepted endpoints.
Every address case reads the full write latch before another PPU write replaces
it, then performs repeated reads to detect accidental address increments. This
is not the Cartesian product of all addresses, values, masks and mappings.

Twelve targeted configurations exercise cost, partial-clock, capture and nested
host sites across three programs. Three executable mutants must finish normally
but fail comparison: absent attribute masking, an incrementing read and a masked
write latch. Four original-prefix comparisons require status/rendering/NMI/live
CHR-size refusals to occur before state mutation or instruction retirement. The
NES prefixes use authored self-jumps, not live state patches.

A separate unmodified FCEUmm sample records its readback disagreement. It is
excluded from the primary acceptance totals; neither reference is modified to
agree. The old palette/nametable reference discrepancies are not removed.

A limited run explicitly reports `complete_matrix=false`. Only a complete run
and the controls can support acceptance. The workflow also requires full retained
palette and nametable sweeps and the 32-configuration runtime-safety suite. Exact
run counts, core hashes and failures are recorded in generated JSON and the PR
verification ledger. A source commit, passing smoke run or planned case count
must not be called a completed CI pass.

## Reproduce and continue

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_oam_ports.py \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so --out build/oam-ports
python3 tools/verify_oam_ports.py --controls \
  --nes-core /path/to/unmodified-nestopia.so \
  --snes-core /path/to/unmodified-snes9x.so \
  --fce-core /path/to/unmodified-fceumm.so --out build/oam-controls
```

The workflow archives exact tested source, original authored NES inputs, generated
assembly, raw NST states, captures and negative controls. No commercial ROM,
private game trace, commercial image or game-derived executable is included.
After CI, verify its tested revision/tree and source archive, then request the
user's merge. Do not silently merge or equate a temporary PR-merge SHA with its
branch head unless their trees have actually been checked.

Remaining work is independently verified status/event timing, DMA/DMC stalls,
rendering-dependent PPU/mapper behavior and efficient production integration.
The historical CV3 random-state mismatch remains unresolved. No gameplay speed,
visible rendering improvement, physical-console validation or complete-port
claim follows from these memory-transfer tests.
