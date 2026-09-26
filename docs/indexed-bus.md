# Indexed memory fast paths and missing NES dummy reads

This continues source revision `9437d881220456d269fa96bbaa8150e0a2ab1dfb`.
It is not a complete, full-speed or cycle-accurate CV3 port. All game-derived
builds, audio, traces and screenshots remain private, outside this repository.

## Correctness bug found and fixed

NMOS 6502 indexed stores and indexed read-modify-write instructions perform an
intermediate read before the actual access. Indexed reads also do so when the
address crosses a page. The intermediate address retains the base address's
high byte and the effective address's low byte. Discarding the returned byte
does not discard register side effects: reading $2007 advances the PPU address,
and reading $2002 clears the PPU address-write toggle.

The prior bridge omitted these side effects. A new independent NES/SNES fixture
exposed the bug. The unmodified prior runtime fails **60 of its 131 records**;
the corrected runtime matches all 131. The test includes absolute-X,
absolute-Y, indirect-Y, page crossings, six RMW operations and a status-toggle
case. Real NES power-on PPU write suppression is allowed to expire first, and
all referenced nametable data is initialized; uninitialized values are not an
oracle.

The generic bridge now reproduces these intermediate reads for supported
side-effecting PPU, controller, APU-status and mapper-IRQ addresses. Dummy reads
of ordinary RAM and ROM are omitted because the current bridge does not model
CPU bus cycles, MMC5 PCM-read mode or complete open-bus behavior. This is a fix
for tested register side effects, not a claim of cycle-exact CPU emulation.

Reference inspected: FCEUmm `src/x6502.c` at
`236ccdfc911e84c60fea6b9d0699c2d440a8de14`, specifically its indexed addressing
and read/store/RMW dispatch. The new assembly is project-authored. The oracle
uses the pinned unmodified NES emulator, not a model derived from this assembly.

## Optimizations retained

A runtime-checked path handles selected LDA, STA, AND, ORA, EOR, ADC, SBC and CMP
absolute-indexed instructions. Effective addresses retain 16-bit wrapping;
internal RAM addresses fold to 2 KiB; data reads use the original, unmodified
ROM bank. Guest accumulator, index registers and flags are preserved or updated
according to the actual operation. Hardware and cartridge-RAM reads, PPU writes,
ROM stores and mapper writes still use the generic compatibility path.

Selected indexed APU writes reuse the existing event-driven sound handler,
including repeated identical reload writes. Operations whose intermediate
address can be a PPU register fall back to the corrected generic handler.
OAM DMA and joypad-strobe writes also remain on that handler.

`--no-quick-indexed` disables the new optimization while retaining the dummy-read
correctness fix. No overclock, emulated game-frame skipping, or unproven index
range assumptions are introduced. Diagnostic counters occupy previously unused
WRAM $0990-$099B; INDEXBASE and DUMMYADDR use generic scratch $082C-$082F.

## Executed verification

- **178 unit tests pass.**
- **11 new independent configurations, 1,425 records / 5,700 register-and-flag
  bytes, zero mismatches.** These cover randomized arithmetic and carry/overflow,
  RAM mirrors, 16-bit wrap, selected ROM maps, C0 execution, disabled fast paths,
  APU reloads, joypad/OAM fallback and PPU dummy-read side effects.
- Every enabled indexed-memory/APU path is checked for a nonzero execution
  counter. The bus fixture checks 36 intermediate I/O reads per configuration.
- The negative control is the actual preceding source revision: **60 mismatches**
  prove that the new PPU test detects the old implementation's missing effects.
- **Five render-aligned gameplay captures, 286,720 pixels, zero differences**
  versus the prior SNES renderer. This is not an all-frame NES comparison.
- The ordinary-controller **31-step approach plus 57-action staircase route**
  completes, with game-state and candidate player X/Y bytes matching at all 57
  endpoints. It is not a boss clear or whole-game validation.
- The ordinary-controller audio run completes startup, walking, jumping and
  attacking. Its live PCM capture is approximately 15.42 seconds, with no clipped
  samples, SPC ready=1, fault=0 and 2,282 acknowledged DSP commands. This checks
  output and responsiveness, not authentic sound fidelity.

## Performance

Same trace, flags, fixed guest-frame inputs and unmodified Snes9x core:

| Interval | Logical updates | Previous sweep checkpoint | New build |
|---|---:|---:|---:|
| Walking | 120 | 239 display frames | 235 |
| Jumping | 25 | 50 | 50 |
| Attacking | 25 | 50 | 50 |
| Settling | 60 | 120 | 120 |

Walking throughput improves **1.70%**, with approximately **1.958 display frames
per logical update**. This is a small improvement, not full speed or an
improvement over the NES original. Profiling used a separately instrumented core
only for locating hot routines; all comparisons above use unmodified cores.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_indexed_matrix.py --nes-core /path/to/fceumm_reference.so \
  --snes-core /path/to/snes9x_libretro.so --out build/indexed-matrix
python3 tools/build_native.py --rom original/CV3.nes --trace /path/to/trace \
  --out build/indexed-preview --experimental-audio --audio-counters \
  --audio-sweep --experimental-raster-scroll
```

The first two commands need no commercial ROM. Ordinary interactive builds must
not use test replay or stress-delay options. Detailed measurements, input/core
hashes, negative-control results and limitations are in
[indexed-bus-verification.json](indexed-bus-verification.json).

## Still unfinished

Full-speed execution, complete level/character/boss/ending coverage, exact sound
and raster timing, DMC samples, other unimplemented sound behavior and physical
SNES testing remain outstanding. This fix does not resolve the documented
partial-row rendering differences or reference-emulator disagreement. Unknown
code paths still halt deliberately. The new boundary tests strengthen one part
of the implementation; they do not establish a perfect port.
