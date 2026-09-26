#!/usr/bin/env python3
"""Original black/white NES scene exercising independent left-edge masks.

The input is assembled from this source; it contains no commercial graphics.
All sprites are below the eight-per-line NES limit. The test uses a steady
frame, so presentation latency cannot account for a pixel mismatch.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from native_fixture import Program, write_program


def create(out: Path, mask: int = 0x18, sprite16: bool = False, split_mask: int | None = None, split_line: int = 96, cycle: bool = False) -> dict:
    if type(mask) is not int or not 0 <= mask <= 0x1e or mask & 1:
        raise ValueError('Mask must be an even integer from 0 through 30')
    if type(sprite16) is not bool:
        raise ValueError('sprite16 must be a bool')
    if type(cycle) is not bool:
        raise ValueError('cycle must be a bool')
    if cycle and split_mask is not None:
        raise ValueError('Cycle and split cannot be combined')
    if split_mask is not None:
        if type(split_mask) is not int or not 0 <= split_mask <= 0x1e or split_mask & 1:
            raise ValueError('Split mask must be an even integer from 0 through 30')
        if not mask & 0x18:
            raise ValueError('MMC5 split requires rendering enabled in the top region')
        if type(split_line) is not int or not 9 <= split_line <= 135:
            raise ValueError('Split line must be an integer from 9 through 135')
    p = Program()
    def write(address: int, value: int) -> None:
        p.op('LDA', 'imm', value); p.op('STA', 'abs', address)
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    write(0x2000, 0); write(0x2001, 0)
    for address, value in ((0x5100, 2), (0x5115, 0x80), (0x5116, 0x9e),
                           (0x5101, 3), (0x5104, 0), (0x5105, 0x44)):
        write(address, value)
    for i in range(8): write(0x5120+i, i)
    for i in range(4): write(0x5128+i, i)
    write(0x2006, 0x3f); write(0x2006, 0)
    for i in range(32): write(0x2007, 0x0f if i%4 == 0 else 0x30)
    # Repeated nonuniform background, deliberately distinct from the objects.
    write(0x2006, 0x20); write(0x2006, 0)
    p.op('LDA', 'imm', 0); p.op('LDY', 'imm', 4); p.op('LDX', 'imm', 0)
    p.label('fill'); p.op('STA', 'abs', 0x2007); p.op('INX')
    p.op('BNE', 'rel', 'fill'); p.op('DEY'); p.op('BNE', 'rel', 'fill')
    # Hide all unused objects before replacing the first 18 entries.
    p.op('LDA', 'imm', 0xf0); p.op('LDX', 'imm', 0); p.label('hide')
    p.op('STA', 'absx', 0x200); p.op('INX'); p.op('BNE', 'rel', 'hide')
    count = 0
    for y in (40, 88, 160):
        for x in (0, 4, 8, 24, 240, 248):
            for j, value in enumerate((y-1, 1 if sprite16 else 0, 0, x)):
                write(0x200+4*count+j, value)
            count += 1
    write(0x70, 0)
    ctrl = 0xa8 if sprite16 else 0x88
    write(0x2000, ctrl)
    p.op('CLI')
    p.label('main'); p.op('JMP', 'abs', 'main')
    p.label('nmi'); p.op('PHA'); p.op('INC', 'zp', 0x70)
    write(0x4014, 2); p.op('LDA', 'abs', 0x2002)
    write(0x2006, 0x20); write(0x2006, 0)
    write(0x2005, 0); write(0x2005, 0); write(0x2000, ctrl)
    if cycle:
        p.op('LDA', 'zp', 0x70)
        p.op('LSR', 'acc'); p.op('LSR', 'acc'); p.op('LSR', 'acc')
        p.op('AND', 'imm', 0x1e); p.op('STA', 'abs', 0x2001)
    else:
        write(0x2001, mask)
    if split_mask is not None:
        write(0x5203, split_line); write(0x5204, 0x80)
    p.op('PLA'); p.op('RTI')
    if split_mask is not None:
        p.label('irq'); p.op('PHA'); p.op('LDA', 'abs', 0x5204)
        write(0x2001, split_mask); write(0x5204, 0)
        p.op('PLA'); p.op('RTI')
    meta = write_program(out, p)
    raw = bytearray((out/'fixture.nes').read_bytes())
    if split_mask is not None:
        struct.pack_into('<H', raw, 16+0x3fffe, p.labels['irq'])
    chr_data = bytearray(0x20000)
    for row in range(8):
        chr_data[row] = (0xb6, 0x6d, 0xdb, 0x96, 0x69, 0xa5, 0x5a, 0xc3)[row]
        chr_data[0x1000+row] = 0xff
        chr_data[0x1010+row] = 0xff
    raw[16+0x40000:] = chr_data
    (out/'fixture.nes').write_bytes(raw)
    palette = bytearray(192); palette[0x30*3:0x30*3+3] = bytes((248, 248, 248))
    (out/'rgb-palette.bin').write_bytes(palette)
    meta.update(rom_sha256=hashlib.sha256(raw).hexdigest(), mask_fixture=True,
                mask=mask, cycle=cycle, sprite16=sprite16, split_mask=split_mask, split_line=split_line if split_mask is not None else None, scope='steady-state binary geometry, left-edge masks; not color fidelity')
    (out/'trace-summary.json').write_text(json.dumps(meta, indent=2)+'\n')
    return meta

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mask', type=lambda n: int(n, 0), default=0x18)
    parser.add_argument('--sprite16', action='store_true')
    parser.add_argument('--cycle', action='store_true')
    parser.add_argument('--split-mask', type=lambda n: int(n, 0))
    parser.add_argument('--split-line', type=int, default=96)
    args = parser.parse_args()
    print(json.dumps(create(args.out, args.mask, args.sprite16, args.split_mask, args.split_line, args.cycle), indent=2))
