#!/usr/bin/env python3
"""Original zero-offset sprite-DMA inputs and PPU I/O-latch readback.

This does not test OAMADDR rotation, active-rendering access, I/O source pages,
or the guest-stack page. Each case initializes its entire RAM source first.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from native_fixture import Program, write_program

RAM_PAGES = (2, 4, 5, 6, 7, 0x0a, 0x12, 0x1a, 0x1f)
ROM_PAGES = (0x80, 0xc0, 0xff)


def create(out: Path, page: int = 2, seed: int = 0, c0: bool = False,
           writer: str = 'STA') -> dict:
    if page not in RAM_PAGES + ROM_PAGES or writer not in ('STA', 'STX', 'STY'):
        raise ValueError('Unsupported procedural DMA case')
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    for addr, value in ((0x2000, 0), (0x2001, 0), (0x4017, 0x40),
                        (0x5100, 2), (0x5115, 0x9e if c0 else 0x80),
                        (0x5116, 0x87 if c0 else 0x9e)):
        p.op('LDA', 'imm', value); p.op('STA', 'abs', addr)
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7e)
    # Allow the independent NES power-on write-suppression interval to expire.
    p.op('LDY', 'imm', 32); p.label('warm_outer'); p.op('LDX', 'imm', 0)
    p.label('warm_inner'); p.op('DEX'); p.op('BNE', 'rel', 'warm_inner')
    p.op('DEY'); p.op('BNE', 'rel', 'warm_outer')
    p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x2001)
    if page < 0x20:
        for i in range(256):
            p.op('LDA', 'imm', ((i * 37) ^ (i >> 1) ^ (seed * 29)) & 255)
            p.op('STA', 'abs', ((page & 7) << 8) + i)
    p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x2003)
    p.op('LDA', 'imm', 0x7f); p.op('CLC'); p.op('ADC', 'imm', 1)
    p.op('LDA', 'imm', page if writer == 'STA' else 0x81)
    p.op('LDX', 'imm', page if writer == 'STX' else 0x91)
    p.op('LDY', 'imm', page if writer == 'STY' else 0xa3)
    p.op('SEC'); p.op(writer, 'abs', 0x4014)
    p.record('dma_preserves_registers_and_flags')
    # Neither read alters the bus latch; the last DMA byte must remain visible.
    p.op('LDA', 'abs', 0x2001); p.record('last_dma_byte_on_ppu_latch')
    p.op('LDA', 'abs', 0x3ff9); p.record('mirrored_ppu_latch')
    p.op('LDA', 'imm', 0x5a); p.op('STA', 'zp', 0x7e)
    p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta.update(oam_copy_fixture=True, page=page, seed=seed, c0=c0,
                writer=writer, oam_address=0)
    (out / 'trace-summary.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--page', type=lambda x: int(x, 0), default=2)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--c0', action='store_true')
    ap.add_argument('--writer', choices=('STA', 'STX', 'STY'), default='STA')
    a = ap.parse_args()
    print(json.dumps(create(a.out, a.page, a.seed, a.c0, a.writer), indent=2))
