#!/usr/bin/env python3
"""Authored forced-blank PPUDATA palette/buffer fixture; no game-derived bytes.

Records full CPU results, including flags. In particular, palette data is NOT
masked by the test program before comparison with an independent NES emulator.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from native_fixture import Program, write_program


def create(out: Path, seed: int = 0, bank: int = 0) -> dict:
    if type(seed) is not int or not 0 <= seed <= 255:
        raise ValueError('seed must be a byte')
    if type(bank) is not int or bank not in (0, 1, 3):
        raise ValueError('bank must select CIRAM 0, CIRAM 1, or MMC5 fill')
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('LDX', 'imm', 0); p.label('clear')
    for a in range(0, 0x800, 256): p.op('STA', 'absx', a)
    p.op('INX'); p.op('BNE', 'rel', 'clear')
    for label in ('warmup1', 'warmup2'):
        p.label(label); p.op('LDA', 'abs', 0x2002); p.op('BPL', 'rel', label)

    def store(address: int, value: int) -> None:
        p.op('LDA', 'imm', value & 255); p.op('STA', 'abs', address)

    def address(value: int) -> None:
        store(0x2006, value >> 8); store(0x2006, value)

    def write(value: int, data: int) -> None:
        address(value); store(0x2007, data)

    for a, v in ((0x5100, 2), (0x5115, 0x80), (0x5116, 0x9e),
                 (0x5105, bank * 0x55), (0x2000, 0), (0x2001, 0)):
        store(a, v)
    # Palette reads through absolute, register-mirrored absolute, indexed
    # absolute and indirect-Y paths. Indexed accesses deliberately do not cross
    # a page here: dummy-read semantics have their own retained fixture.
    modes = ('absolute', 'register-mirror', 'indexed', 'indirect')
    targets = [0x3f00 + i for i in range(32)] + [0x3f30, 0x3f54, 0x3f98, 0x3fdc, 0x3fff]
    cases = []
    for i, target in enumerate(targets):
        increment = 32 if (i + seed) & 1 else 1
        gray = ((i // 2) + seed) & 1
        high = ((i + seed) & 3) << 6
        mode = modes[(i // 4 + seed) & 3]
        store(0x2000, 0); store(0x2001, gray)
        store(0x5106, 0x80 + ((i * 7 + seed) & 0x7f))
        store(0x5107, i + seed)
        # Shadow reads must use the original address, not the aliased palette
        # index. Consecutive palette reads must each refresh the delayed buffer.
        shadow = target - 0x1000
        write(shadow, (0x83 + i * 11 + seed) & 255)
        following = (target + increment) & 0x3fff
        if following >= 0x3f00:
            write(following - 0x1000, (0x51 + i * 13 + seed) & 255)
            write(following, (0x65 + i * 3 + seed) & 255)
        write(target, (0xc7 + i * 5 + seed) & 255)
        store(0x2000, 4 if increment == 32 else 0)
        address(target)
        p.op('LDX', 'imm', 1); p.op('LDY', 'imm', 1)
        store(0x40, 6); store(0x41, 0x20)
        store(0x2003, high | 0x1b)  # prime the PPU I/O latch without changing v
        p.op('CLV'); p.op('SEC' if i & 1 else 'CLC')
        def read_data() -> None:
            if mode == 'absolute': p.op('LDA', 'abs', 0x2007)
            elif mode == 'register-mirror': p.op('LDA', 'abs', 0x3fff)
            elif mode == 'indexed': p.op('LDA', 'absx', 0x2006)
            else: p.op('LDA', 'iy', 0x40)
        read_data(); p.record(f'{i:02d}_palette')
        # A write-only PPU register returns the entire refreshed I/O latch.
        p.op('LDA', 'abs', 0x2000); p.record(f'{i:02d}_io_latch')
        read_data(); p.record(f'{i:02d}_next_read')
        address(0x2000)
        p.op('LDA', 'abs', 0x2007); p.record(f'{i:02d}_shadow_buffer')
        cases.append(dict(address=target, increment=increment, grayscale=bool(gray),
                          bus_high=high, mode=mode, nametable_source=bank))
    store(0x7e, 0x5a)
    p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta.update(palette_read_fixture=True, seed=seed, bank=bank, cases=cases,
                scope='Forced blanking, no DMC or palette I/O latch decay; not raster timing')
    (out/'trace-summary.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--bank', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(create(args.out, args.seed, args.bank), indent=2))
