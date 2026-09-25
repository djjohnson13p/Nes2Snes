# Nes2Snes

An experimental, source-only NES-to-SNES reverse-engineering and porting workspace.

**Status: initial tooling under development. This is not a playable CV3 port and is not a general-purpose ROM converter.**

Work is being implemented and tested from the ChatGPT conversation, without a Codex/Work handoff. Build and emulator checks may also use GitHub Actions.

## Source ROM handling

Do not commit commercial ROMs, extracted game assets, or generated game-derived binaries. Keep those in an ignored local `original/` or `build/` directory. Public tests use procedurally generated graphics, not commercial game content.

## Initial milestones

1. Validate the supplied ROM, identify its exact binary layout and hashes, and extract assets locally.
2. Build a native SNES graphics-viewer ROM with converted NES tiles, controller input, and DMA uploads.
3. Verify the build with an independent assembler and an SNES emulator.
4. Reconstruct and validate the original game execution paths before porting gameplay.

Progress is recorded in `docs/` as implementation and testing proceed. A rendered graphics viewer must not be described as a playable game port.
