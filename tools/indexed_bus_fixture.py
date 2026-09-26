#!/usr/bin/env python3
"""Procedural NMOS dummy-read side effects through NES PPU data/status ports.

Independent emulator comparison is essential: RAM-only CPU tests cannot detect
an omitted read that advances PPU VRAM or clears the PPU address-write toggle.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from native_fixture import Program, write_program


def create(out: Path) -> dict:
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7E)
    for label in ('warm1', 'warm2'):
        p.label(label); p.op('LDA', 'abs', 0x2002); p.op('BPL', 'rel', label)
    def store(a: int, v: int) -> None:
        p.op('LDA', 'imm', v); p.op('STA', 'abs', a)
    for a, v in ((0x5100, 2), (0x5115, 0x80), (0x5116, 0x9E), (0x5105, 0x44),
                 (0x2000, 0), (0x2001, 0), (0x4017, 0x40)):
        store(a, v)
    def address(a: int) -> None:
        p.op('LDA', 'abs', 0x2002)
        store(0x2006, a >> 8); store(0x2006, a & 255)
    def seed() -> None:
        address(0x2200)
        for v in (0x11, 0x82, 0x43, 0xE4, 0x35, 0x76, 0xA7, 0x58): store(0x2007, v)
        address(0x2200)
        p.op('LDA','abs',0x2007)  # known buffered byte from seeded location
        address(0x2200)
    def flags() -> None:
        p.op('LDA', 'imm', 0x7F); p.op('CLC'); p.op('ADC', 'imm', 1)
        p.op('LDA', 'imm', 0xC6); p.op('SEC')
    cases = [(op, mode, cross) for op in ('LDA','AND','ORA','EOR','ADC','SBC','CMP')
             for mode, cross in (('absx', True), ('absy', True), ('iy', True))]
    cases += [('LDX', 'absy', True), ('LDY', 'absx', True)]
    cases += [('STA', mode, cross) for mode in ('absx','absy','iy') for cross in (False, True)]
    cases += [(op, 'absx', False) for op in ('ASL','LSR','ROL','ROR','INC','DEC')]
    for i, (op, mode, cross) in enumerate(cases):
        seed()
        base = 0x20FF if cross else 0x2000
        index = 8 if cross else 7
        if mode == 'iy':
            store(0x20, base & 255); store(0x21, base >> 8)
        p.op('LDX', 'imm', index); p.op('LDY', 'imm', index)
        flags()
        p.op(op, mode, 0x20 if mode == 'iy' else base)
        p.record(f'{i}_{op}_{mode}_cross{int(cross)}_flags')
        p.op('LDA', 'abs', 0x2007)
        p.record(f'{i}_next_buffered_byte')
        if op in ('STA','ASL','LSR','ROL','ROR','INC','DEC'):
            address(0x2200); p.op('LDA', 'abs', 0x2007)
            for j in range(5):
                p.op('LDA', 'abs', 0x2007); p.record(f'{i}_vram_{j}')
    # A dummy read of $2002 must clear a previously half-written address.
    address(0x2200); store(0x2007, 0x69)
    p.op('LDA', 'abs', 0x2002); store(0x2006, 0x27)
    p.op('LDA', 'imm', 0); p.op('LDX', 'imm', 0)
    p.op('STA', 'absx', 0x2002)
    store(0x2006, 0x22); store(0x2006, 0)
    p.op('LDA', 'abs', 0x2007); p.op('LDA', 'abs', 0x2007)
    p.record('status_dummy_resets_toggle')
    p.op('LDA', 'imm', 0x5A); p.op('STA', 'zp', 0x7E)
    p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    result = write_program(out, p)
    result['indexed_bus_fixture'] = True
    (out/'trace-summary.json').write_text(json.dumps(result, indent=2)+'\n')
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();m=create(a.out)
    print(f"Created {len(m['records'])} records in {m['program_bytes']} bytes")
