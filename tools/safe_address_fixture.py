#!/usr/bin/env python3
"""Original boundary-address fixture; no commercial code or data is included."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from native_fixture import Program, write_program
from opcodes6502 import OPS


def create(out: Path) -> dict:
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('LDX', 'imm', 0); p.label('clear')
    for page in range(0, 0x800, 0x100): p.op('STA', 'absx', page)
    p.op('INX'); p.op('BNE', 'rel', 'clear')
    p.op('STA', 'abs', 0x2000); p.op('STA', 'abs', 0x2001)
    writes = {'STA', 'STX', 'STY', 'ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC'}
    for opcode, (name, mode, size) in sorted(OPS.items()):
        if mode not in ('zpx', 'zpy'): continue
        for case, index in enumerate((0, 1, 254, 255)):
            value = (0x81 + case * 41) & 255
            p.op('LDA', 'imm', value); p.op('STA', 'zp', index)
            p.op('LDA', 'imm', 0x7f); p.op('CLC'); p.op('ADC', 'imm', case & 1)
            p.op('LDA', 'imm', 0x69)
            p.op('LDX', 'imm', index if mode == 'zpx' else 0x39)
            p.op('LDY', 'imm', index if mode == 'zpy' else 0x52)
            p.op('SEC' if case & 2 else 'CLC')
            p.op(name, mode, 0)
            p.record(f'zero_base_{name}_{mode}_index{index}')
            if name in writes:
                p.op('LDA', 'zp', index)
                p.record(f'zero_base_{name}_{mode}_index{index}_memory')
    for address in (0x800, 0xa00, 0xfff, 0x1000, 0x17ff, 0x1fff):
        p.op('LDA', 'imm', 0xa9); p.op('STA', 'abs', address & 0x7ff)
        p.op('LDA', 'abs', address); p.record(f'mirror_{address:04x}')
    for mode in ('absx', 'absy'):
        p.op('LDA', 'imm', 0x92); p.op('STA', 'abs', 0x7ff)
        p.op('LDX', 'imm', 255); p.op('LDY', 'imm', 255)
        p.op('LDA', mode, 0x1f00); p.record(f'upper_ram_boundary_{mode}')
    p.op('LDA', 'imm', 0x5a); p.op('STA', 'zp', 0x7e)
    p.label('done'); p.op('JMP', 'abs', 'done')
    p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta['safe_address_fixture'] = True
    (out / 'trace-summary.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    result = create(parser.parse_args().out)
    print(f"Created {len(result['records'])} zero-base and RAM-mirror records.")
