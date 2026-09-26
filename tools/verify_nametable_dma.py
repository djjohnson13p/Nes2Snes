#!/usr/bin/env python3
"""Execute both nametable uploaders on SNES hardware emulation.

The authored harness calls the actual project routines under forced blank.
Expected VRAM is computed from individual dirty rows, not the coalescing code.
No commercial input is needed; this is not an independent NES rendering test.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import subprocess
from build_viewer import ROOT, tool, finalize_rom
from libretro_runner import Runner

ROWS = 160

def expected_vram(initial: bytes, source: bytes, flags: bytes, enabled: bool) -> bytes:
    if len(initial) != 65536 or len(source) != 0x3000 or len(flags) != ROWS:
        raise ValueError('Wrong VRAM/source/dirty-map size')
    output = bytearray(initial)
    if enabled:
        for row, dirty in enumerate(flags):
            if not dirty:
                continue
            if row < 128:
                src, dst = row * 64, 0x4000 + row * 64
            else:
                src, dst = 0x2800 + (row - 128) * 64, 0x6000 + (row - 128) * 64
            output[dst:dst + 64] = source[src:src + 64]
    return bytes(output)

def expected_runs(flags: bytes, enabled: bool) -> int:
    if len(flags) != ROWS:
        raise ValueError('Wrong dirty-map size')
    # The two address regions must never form one run, even if adjacent flags
    # are both set. No copied gap bytes are permitted.
    return 0 if not enabled else sum(
        bool(flags[i]) and (i == begin or not flags[i - 1])
        for begin, end in ((0, 128), (128, 160)) for i in range(begin, end))

def cases() -> list[tuple[str, bytes, bool]]:
    result = [('empty', bytes(ROWS), True), ('gate-disabled', bytes([1]) * ROWS, False),
              ('dense', bytes([1]) * ROWS, True),
              ('actual-30-row-tables', bytes([1] * 30 + [0] * 2) * 5, True)]
    for i in range(ROWS):
        mask = bytearray(ROWS); mask[i] = 1 + i % 255
        result.append((f'single-{i}', bytes(mask), True))
    for i in range(ROWS - 1):
        mask = bytearray(ROWS); mask[i:i + 2] = b'\x01\xff'
        result.append((f'adjacent-{i}', bytes(mask), True))
    for parity in (0, 1):
        result.append((f'alternating-{parity}', bytes((i + parity) % 2 for i in range(ROWS)), True))
    rng = random.Random(0x4E3253)
    for n in range(96):
        threshold = (n % 8 + 1) / 9
        flags = bytes(rng.randrange(1, 256) if rng.random() < threshold else 0 for _ in range(ROWS))
        result.append((f'random-{n}', flags, n % 16 != 0))
    return result

HARNESS = '''.setcpu "65816"
UPLOAD=$0E00
UPLOAD_ANY=$0D66
VROW=$0C32
USE_COALESCED_NT_DMA=1
.segment "CODE"
.a8
.i8
Reset:
    sei
    cld
    clc
    xce
    rep #$30
.a16
.i16
    ldx #$1FFF
    txs
    lda #$0C00
    tcd
    sep #$20
.a8
    phk
    plb
    lda #$80
    sta $2100
    stz $4200
    stz $420B
    stz $420C
    stz $0500
    stz $0501
    lda #$5A
    sta $050F
Wait:
    lda $0500
    beq Wait
    pha
    stz $0508
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    pla
    cmp #$02
    beq New
    jsr UploadNametables
    bra Done
New:
    jsr UploadNametablesCoalesced
Done:
    php
    pla
    sta $0504
    rep #$20
.a16
    tsc
    sta $0502
    tdc
    sta $0506
    sep #$20
.a8
    stz $0500
    lda #$01
    sta $0501
    bra Wait
Irq:
    rti
'''
HEADER = '''
.segment "HEADER"
    .byte "N2S NAMETABLE TEST   "
    .byte $20,$00,$06,$00,$01,$00,$00
    .word $FFFF,$0000
.segment "VECTOR"
    .word $0000,$0000,Irq,Irq,Irq,Irq,$0000,Irq
    .word $0000,$0000,Irq,$0000,Irq,Irq,Reset,Irq
'''

def harness(out: Path, mutation: bool = False) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    text = (ROOT / 'snes/src/native_video.inc').read_text()
    old = text.split('\nUploadNametables:\n', 1)[1].split('\nUploadObjectsPalette:', 1)[0]
    old = 'UploadNametables:\n' + old
    new = (ROOT / 'snes/src/native_nametable_dma.inc').read_text()
    # Test-only negative control: move the HUD's source by a row. The actual
    # candidate file is unchanged. A full-frame comparison must detect this.
    if mutation:
        assert new.count('adc #$2800') == 1
        new = new.replace('adc #$2800', 'adc #$2840')
    routines = (old + '\n' + new).replace('    sta $420B', '    inc $0508\n    sta $420B')
    source = HARNESS + routines + HEADER
    (out / 'harness.s').write_text(source)
    subprocess.run([tool('ca65'), '-o', str(out / 'harness.o'), str(out / 'harness.s')], check=True)
    subprocess.run([tool('ld65'), '-C', str(ROOT / 'snes/linker/native.cfg'),
                    '-o', str(out / 'harness.bin'), str(out / 'harness.o')], check=True)
    rom = out / 'harness.sfc'
    rom.write_bytes(finalize_rom((out / 'harness.bin').read_bytes(), b''))
    return rom

def verify(core: Path, out: Path, mutation: bool = False) -> dict:
    rom = harness(out, mutation)
    runner = Runner(core, rom)
    rows = []
    # Non-periodic source bytes distinguish swapped/shifted rows.
    rng = random.Random(0xD0A)
    source = bytes(rng.randrange(256) for _ in range(0x3000))
    initial = bytes(rng.randrange(256) for _ in range(65536))
    try:
        runner.run(2)
        ram_ptr = runner.lib.retro_get_memory_data(2)
        video_ptr = runner.lib.retro_get_memory_data(3)
        if not ram_ptr or runner.lib.retro_get_memory_size(2) != 0x20000:
            raise RuntimeError('Require full SNES WRAM')
        if not video_ptr or runner.lib.retro_get_memory_size(3) != 0x10000:
            raise RuntimeError('Require raw SNES VRAM')
        if runner.memory()[0x50F] != 0x5A:
            raise RuntimeError('Harness did not boot')
        selected = [('dense', bytes([1]) * ROWS, True)] if mutation else cases()
        for name, flags, enabled in selected:
            expected = expected_vram(initial, source, flags, enabled)
            for mode in (1, 2):
                C.memmove(ram_ptr + 0x10000, source, len(source))
                C.memmove(video_ptr, initial, len(initial))
                C.memmove(ram_ptr + 0xE00, flags + b'\xA7\xB9', ROWS + 2)
                C.memmove(ram_ptr + 0xD65, bytes((0xA5, int(enabled), 0xB6)), 3)
                C.memmove(ram_ptr + 0x500, bytes((mode, 0)), 2)
                for _ in range(10):
                    runner.run(1)
                    memory = runner.memory()
                    if memory[0x501] == 1 and memory[0x500] == 0:
                        break
                else:
                    raise RuntimeError(f'{name}/{mode}: incomplete command')
                actual = runner.memory(3)
                differences = sum(a != b for a, b in zip(actual, expected))
                if differences:
                    raise RuntimeError(f'{name}/{mode}: {differences} VRAM bytes differ')
                if memory[0xE00:0xEA0] != (bytes(ROWS) if enabled else flags):
                    raise RuntimeError(f'{name}/{mode}: dirty map corruption')
                if memory[0xEA0:0xEA2] != b'\xA7\xB9' or memory[0xD65] != 0xA5 or memory[0xD67] != 0xB6:
                    raise RuntimeError(f'{name}/{mode}: out-of-range write')
                if memory[0xD66] != 0 or memory[0x502:0x504] != b'\xff\x1f' or memory[0x506:0x508] != b'\x00\x0c':
                    raise RuntimeError(f'{name}/{mode}: flag/stack/direct-page failure')
                if memory[0x504] & 0x30 != 0x20:
                    raise RuntimeError(f'{name}/{mode}: incorrect return widths')
                expected_count = (sum(bool(x) for x in flags) if enabled else 0) if mode == 1 else expected_runs(flags, enabled)
                if memory[0x508] != expected_count:
                    raise RuntimeError(f'{name}/{mode}: wrong transfer count {memory[0x508]} vs {expected_count}')
                rows.append(dict(case=name, mode='coalesced' if mode == 2 else 'legacy',
                                 dma_transfers=memory[0x508], vram_bytes_checked=65536, mismatches=0))
            if len(rows) % 100 == 0:
                print(f'{len(rows)} full-VRAM uploader checks complete', flush=True)
                (out / 'progress.json').write_text(json.dumps(dict(complete=False, checks=len(rows))) + '\n')
        result = dict(passed=True, configurations=len(rows), cases=len(selected),
                      vram_bytes_checked=len(rows) * 65536, mismatches=0,
                      core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                      harness_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                      scope='Actual project DMA routines executed under forced blank in unmodified Snes9x; independent row-write specification and full VRAM comparison. No NES/gameplay/active-display/cycle-equivalence claim.',
                      results=rows)
        (out / 'nametable-dma-verification.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    finally:
        runner.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mutation', action='store_true')
    args = parser.parse_args()
    result = verify(args.core, args.out, args.mutation)
    print(json.dumps({k: v for k, v in result.items() if k != 'results'}, indent=2))
