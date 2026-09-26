#!/usr/bin/env python3
"""Authored serial-poll fixtures: flags, scratch bytes, alias guards and banks."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from native_fixture import Program,write_program


def create(out:Path, indices:list[int]|None=None, c0:bool=False, outside_nmi:bool=False)->dict:
    indices=list(range(8))+[127,254,255] if indices is None else indices
    if not indices or len(indices)>28 or any(type(x)!=int or not 0<=x<256 for x in indices):
        raise ValueError('Require 1..28 byte indices')
    reserved={0x60,0x70,0x7e}
    if any(x in reserved or ((x+1)&255) in reserved for x in indices):
        raise ValueError('Fixture indices overlap its clock, flags or completion state')
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('LDX','imm',0);p.label('clear')
    for a in range(0,0x800,256):p.op('STA','absx',a)
    p.op('INX');p.op('BNE','rel','clear')
    for a,v in ((0x5100,2),(0x5115,0x9e if c0 else 0x80),(0x5116,0x87 if c0 else 0x9e)):
        p.op('LDA','imm',v);p.op('STA','abs',a)
    # Respect NES power-on PPU write suppression before enabling NMI.
    for label in ('vblank1','vblank2'):
        p.label(label);p.op('BIT','abs',0x2002);p.op('BPL','rel',label)
    p.op('LDA','imm',0x80);p.op('STA','abs',0x2000)
    p.label('main')
    if outside_nmi:
        p.op('LDA','zp',0x70);p.op('CMP','imm',4);p.op('BCC','rel','main')
        p.op('JSR','abs','checks')
    p.label('idle');p.op('JMP','abs','idle')
    p.label('nmi');p.op('PHA')
    p.op('INC','zp',0x70)
    if not outside_nmi:
        p.op('LDA','zp',0x70);p.op('CMP','imm',4);p.op('BNE','rel','nmi_done')
        p.op('JSR','abs','checks')
    p.label('nmi_done');p.op('PLA');p.op('RTI')
    p.label('checks')
    for i,index in enumerate(indices):
        # X=3,4,5 aliases scratch: initialize in the same order on both systems.
        for a,v in ((index,0x35^index),((index+1)&255,0xA5^i),(4,0xF8),(5,0x23)):
            p.op('LDA','imm',v);p.op('STA','zp',a)
        p.op('LDX','imm',index);p.op('LDY','imm',0xAC)
        p.op('LDA','imm',0x40 if (i%3) else 0);p.op('STA','zp',0x60);p.op('BIT','zp',0x60)
        p.op('SEC' if i&1 else 'CLC');p.op('LDA','imm',0x91)
        p.op('JSR','abs','poll');p.record(f'x{index}_registers')
        for name,a in (('first',index),('second',(index+1)&255),('scratch4',4),('scratch5',5)):
            p.op('LDA','zp',a);p.record(f'x{index}_{name}')
        p.op('LDA','abs',0x4016);p.record(f'x{index}_serial_after_eight')
    p.op('LDA','imm',0x5A);p.op('STA','zp',0x7e);p.op('RTS')
    # Construct the independent fixture algorithm, not a copy of runtime bytes.
    p.label('poll');p.op('LDY','imm',1);p.op('STY','abs',0x4016);p.op('DEY')
    p.op('STY','abs',0x4016);p.op('LDY','imm',8);p.label('bits')
    for port,temp,dest in ((0x4016,4,0),(0x4017,5,1)):
        p.op('LDA','abs',port);p.op('STA','zp',temp);p.op('LSR','acc')
        p.op('ORA','zp',temp);p.op('LSR','acc');p.op('ROL','zpx',dest)
    p.op('DEY');p.op('BNE','rel','bits');p.op('RTS')
    meta=write_program(out,p)
    meta.update(controller_fixture=True,indices=indices,c0=c0,outside_nmi=outside_nmi,
                # Index $70 would corrupt the NMI cadence; tests omit that value.
                expected_native_calls=0 if c0 or outside_nmi else sum(x<3 for x in indices))
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--c0',action='store_true');p.add_argument('--outside-nmi',action='store_true')
    a=p.parse_args();create(a.out,c0=a.c0,outside_nmi=a.outside_nmi)
