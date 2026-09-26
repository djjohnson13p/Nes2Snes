# Conservative RAM and simple-I/O paths — 2026-09-25

This continues the [native audio and interrupt-safety checkpoint](direct-audio-2026-09-25.md). It is not a complete port, full-speed result, or faithful NES APU implementation.

## Changes retained

`native_safe.py` replaces only classified memory instructions whose RAM address can be preserved for **every** 8-bit index: indexed zero-page base zero, ordinary internal-RAM mirrors, and indexed mirrors whose entire range stays within the same 2-KiB RAM window. It does not infer index ranges from a limited playthrough. Eight sites in this CV3 build qualify. Original raw-data banks remain unchanged.

Simple absolute PPU and IRQ writes use a shorter context handler. The selected writers preserve X, Y, D and DBR; their veneer preserves guest P and X, and the handler saves/restores full A. OAM, data-port and controller operations keep the full context path. Execution bank C0 keeps COP fallback. The existing host-PBR and veneer-PC NMI gates remain in effect.

`--no-safe-addresses` and `--no-simple-direct` independently disable the new paths. The hidden-sprite semantic-cache experiment was discarded: it showed no useful frame-time improvement. No emulator overclock or game-logic frame skipping is used.

## Fresh verification

- **102 unit tests pass**, including exhaustive address/index checks over the selected RAM-mirror domain.
- **1,438 CPU/PPU records / 5,752 register-and-flag bytes** match independent FCEUmm and Snes9x cores. This includes 116 new zero-base and RAM-boundary records; that fixture executes with zero COP calls when the new substitutions are enabled. A separate all-bank fixture verifies 95 direct writes including initialization, plus the C0 fallback.
- **160 animated object frames / 81,920 OAM bytes** match the independent procedural encoding checks.
- Four procedural audio cases (enabled, silent, legacy direct-call fallback, forced nested NMI) pass again. These check tones/mute, not complete NES APU fidelity.
- **Five selected gameplay captures / 286,720 pixels** match checkpoint 5645950 after render-frame alignment. This is not every frame or every route.
- The ordinary-controller audio and silent builds independently pass startup, walking, jumping and attacking. The audio run produces a 15.62-second live capture with no full-scale PCM samples, SPC ready=1, fault=0 and 2,088 acknowledged DSP commands. It is not a recording played back by the game.

## Timing

Same fixed logical-frame inputs and unmodified Snes9x core:

| Segment | Logical updates | Pipelined checkpoint 5645950 | Current with audio |
|---|---:|---:|---:|
| Walking | 120 | 242 host frames | 237 host frames |
| Jumping | 25 | 56 | 50 |
| Attacking | 25 | 50 | 50 |
| Settling | 60 | 120 | 120 |

Walking throughput improves 2.11% from 5645950, and jumping 12%. Relative to the first audio checkpoint, walking changes only from 240 to 237 host frames (1.27%). The current walking ratio is **1.975 display frames per game update**, still approximately half speed. The small gains must not be described as full-speed or faster-than-NES operation.

## Reproducible builds

```sh
python3 -m unittest discover -s tests -v
python3 tools/safe_address_fixture.py --out build/safe-address-fixture
python3 tools/build_native.py --rom build/safe-address-fixture/fixture.nes --trace build/safe-address-fixture --out build/safe-address-fixture/snes
python3 tools/verify_native_cpu.py --nes-core /path/to/fceumm.so --snes-core /path/to/snes9x.so --fixture build/safe-address-fixture --out build/safe-address-fixture/verification
```

Supply the user's authorized CV3 ROM and matching classified trace to build the interactive version. Omit `--input-replay`; audio is opt-in with `--experimental-audio`.

Interactive audio SHA-256: `795744bbf4eb4188c4fac430a4a07444998424bad9abb2b6a2590df999d7cf6d`.

Interactive silent SHA-256: `8bd11b7d4ecdee95aa7ec51af930bf4b5081d6d0485b4049380907dc2988bf3e`.

## Unfinished

All limitations of the earlier audio checkpoint remain: approximate four-voice sound without envelopes, length/linear-counter fidelity, sweep, DMC or expansion audio; incomplete gameplay-path coverage; bounded mapper/IRQ behavior; deliberately halted unclassified code; no physical-console test. Profiling identified substantial instruction-bridge overhead, but does not establish that a particular further optimization will achieve full speed.

See [machine-readable evidence](safe-address-verification.json).
