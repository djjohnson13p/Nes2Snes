#!/usr/bin/env python3
"""Procedural regression cases for native COP fast paths, with no game data.

Seeded RAM/flag tests include 8-bit index and zero-page pointer wrapping, native
ROM reads, hardware fallback, and mapper writes from switchable code itself.
"""
from pathlib import Path
import argparse
import json
import random
from native_fixture import Program, write_program
from build_native import QUICK_ZPX


def create(out: Path, seed: int=0, cases: int=60) -> dict:
    if not 1<=cases<=90:raise ValueError('cases must be between 1 and 90')
    rng=random.Random(seed)
    p=Program()
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('LDX','imm',0);p.label('clear')
    for a in range(0,0x800,0x100):p.op('STA','absx',a)
    p.op('INX');p.op('BNE','rel','clear')
    for address,value in ((0x5100,2),(0x5115,0x80),(0x5116,0x9e)):
        p.op('LDA','imm',value);p.op('STA','abs',address)
    operations=sorted(QUICK_ZPX)
    for i in range(cases):
        name=operations[i%len(operations)]
        a,value,x,y,operand=[rng.randrange(256) for _ in range(5)]
        carry=rng.randrange(2);overflow=rng.randrange(2)
        target=(operand+x)&255
        # $7E is the completion marker; don't accidentally complete early.
        if target==0x7e:operand=(operand+1)&255;target=(operand+x)&255
        p.op('LDA','imm',value);p.op('STA','zp',target)
        # Known initial V/C, independently varied from A and RAM contents.
        p.op('LDA','imm',0x7f);p.op('CLC');p.op('ADC','imm',1 if overflow else 0)
        p.op('LDA','imm',a);p.op('LDX','imm',x);p.op('LDY','imm',y)
        p.op('SEC' if carry else 'CLC')
        p.op(name,'zpx',operand)
        p.record(f'{seed}_{i}_{name}_a{a}_x{x}_y{y}_base{operand}_v{value}_c{carry}_V{overflow}')
        if name in ('STA','ASL','LSR','ROL','ROR','INC','DEC'):
            p.op('LDA','zp',target);p.record(f'{seed}_{i}_stored_value')
    for i,(pointer,base,index) in enumerate(((0xff,0x00fe,2),(0xff,0xffff,2),
                                          (0x20,0x1ffe,2),(0x20,0x7fff,1),
                                          (0x20,0x89ff,255),(0xff,0xc000,0))):
        p.op('LDA','imm',0x6d);p.op('STA','zp',1)
        p.op('LDA','imm',base&255);p.op('STA','zp',pointer)
        p.op('LDA','imm',base>>8);p.op('STA','zp',(pointer+1)&255)
        p.op('LDY','imm',index);p.op('LDA','iy',pointer)
        p.record(f'indirect_wrapping_{i}')
    # Return must execute in the new bank, not merely read data from it.
    first=Program(0x8100);first.op('LDA','imm',0x82);first.op('STA','abs',0x5115)
    second=Program(0x8105);second.op('LDA','imm',0x5b);second.op('RTS')
    p.op('LDA','imm',0x80);p.op('STA','abs',0x5115);p.op('JSR','abs',0x8100)
    p.record('switch_primary_while_executing_it')
    cfirst=Program(0xc100);cfirst.op('LDA','imm',0x87);cfirst.op('STA','abs',0x5116)
    csecond=Program(0xc105);csecond.op('LDA','imm',0x6d);csecond.op('RTS')
    p.op('LDA','imm',0x9e);p.op('STA','abs',0x5116);p.op('JSR','abs',0xc100)
    p.record('switch_c000_while_executing_it')
    # Serial joypad reads and the indirect I/O fallback, with no buttons held.
    p.op('LDA','imm',1);p.op('STA','abs',0x4016)
    p.op('LDA','imm',0);p.op('STA','abs',0x4016)
    for i in range(10):
        p.op('SEC' if i&1 else 'CLC');p.op('LDA','abs',0x4016)
        p.record(f'joypad_serial_{i}')
    p.op('LDA','imm',0x16);p.op('STA','zp',0x20)
    p.op('LDA','imm',0x40);p.op('STA','zp',0x21)
    p.op('LDY','imm',0);p.op('LDA','iy',0x20);p.record('indirect_hardware_fallback')
    # Exercise the native WRAM block-copy path, with a predictable OAM page.
    p.op('LDX','imm',0);p.label('oam_fill')
    p.op('TXA');p.op('EOR','imm',seed&255);p.op('STA','absx',0x0200)
    p.op('INX');p.op('BNE','rel','oam_fill')
    p.op('LDA','imm',2);p.op('STA','abs',0x4014)
    p.op('LDA','imm',0x5a);p.op('STA','zp',0x7e)
    p.label('done');p.op('JMP','abs','done');p.label('nmi');p.op('RTI')
    result=write_program(out,p,{0x100:first,0x4105:second,0x3c100:cfirst,0xe105:csecond})
    result['fastpath_stress_seed']=seed
    result['expected_oam_source_page']=2
    (out/'trace-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--cases',type=int,default=60)
    a=p.parse_args();m=create(a.out,a.seed,a.cases)
    print(f"Created {len(m['records'])} regression records from seed {a.seed}.")
