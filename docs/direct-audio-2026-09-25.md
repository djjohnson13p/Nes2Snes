# Direct accesses, interrupt recovery and experimental audio

This checkpoint continues source revision `5645950a620da85464c1e37c3d50342500aa439e`.
It is an early interactive port, not a completed game. The original ROM and all
game-derived images, WAV files and binaries remain outside this public repository.

## New implementation

Selected classified, three-byte absolute accesses use same-size JSR instructions
into reserved WRAM veneers, with register/flag-preserving host handlers. Other
accesses retain the existing COP path. Live PRG selectors are never converted.
Execution bank `$C0` also retains COP because it lacks the low WRAM mirror used by
the veneers. Raw ROM data remains separate and unchanged. `--no-direct-calls`
restores the older interception path.

Sprite-cache checks can be unrolled; unchanged objects avoid repeated index
arithmetic. `--no-unrolled-objects` restores the old loop. This supplied no extra
whole-display-frame speed gain in the selected route; it is not reported as one.

A latent interrupt bug was exposed by audio-related timing changes: after
`RUNNING` cleared but before `NmiRestore` completed, a second host NMI could
replace the still-live guest context. The dispatcher now rejects host-code
interrupts before writing `NCTX`. The test-only `--stress-nmi-restore` delay
forces repeated interrupts in that window. The fixed procedural fixture passes;
removing only the new gate causes the same stressed fixture to stop progressing.
The delay is not present in normal builds.

## First native audio preview — explicitly incomplete

`--experimental-audio` builds and uploads an original SPC700 DSP-command receiver
and five procedural BRR waves. The running NES game supplies its APU register
values; four native DSP voices approximate its two pulses, triangle and noise.
Mailbox acknowledgements have bounded timeouts, cached DSP values avoid unchanged
writes, and failure disables further commands rather than hanging indefinitely.
The driver and wave data are authored in this project, not imported from a game.

**Not implemented:** hardware envelopes, length counters, triangle linear-counter
timing, sweep, accurate noise mode/rates, DMC samples, expansion sound and
cycle-accurate phase/retrigger behavior. Notes can sustain incorrectly; percussion
and sampled sounds can be missing or different. This is not remastered audio or
a claim of NES APU equivalence. Music sequencing still runs at the slowed logical
game rate. The default build remains silent; audio is an explicit preview option.

A fresh normal-controller test completed startup, first-stage walking, jumping
and attacking with audio enabled. Its 15.89-second stage-one PCM capture is
nonzero, has 2,088 DSP command acknowledgements, no mailbox fault and no full-scale
PCM samples. Those measurements establish working output, not audio fidelity.

## Measured performance

Same fixed guest-input script, independently executed with the unmodified Snes9x
core, compared to a fresh build of the previous checkpoint:

| Interval | Game updates | Previous SNES frames | New audio build SNES frames |
|---|---:|---:|---:|
| Walk right | 120 | 242 | 240 |
| Jump right | 25 | 56 | 50 |
| Attack | 25 | 50 | 50 |
| Settle | 60 | 120 | 120 |

Walking throughput increases about 0.83%; jumping throughput increases 12%.
The updated silent candidate produces the same intervals. The audio-enabled
normal-controller test separately produces 240/50/50/120 on these intervals.
**This is still about two SNES frames per logical game frame, not full speed or
an improvement over the NES original.** Host instruction histograms were used
for exploration only; they are not cycle measurements or the correctness oracle.

All five selected render-aligned images match the prior renderer: 286,720 pixels,
zero differences. These are selected captures, not every game frame.

## Fresh verification

- 90 Python unit tests passed.
- 1,322 differential NES/SNES CPU/PPU records, containing 5,288 register-and-flag
  bytes, matched. This includes 192 new store/flag records across all 32 mapped
  execution combinations, testing `$C0` fallback as well as direct accesses.
- 160 animated procedural sprite frames matched their independent encoding model:
  81,920 object-buffer bytes, zero differences, all four tested sprite modes.
- Four original audio fixture configurations passed: audio enabled, audio disabled
  (silence), legacy interception/indexed objects, and forced nested NMI.
- Measured tone fundamentals are approximately 441.4 Hz, 882.8 Hz and 219.7 Hz,
  versus generated targets of 440.43 Hz, 880.86 Hz and 220.21 Hz. Noise is nonzero
  and the designated muted segment contains all-zero PCM.

All audio/CPU correctness checks use the unmodified independent emulator cores.
The Snes9x core SHA-256 for this run is
`89f581685aa126fad2ba6518cc7534e2174322d6db9ff278cb948ad53719dcc3`.
The detailed build hashes, counters and measurements are in
[direct-audio-verification.json](direct-audio-verification.json).

## Reproduce

With an authorized local ROM, the previously generated extended trace and the
pinned external tools:

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_native.py --rom original/CV3.nes --trace build/trace \
  --out build/audio-preview --experimental-audio
python3 tools/capture_game_audio.py --core /path/to/snes9x_libretro.so \
  --rom build/audio-preview/native-prototype.sfc --out build/audio-preview/check
python3 tools/verify_audio_matrix.py --core /path/to/snes9x_libretro.so \
  --out build/audio-matrix
```

The matrix is source-only and needs no commercial ROM. A normal build without
`--experimental-audio` remains available as the silent fallback. Neither
`--input-replay` nor `--stress-nmi-restore` belongs in a distributed interactive
build: both are explicitly test-only modes.

SPC protocol and DSP register reference consulted: eKid's authored
[SPC700 reference](https://wiki.superfamicom.org/spc700-reference).
The implementation is original and validated by actual DSP output, not solely
by agreement with generated tables.

## Remaining work

Full-speed execution, broader level/character/death/restart coverage, accurate
APU behavior, DMC playback, complicated display effects and physical SNES
validation remain outstanding. Unsupported guest execution still fails closed.
