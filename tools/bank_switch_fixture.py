#!/usr/bin/env python3
"""Original mapper-return/stack fixture; no commercial game bytes.

Exercises STA/STX/STY with arbitrary preserved flags, raw reads after live bank
changes, stack depth, switchable-code continuation, and the C0 fallback. The
optional build-time delay forces host NMIs after CODEBANK has changed but before
the WRAM veneer returns. That delay is not part of the NES fixture itself.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from native_fixture import Program, write_program


def create(out: Path, seed: int = 0, enable_nmi: bool = False) -> dict:
    if not 0 <= seed <= 255:
        raise ValueError('seed must be an unsigned byte')
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7e); p.op('STA', 'zp', 0x7d)
    p.op('STA', 'abs', 0x2000); p.op('STA', 'abs', 0x2001)
    p.op('LDA', 'imm', 2); p.op('STA', 'abs', 0x5100)
    if enable_nmi:
        p.op('LDA', 'imm', 0x80); p.op('STA', 'abs', 0x2000)
    for cb in (30, 7):
        p.op('LDA', 'imm', cb | 0x80); p.op('STA', 'abs', 0x5116)
        for primary in range(16):
            for n, operation in enumerate(('STA', 'STX', 'STY')):
                value = 0x80 + primary * 2
                depth = (seed + primary + n) % 9
                for _ in range(depth):
                    p.op('LDA', 'imm', 0x6a); p.op('PHA')
                a, x, y = (value if operation == 'STA' else (seed+0x23)&255,
                           value if operation == 'STX' else (seed+0x55)&255,
                           value if operation == 'STY' else (seed+0x79)&255)
                p.op('LDA', 'imm', a); p.op('LDX', 'imm', x); p.op('LDY', 'imm', y)
                p.op('SEC' if (primary+n+seed)&1 else 'CLC')
                p.op('BIT', 'abs', 'flagbyte')
                p.op(operation, 'abs', 0x5115)
                p.record(f'{operation}_primary{primary}_c{cb}_depth{depth}')
                for _ in range(depth):
                    p.op('PLA')
                p.op('TSX'); p.op('LDA', 'abs', 0x8000)
                p.record(f'raw_bank_and_stack_primary{primary}_c{cb}_{operation}')
    # Fixed-selector stores preserve the selected mapping and stack.
    for operation in ('STA', 'STX', 'STY'):
        p.op('LDA', 'imm', 0x9f); p.op('LDX', 'imm', 0x9f); p.op('LDY', 'imm', 0x9f)
        p.op(operation, 'abs', 0x5117)
        p.record(f'{operation}_fixed_5117')
    p.op('LDA', 'imm', 0x80); p.op('STA', 'abs', 0x5115)
    first = Program(0x8100)
    first.op('LDX', 'imm', 0x82); first.op('STX', 'abs', 0x5115)
    second = Program(0x8105)
    second.op('LDA', 'imm', 0x51); second.op('RTS')
    p.op('JSR', 'abs', 0x8100); p.record('STX_switches_executing_primary')
    p.op('LDA', 'imm', 0x9e); p.op('STA', 'abs', 0x5116)
    cfirst = Program(0xc100)
    cfirst.op('LDY', 'imm', 0x87); cfirst.op('STY', 'abs', 0x5116)
    csecond = Program(0xc105)
    csecond.op('LDA', 'imm', 0x69); csecond.op('RTS')
    p.op('JSR', 'abs', 0xc100); p.record('STY_switches_executing_c000')
    p.op('LDA', 'imm', 0); p.op('STA', 'abs', 0x2000)
    p.op('LDA', 'imm', 0x5a); p.op('STA', 'zp', 0x7e)
    p.label('done'); p.op('JMP', 'abs', 'done')
    p.label('nmi'); p.op('INC', 'zp', 0x7d); p.op('RTI')
    p.label('flagbyte'); p.data.append(0xc0 if seed&1 else 0x40)
    meta = write_program(out, p, {0x100:first, 0x4105:second, 0x3c100:cfirst, 0xe105:csecond})
    meta.update(bank_switch_fixture=True, seed=seed, nmi_enabled=enable_nmi)
    (out/'trace-summary.json').write_text(json.dumps(meta, indent=2)+'\n')
    return meta


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--enable-nmi', action='store_true')
    a=p.parse_args(); m=create(a.out,a.seed,a.enable_nmi)
    print(f"Created {len(m['records'])} records, {m['program_bytes']} program bytes")
