# Toolchain and provenance

Local development uses Python, ca65/ld65/da65 and separately built libretro cores. The conversation's local sandbox initially lacked the assembler and emulators and could not download dependencies directly. GitHub Actions built a tool bundle, which was retrieved through the GitHub connector and then executed locally. This was not a Codex/Work handoff.

- Assembler package: Ubuntu `cc65` 2.19-1; its ca65 version output is `ca65 V2.18 - Ubuntu 2.19-1`.
- Snes9x libretro source: `libretro/snes9x`, revision `fae2fea08f74180759ef540ee94259213f503480`.
- Tested Snes9x core SHA-256: `954fa8e0f80dd65f8a511189e2c9190ebdb80de753fc6dd9c6407530d990728f`.
- FCEUmm source: `libretro/libretro-fceumm`, revision `236ccdfc911e84c60fea6b9d0699c2d440a8de14`.
- Runtime probe: `tools/fceumm_probe.inc`, installed by `tools/instrument_fceumm.py`, then rebuilt locally.

External references:

- ca65 manual: https://cc65.github.io/doc/ca65.html
- da65 classification/reassembly manual: https://cc65.github.io/doc/da65.html
- FCEUmm implementation: https://github.com/libretro/libretro-fceumm
- Snes9x implementation: https://github.com/libretro/snes9x
- Existing third-party CV3 disassembly: https://github.com/vinheim3/castlevania3-disasm

The existing CV3 disassembly was discovered as a possible research reference. It has not been copied into this repository or independently verified against this exact upload. The current matching bank sources are generated from the uploaded ROM and this project's runtime trace, not claimed as work recovered from that third-party repository.

The public CI fixture is procedural and includes no commercial game data. Emulator binaries and game-derived build products are not committed. Respect the separate licenses of external emulator/toolchain projects, including FCEUmm's GPL terms when distributing a modified core and its corresponding source.
