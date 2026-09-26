# Palette integration and ongoing regression gates — 2026-09-26

Read this together with [palette-reads.md](palette-reads.md), which preserves the
recovery ledger, the original 307-test acceptance run, and private gameplay scope.
The follow-up unit suite has **313 passing tests**. Runtime source and the private
build hashes have not changed since that acceptance run.

## Verified source versus staging

`3f33cb701dea111aea8176814ffd8ff9af5db707` is the source-transfer staging commit.
It is not an integrated-runtime claim. Actions run `36267690618` applied that exact
hash-checked transfer and independently passed 307 unit tests, all 16 palette
configurations, and all 32 retained runtime-safety configurations. The exact tested
integration is **`4fa42bcd313eb75a0c933f2752c6afb8db064a3f`**, tree
`780ef063fbf5f051eb6779a8a7f51d23b2335d74`.

The downloaded acceptance artifact has SHA-256
`a40c20ced6e19eba05f0ed2cdde423e6bccb34830fdba41a4cff2df51a6f4ae1`.
Every archived source file was compared with the locally tested file and matched.
The general CI run on the staging commit alone is not evidence for the integrated
runtime; the palette job's archived tested revision is the relevant evidence.

## Why two recurring identity checks needed correction

The dispatch and nametable-DMA introduction workflows asserted that default ROMs
were byte-identical to their respective pre-feature source revisions. That was a
valid, explicitly historical test when adding opt-in optimizations. It cannot
remain an invariant for every later intentional default-runtime correctness fix.

The new palette handler intentionally changes default ROM bytes. Fresh procedural
CPU, fill, and dispatch builds differ from the `a209aaf` defaults by 6,880, 6,995,
and 6,891 byte positions respectively. These are assembly/layout changes, not
counts of behavioral errors. Cross-revision identity is not claimed.

Ongoing default-policy checks now build **the same current source** with options
omitted and with `native_inline_dispatch`, `coalesced_nt_dma`, and `fill_cache_fix`
explicitly false. All three 4-MiB procedural ROM pairs match byte-for-byte. The
checker also requires disabled default parameters and disabled build metadata;
empty output, changed output, changed defaults, enabled metadata, and invalid
fixture selections are rejected by tests. Six new unit tests bring the total to
313. This verifies opt-in policy, not gameplay accuracy.

The 45-configuration independent dispatch suite, its unknown-target guards, the
421-case VRAM matrix, mutated-DMA negative control, independent fill-mode tests,
actual old-source fill failure, and retained CPU/audio safety checks are still
required by their workflows. No pixel/register mismatch tolerance was relaxed.
The dispatch verifier's explicit `--previous-root` historical identity mode also
remains available; ongoing CI no longer applies that historical assertion to an
intentionally different runtime. The nametable workflow still archives its old
source for the actual failing fill-mode control.

`palette-integration-verification.json` records local default-policy evidence and
the first successful independent acceptance run. Follow-up workflow and merge
status must be checked at their actual tested commit; an earlier green run does
not automatically certify a newer revision.

The exact prior 117-action Block 1-03 script remains unrecovered from the sources
checked. This follow-up adds no route, boss clear, speed gain, or complete-port
claim. Private ROM bytes, traces, and game captures remain outside GitHub.
