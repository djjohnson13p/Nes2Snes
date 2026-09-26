#!/usr/bin/env python3
"""Original sprite-DMA inputs and PPU I/O-latch readback.

Supports destination offsets while rendering is disabled. Active-rendering
access, I/O source pages and guest-stack DMA are outside this fixture.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from native_fixture import Program, write_program

RAM_PAGES = (2, 4, 5, 6, 7, 0x0a, 0x12, 0x1a, 0x1f)
ROM_PAGES = (0x80, 0xc0, 0xff)


def create(out: Path, page: int = 2, seed: int = 0, c0: bool = False,
           writer: str = 'STA', oam_address: int = 0,
           post_write: int | None = None, mutate_source: bool = False,
           neutral_latch: bool = False, stream_offsets: bool = False) -> dict:
    if type(neutral_latch) is not bool or type(stream_offsets) is not bool:
        raise ValueError('Fixture mode switches must be booleans')
    if stream_offsets and (post_write is not None or mutate_source):
        raise ValueError('Streaming does not combine source or post-write variants')
    if page not in RAM_PAGES + ROM_PAGES or writer not in ('STA', 'STX', 'STY'):
        raise ValueError('Unsupported procedural DMA case')
    if type(oam_address) is not int or not 0 <= oam_address <= 255:
        raise ValueError('OAM address must be a byte')
    if post_write is not None and (type(post_write) is not int or not 0 <= post_write <= 255):
        raise ValueError('Post-write must be a byte or None')
    if type(mutate_source) is not bool or (mutate_source and page >= 0x20):
        raise ValueError('Source mutation requires an ordinary RAM page')
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
            value = ((i * 37) ^ (i >> 1) ^ (seed * 29)) & 255
            # Isolate OAM wrapping from the documented reference disagreement
            # over absent attribute bits on the final DMA byte's I/O latch.
            if neutral_latch and i == 255: value &= 0xe3
            p.op('LDA', 'imm', value)
            p.op('STA', 'abs', ((page & 7) << 8) + i)
    if stream_offsets:
        if post_write is not None or mutate_source:
            raise ValueError('Streaming fixture does not combine source/post-write variants')
        p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7c)
        p.label('offset_iteration'); p.op('LDA', 'zp', 0x7c)
    else:
        p.op('LDA', 'imm', oam_address)
    p.op('STA', 'abs', 0x2003)
    p.op('LDA', 'imm', 0x7f); p.op('CLC'); p.op('ADC', 'imm', 1)
    p.op('LDA', 'imm', page if writer == 'STA' else 0x81)
    p.op('LDX', 'imm', page if writer == 'STX' else 0x91)
    p.op('LDY', 'imm', page if writer == 'STY' else 0xa3)
    p.op('SEC'); p.op(writer, 'abs', 0x4014)
    p.record('dma_preserves_registers_and_flags')
    # Neither read alters the bus latch; the last DMA byte must remain visible.
    p.op('LDA', 'abs', 0x2001); p.record('last_dma_byte_on_ppu_latch')
    p.op('LDA', 'abs', 0x3ff9); p.record('mirrored_ppu_latch')
    if post_write is not None:
        # A full DMA wraps back to its initial OAMADDR. This store must land
        # there rather than at zero or at a leaked 16-bit destination address.
        p.op('LDA', 'imm', post_write); p.op('STA', 'abs', 0x2004)
        p.record('post_dma_write_preserves_flags')
    if mutate_source:
        # The copied buffer must not alias subsequent writes to its source.
        p.op('LDA', 'imm', 0x5c); p.op('STA', 'abs', ((page & 7) << 8) + 17)
    if stream_offsets:
        p.op('LDA', 'imm', 1); p.op('STA', 'zp', 0x7d)
    p.op('LDA', 'imm', 0x5a); p.op('STA', 'zp', 0x7e)
    if stream_offsets:
        # A host acknowledgement only advances this procedural test fixture.
        # It is not used by the game or by distributed interactive ROMs.
        p.label('host_wait'); p.op('LDA', 'zp', 0x7d); p.op('BNE', 'rel', 'host_wait')
        p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7e)
        p.op('INC', 'zp', 0x7c); p.op('BEQ', 'rel', 'offsets_finished')
        p.op('JMP', 'abs', 'offset_iteration')
        p.label('offsets_finished'); p.op('LDA', 'imm', 0xa5); p.op('STA', 'zp', 0x7e)
    p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta.update(oam_copy_fixture=True, page=page, seed=seed, c0=c0,
                writer=writer, oam_address=oam_address, post_write=post_write,
                mutate_source=mutate_source, neutral_latch=neutral_latch, stream_offsets=stream_offsets)
    (out / 'trace-summary.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--page', type=lambda x: int(x, 0), default=2)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--c0', action='store_true')
    ap.add_argument('--writer', choices=('STA', 'STX', 'STY'), default='STA')
    ap.add_argument('--oam-address', type=lambda x: int(x, 0), default=0)
    ap.add_argument('--post-write', type=lambda x: int(x, 0))
    ap.add_argument('--mutate-source', action='store_true')
    ap.add_argument('--neutral-latch', action='store_true')
    a = ap.parse_args()
    print(json.dumps(create(a.out, a.page, a.seed, a.c0, a.writer, a.oam_address, a.post_write, a.mutate_source, a.neutral_latch), indent=2))
