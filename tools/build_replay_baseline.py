#!/usr/bin/env python3
"""Rebuild the pre-pipeline renderer with matching replay/capture instrumentation.

Reads source from an existing local git revision; does not fetch the network or
change the working tree. The two instrumentation hooks do not change rendering
or dispatch logic. Source ROM, trace and produced binary stay local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = '46e746935b647dd96271b0f30f1fbfbbdd6f76a1'

REPLAY = '''.if TEST_INPUT_REPLAY
    rep #$20
.a16
    lda GFRAMES
    cmp #REPLAY_LENGTH
    bcs @replayend
    tax
    sep #$20
.a8
    lda f:$800000+InputReplay,x
    bra @replayvalue
@replayend:
    sep #$20
.a8
    lda #$00
@replayvalue:
    sta JOYLATCH
    sta JOYSHIFT
    rts
.endif
'''


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError('Reference does not have the expected instrumentation site')
    return source.replace(old, new, 1)


def build(rom: Path, trace: Path, replay: Path, out: Path, reference: str = REFERENCE) -> dict:
    inputs = [p.resolve(strict=True) for p in (rom, trace, replay)]
    out = out.resolve()
    sources = {}
    for name in ('native.s', 'native_video.inc'):
        sources[name] = subprocess.check_output(
            ['git', '-C', str(ROOT), 'show', f'{reference}:snes/src/{name}'], text=True)
    if 'TEST_INPUT_REPLAY' in sources['native.s']:
        raise ValueError('Expected the pre-replay source revision')
    source_hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in sources.items()}
    sources['native.s'] = replace_once(sources['native.s'],
        '    jeq @done\n    rep #$20\n.a16\n    lda $4218',
        '    jeq @done\n' + REPLAY + '    rep #$20\n.a16\n    lda $4218')
    sources['native.s'] = replace_once(sources['native.s'],
        'RgbPalette: .incbin "palette.bin"',
        'RgbPalette: .incbin "palette.bin"\n.if TEST_INPUT_REPLAY\nInputReplay: .incbin "input-replay.bin"\n.endif')
    sources['native_video.inc'] = replace_once(sources['native_video.inc'],
        '@remainblank:\n    rep #$20\n.a16\n    lda #$0000',
        '@remainblank:\n    rep #$20\n.a16\n    lda GFRAMES\n    sta $0974\n    lda #$0000')
    with tempfile.TemporaryDirectory(prefix='nes2snes-baseline-') as directory:
        temp = Path(directory)
        for folder in ('tools', 'snes'):
            shutil.copytree(ROOT / folder, temp / folder, ignore=shutil.ignore_patterns('__pycache__'))
        for name, text in sources.items():
            (temp / 'snes/src' / name).write_text(text)
        subprocess.run([sys.executable, str(temp / 'tools/build_native.py'),
                        '--rom', str(inputs[0]), '--trace', str(inputs[1]),
                        '--input-replay', str(inputs[2]), '--out', str(out),
                        '--synchronous-video', '--no-object-cache'], check=True)
    result = dict(reference_revision=reference, reference_source_sha256=source_hashes,
                  instrumented_rom_sha256=hashlib.sha256((out / 'native-prototype.sfc').read_bytes()).hexdigest(),
                  instrumentation='Guest-frame input lookup and presented-frame counter only.')
    (out / 'baseline-provenance.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'trace', 'replay', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reference', default=REFERENCE)
    args = parser.parse_args()
    print(json.dumps(build(args.rom, args.trace, args.replay, args.out, args.reference), indent=2))
