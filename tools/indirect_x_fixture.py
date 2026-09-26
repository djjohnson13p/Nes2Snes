#!/usr/bin/env python3
"""Procedural NMOS (zero-page,X) read tests; no commercial input is used."""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
from native_fixture import Program, write_program

READS = ('LDA', 'CMP', 'ADC', 'SBC', 'AND', 'ORA', 'EOR')
INDEXES = (0, 1, 2, 127, 128, 254, 255)
TARGETS = (0x0200, 0x027F, 0x07F0, 0x0A00, 0x12FF, 0x17F0,
           0x1A01, 0x8000, 0xA000, 0xC000, 0xFFFF)

def pointer(p: Program, address: int, index: int, target: int) -> int:
    """Store both pointer bytes in zero page and return the instruction operand."""
    for a, value in ((address, target & 255), ((address + 1) & 255, target >> 8)):
        p.op('LDA', 'imm', value)
        p.op('STA', 'zp', a)
    p.op('LDX', 'imm', index)
    return (address - index) & 255

def create(out: Path, block: int = 0, seed: int = 0,
           sweep_indexes: bool = False, in_nmi: bool = False) -> dict:
    if not 0 <= block < 16:
        raise ValueError('block must be in 0..15')
    rng = random.Random(seed)
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7E)
    p.op('STA', 'abs', 0x02F0)
    p.op('STA', 'abs', 0x2000); p.op('STA', 'abs', 0x2001)
    # Explicit CIRAM mapping: mapper power-on state is not a fixture oracle.
    p.op('STA', 'abs', 0x5104); p.op('STA', 'abs', 0x5105)
    p.op('LDA', 'imm', 2); p.label('raw_instruction'); p.op('STA', 'abs', 0x5100)
    p.op('LDA', 'imm', 0x80); p.op('STA', 'abs', 0x5115)
    p.op('LDA', 'imm', 0x9E); p.op('STA', 'abs', 0x5116)
    # Allow the NES's startup PPU-write suppression to expire before I/O tests.
    p.op('LDX', 'imm', 2); p.label('warmup')
    p.op('BIT', 'abs', 0x2002); p.op('BPL', 'rel', 'warmup')
    p.op('DEX'); p.op('BNE', 'rel', 'warmup')
    p.op('LDA', 'imm', 0x5B); p.op('STA', 'abs', 0x0100)
    if in_nmi:
        p.op('LDA', 'imm', 0x80); p.op('STA', 'abs', 0x2000)
        p.label('await_nmi'); p.op('LDA', 'abs', 0x02F0)
        p.op('BEQ', 'rel', 'await_nmi')
        p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x2000)
        p.op('LDA', 'imm', 0x5A); p.op('STA', 'zp', 0x7E)
        p.label('done'); p.op('JMP', 'abs', 'done')
        p.label('nmi'); p.op('LDA', 'abs', 0x02F0)
        p.op('BEQ', 'rel', 'run_tests'); p.op('RTI'); p.label('run_tests')
    coverage = []
    targets = TARGETS + (p.labels['raw_instruction'],)
    for i in range(16):
        for op_i, operation in enumerate(READS):
            number = block * 16 + i
            ptr = (0, 0xFE, 0xFF)[op_i % 3] if sweep_indexes else number
            index = number if sweep_indexes else INDEXES[(i + op_i) % len(INDEXES)]
            target = targets[(i + op_i + seed) % len(targets)]
            # Walk all 32 supported mapper combinations across the matrix.
            primary = (i + block + op_i) % 16
            cbank = 7 if (block + op_i) & 1 else 30
            p.op('LDA', 'imm', 0x80 | (primary * 2)); p.op('STA', 'abs', 0x5115)
            p.op('LDA', 'imm', 0x80 | cbank); p.op('STA', 'abs', 0x5116)
            if target < 0x2000:
                p.op('LDA', 'imm', (0, 127, 128, 255, rng.randrange(256))[(i+op_i) % 5])
                p.op('STA', 'abs', target & 0x7FF)
            operand = pointer(p, ptr, index, target)
            p.op('LDA', 'imm', 127); p.op('CLC'); p.op('ADC', 'imm', (i+op_i) & 1)
            p.op('LDA', 'imm', (0, 127, 128, 255, rng.randrange(256))[(i+2*op_i) % 5])
            p.op('LDY', 'imm', rng.randrange(256)); p.op('SEC' if (i+op_i) & 2 else 'CLC')
            p.op(operation, 'ix', operand)
            p.record(f'{operation}_ptr{ptr:02x}_x{index:02x}_target{target:04x}')
            coverage.append(dict(operation=operation, pointer=ptr, index=index,
                                 target=target, primary_bank=primary, c_bank=cbank))
    # Hardware addresses must NOT take the raw-memory reader. Serial shifts
    # are externally observable even though this fixture supplies no buttons.
    p.op('LDA', 'imm', 1); p.op('STA', 'abs', 0x4016)
    p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x4016)
    operand = pointer(p, 0xFF, 255, 0x4016)
    for i in range(12):
        p.op('LDA', 'ix', operand); p.record(f'joypad_side_effect_{i}')
    # Seed the buffered port explicitly; never compare uninitialized VRAM.
    p.op('LDA', 'abs', 0x2002)
    p.op('LDA', 'imm', 0x20); p.op('STA', 'abs', 0x2006)
    p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x2006)
    for i in range(24):
        p.op('LDA', 'imm', (i*17+seed) & 255); p.op('STA', 'abs', 0x2007)
    p.op('LDA', 'imm', 0x20); p.op('STA', 'abs', 0x2006)
    p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x2006)
    p.op('LDA', 'abs', 0x2007)
    operand = pointer(p, 0xFE, 128, 0x2007)
    for i in range(12):
        p.op('LDA', 'ix', operand); p.record(f'buffered_ppu_side_effect_{i}')
    if in_nmi:
        p.op('LDA', 'imm', 1); p.op('STA', 'abs', 0x02F0); p.op('RTI')
    else:
        p.op('LDA', 'imm', 0x5A); p.op('STA', 'zp', 0x7E)
        p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta.update(indirect_x_fixture=True, block=block, seed=seed,
                sweep_indexes=sweep_indexes, in_nmi=in_nmi,
                expected_fast_reads=len(coverage), expected_io_reads=24, coverage=coverage)
    (out/'trace-summary.json').write_text(json.dumps(meta, indent=2)+'\n')
    return meta

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--block', type=int, default=0)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--sweep-indexes', action='store_true')
    parser.add_argument('--in-nmi', action='store_true')
    args = parser.parse_args()
    meta = create(args.out, args.block, args.seed, args.sweep_indexes, args.in_nmi)
    print(f"Created {len(meta['records'])} records in {meta['program_bytes']} bytes")
