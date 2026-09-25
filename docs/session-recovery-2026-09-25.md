# Session recovery and fresh build verification — 2026-09-25

This records a new local build/test run after the conversation appeared to stall. It is not a new gameplay or performance milestone.

## Recovered input

- Source revision tested: `ac738dfecf4cb094e1294b5eb37aa080d25b0d09`.
- Recovery workflow run: `36189372731`.
- Recovery artifact: `10886953705` (`recoverable-workspace`).
- All nine entries in the recovery SHA256SUMS file were checked and matched.
- The ZIP stores files at its root; SHA256SUMS paths retain the original `recovery/` prefix. Remove that prefix when verifying against the extracted ZIP root.
- The restored ca65 executable identifies itself as `ca65 V2.18 - Ubuntu 2.19-1`.

## Checks executed again

1. `python3 -m unittest discover -s tests -v`: **54 tests passed**.
2. `python3 tools/native_fixture.py --out build/session-health/native-fixture`: generated the procedural NES CPU/mapper fixture.
3. `python3 tools/build_native.py --rom build/session-health/native-fixture/fixture.nes --trace build/session-health/native-fixture --out build/session-health/native-fixture/snes`: assembled and linked a fresh 4,194,304-byte SNES ROM.
4. `python3 tools/verify_native_cpu.py --nes-core <recovery>/cores/fceumm_reference.so --snes-core <recovery>/cores/snes9x_libretro.so --fixture build/session-health/native-fixture --out build/session-health/native-fixture/verification`: executed the fixture in independent NES and SNES cores. **180 records / 720 register-and-flag bytes compared; zero mismatches**.

Fresh SNES fixture SHA-256: `ee3cab5d3e647d741db4e9c205edef8e793f12f3e467bc283004bd1f084d9323`.

## Scope and limitations

These fresh checks establish that the source recovery, assembler/linker, Python tests, and emulator-based native CPU/mapper verification work in the current conversation runtime. This was not a fresh full-game CV3 playthrough, and no speedup, audio implementation, or complete port is claimed.

The uploaded CV3.nes file remains available locally. It was not uploaded to this public repository. The restored workspace initially had no assembler on PATH. A direct git clone failed because the container could not resolve github.com, but the GitHub connector could read the repository and deliver the recovery artifact. Recovery therefore did not require direct container Internet access.

None of these observations diagnose why the ChatGPT interface stopped producing responses. They distinguish the functioning project/build pipeline from the unresolved conversation-generation symptom.
