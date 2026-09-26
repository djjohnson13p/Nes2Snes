#!/usr/bin/env python3
"""Authored idle-state fixture; no commercial program bytes are used.

A free-running loop changes a byte and counts iterations. NMI independently
records that counter and byte. A matching update number does not constrain the
number of idle iterations. This intentionally does not demand NES/SNES RNG parity.
"""
from pathlib import Path
import argparse
import json
from native_fixture import Program, write_program


def create(out: Path) -> dict:
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0)
    for a in (0x2000,0x2001):p.op('STA','abs',a)
    for a in (0x40,0x41,0x42,0x43,0x44,0x50,0x7e):p.op('STA','zp',a)
    p.op('LDX','imm',2);p.label('wait');p.op('BIT','abs',0x2002)
    p.op('BPL','rel','wait');p.op('DEX');p.op('BNE','rel','wait')
    p.op('LDA','imm',0x80);p.op('STA','abs',0x2000);p.op('CLI')
    p.label('tick');p.op('INC','zp',0x42);p.op('BNE','rel','advance');p.op('INC','zp',0x43);p.op('BNE','rel','advance');p.op('INC','zp',0x44)
    p.label('advance');p.op('LDA','zp',0x40);p.op('CLC');p.op('ADC','imm',37);p.op('STA','zp',0x40)
    p.op('JMP','abs','tick')
    p.label('nmi');p.op('PHA');p.op('TXA');p.op('PHA');p.op('TYA');p.op('PHA')
    p.op('LDY','zp',0x50);p.op('BNE','rel','restore');p.op('INC','zp',0x50)
    p.op('LDX','zp',0x41)
    p.label('sample');p.op('LDA','zp',0x40);p.op('STA','absx',0x600)
    p.op('LDA','zp',0x42);p.op('STA','absx',0x620)
    p.op('LDA','zp',0x43);p.op('STA','absx',0x640)
    p.op('LDA','zp',0x44);p.op('STA','absx',0x660)
    p.op('INC','zp',0x41);p.op('LDA','zp',0x41);p.op('CMP','imm',32);p.op('BNE','rel','finish')
    p.op('LDA','imm',0);p.op('STA','abs',0x2000)
    p.op('LDA','imm',0x5a);p.op('STA','zp',0x7e)
    p.label('finish');p.op('DEC','zp',0x50)
    p.label('restore');p.op('PLA');p.op('TAY');p.op('PLA');p.op('TAX');p.op('PLA');p.op('RTI')
    meta=write_program(out,p)
    meta.update(tick_pc=p.labels['tick'],sample_pc=p.labels['sample'],
                addresses=[0x40,0x41,0x42,0x43,0x44],samples=32,
                scope='Independent authored NMI log calibrates a read-only idle observer; not cross-platform idle timing equivalence.')
    (out/'idle-fixture.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    print(json.dumps(create(p.parse_args().out),indent=2))
