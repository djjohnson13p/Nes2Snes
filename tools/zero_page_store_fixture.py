#!/usr/bin/env python3
"""Original STY indexed-zero-page cases, with explicit flags and wraparound."""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
from native_fixture import Program, write_program


def create(out: Path, seed: int = 0, c0: bool = False) -> dict:
    rng = random.Random(seed)
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7e)
    for addr, value in ((0x5100, 2), (0x5115, 0x9e if c0 else 0x80),
                        (0x5116, 0x87 if c0 else 0x9e)):
        p.op('LDA', 'imm', value); p.op('STA', 'abs', addr)
    for i in range(128):
        base = (0, 1, 0x7f, 0x80, 0xfe, 0xff, rng.randrange(256), 0xf0)[i % 8]
        x = (0, 1, 0x7f, 0x80, 0xfe, 0xff, rng.randrange(256), 0x20)[(i // 8) % 8]
        y = (0, 0x80, 0xff, 0x7f, rng.randrange(256))[i % 5]
        if (base + x) & 255 == 0x7e and y == 0x5a:
            y ^= 1  # Only the final instruction may signal completion.
        p.op('LDA', 'imm', 0x7f); p.op('CLC'); p.op('ADC', 'imm', 1 if i & 1 else 0)
        p.op('LDX', 'imm', x); p.op('LDY', 'imm', y)
        p.op('LDA', 'imm', (0, 0x80, 0xff, rng.randrange(256))[i % 4])
        p.op('SEC' if i & 2 else 'CLC')
        p.op('STY', 'zpx', base)
        p.record(f'sty_{i:03d}_base{base:02x}_x{x:02x}_flags')
        p.op('LDA', 'zp', (base + x) & 255)
        p.record(f'sty_{i:03d}_memory')
    p.op('LDA', 'imm', 0x5a); p.op('STA', 'zp', 0x7e)
    p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta.update(zero_page_store_fixture=True, seed=seed, c0=c0, store_cases=128)
    (out / 'trace-summary.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--c0', action='store_true')
    args = ap.parse_args()
    print(json.dumps(create(args.out, args.seed, args.c0), indent=2))
