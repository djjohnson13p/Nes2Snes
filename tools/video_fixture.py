#!/usr/bin/env python3
"""Original procedural animated OAM fixture; no commercial game content.

Changes coordinates, tiles, flips, priority, visibility and sprite-size/pattern
selection, with repeated frames in between to exercise the object cache.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from native_fixture import Program,write_program

def create(out:Path)->dict:
    p=Program()
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('LDX','imm',0);p.label('clear')
    for address in range(0,0x800,256):p.op('STA','absx',address)
    p.op('INX');p.op('BNE','rel','clear')
    for address,value in ((0x5100,2),(0x5115,0x80),(0x5116,0x9e),(0x5101,3),(0x5105,0x44),(0x2001,0x1e),(0x2000,0x80)):
        p.op('LDA','imm',value);p.op('STA','abs',address)
    p.label('main');p.op('JMP','abs','main')
    p.label('nmi')
    p.op('PHA');p.op('TXA');p.op('PHA');p.op('TYA');p.op('PHA')
    p.op('INC','zp',0x70)
    p.op('LDA','zp',0x70);p.op('AND','imm',3);p.op('BNE','rel','same_objects')
    p.op('LDX','imm',0);p.label('objects')
    p.op('TXA');p.op('CLC');p.op('ADC','zp',0x70);p.op('STA','absx',0x0200)
    p.op('TXA');p.op('EOR','zp',0x70);p.op('STA','absx',0x0201)
    p.op('TXA');p.op('EOR','zp',0x70);p.op('AND','imm',0xe3);p.op('STA','absx',0x0202)
    p.op('TXA');p.op('EOR','imm',0xa0);p.op('STA','absx',0x0203)
    for _ in range(4):p.op('INX')
    p.op('BNE','rel','objects')
    p.label('same_objects')
    # Independently change size/pattern bits while raw OAM can remain unchanged.
    p.op('LDA','zp',0x70);p.op('AND','imm',0x28);p.op('ORA','imm',0x80);p.op('STA','abs',0x2000)
    p.op('LDA','imm',2);p.op('STA','abs',0x4014)
    p.op('PLA');p.op('TAY');p.op('PLA');p.op('TAX');p.op('PLA');p.op('RTI')
    meta=write_program(out,p);meta['animated_oam_fixture']=True
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    create(p.parse_args().out)
