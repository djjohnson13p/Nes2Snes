#!/usr/bin/env python3
"""Original indexed-indirect LDA boundary/flag regression input."""
from __future__ import annotations
import argparse,json,random
from pathlib import Path
from native_fixture import Program,write_program

def create(out:Path,seed:int=0)->dict:
    rng=random.Random(seed);p=Program()
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('STA','zp',0x7e)
    p.op('LDA','imm',2);p.op('STA','abs',0x5100)
    p.op('LDA','imm',0x80);p.op('STA','abs',0x5115)
    p.op('LDA','imm',0x9e);p.op('STA','abs',0x5116)
    targets=(0x0002,0x07fe,0x0800,0x0fff,0x1f01,0x1fff,0x8000,0xc000,0xff00,0xffff)
    for i in range(80):
        pointer=(0,0x20,0xfe,0xff)[i%4]
        target=targets[i%len(targets)]
        index=(0,1,127,255)[(i//4)%4]
        base=(target-index)&65535
        if target<0x2000:
            p.op('LDA','imm',(0,0x80,0xff,rng.randrange(256))[i%4])
            p.op('STA','abs',target&0x7ff)
        p.op('LDA','imm',base&255);p.op('STA','zp',pointer)
        p.op('LDA','imm',base>>8);p.op('STA','zp',(pointer+1)&255)
        p.op('LDA','imm',0x7f);p.op('CLC');p.op('ADC','imm',i&1)
        p.op('LDA','imm',rng.randrange(256));p.op('LDX','imm',rng.randrange(256));p.op('LDY','imm',index)
        p.op('SEC' if i&2 else 'CLC')
        p.op('LDA','iy',pointer)
        p.record(f'lda_iy_{i}_ptr{pointer:02x}_base{base:04x}_index{index}')
    p.op('LDA','imm',1);p.op('STA','abs',0x4016)
    p.op('LDA','imm',0);p.op('STA','abs',0x4016)
    p.op('LDA','imm',0x16);p.op('STA','zp',0x20)
    p.op('LDA','imm',0x40);p.op('STA','zp',0x21);p.op('LDY','imm',0)
    for i in range(10):
        p.op('LDA','iy',0x20);p.record(f'joypad_fallback_{i}')
    p.op('LDA','imm',0x5a);p.op('STA','zp',0x7e)
    p.label('done');p.op('JMP','abs','done');p.label('nmi');p.op('RTI')
    m=write_program(out,p);m.update(indirect_load_fixture=True,seed=seed)
    (out/'trace-summary.json').write_text(json.dumps(m,indent=2)+'\n');return m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=0)
    a=p.parse_args();m=create(a.out,a.seed);print(f"Created {len(m['records'])} records")
