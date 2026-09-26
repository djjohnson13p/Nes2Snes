# Nonzero OAM DMA investigation

Continuation baseline: `a19a87c328e47e3603e3f049b605a85693e230c9`.

A fresh local recovery of the source and pinned toolchain passed all 190 baseline unit tests. A newly parameterized procedural sprite-DMA fixture then set OAMADDR to 1 before copying a fully initialized RAM page with rendering disabled. The unmodified FCEUmm core's tagged SPRA state and the existing SNES bridge differed in all 256 OAM bytes. The CPU/flag and last-byte-latch checks still passed, demonstrating why those checks alone do not certify destination-address behavior.

The existing WriteOamDma implementation copies to $7E3800 regardless of OADDR. The next change will retain the fast zero-offset copy and add a wrapping destination path, then test independent OAM contents, preserved registers/flags, subsequent writes and alternate interception paths.

This is a narrowly identified compatibility bug, not evidence that CV3's tested route uses a nonzero DMA offset. It is not a whole-game, speed, audio-fidelity or physical-console result.

This branch and this commit were written through the GitHub connector during the continuation. No additional repository authorization was required. This observation does not diagnose interrupted conversation responses.
