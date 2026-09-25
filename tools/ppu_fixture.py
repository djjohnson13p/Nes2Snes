#!/usr/bin/env python3
"""Original buffered-PPU/alias/palette CPU fixture for an independent NES oracle.

Rendering and NMI are disabled so this tests register semantics, not raster
cycle equivalence. It contains no original-game data.
"""
from __future__ import annotations
import argparse,json,random
from pathlib import Path
from native_fixture import Program,write_program

def create(out:Path,seed:int=0)->dict:
    rng=random.Random(seed);p=Program()
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('LDX','imm',0);p.label('clear')
    for address in range(0,0x800,256):p.op('STA','absx',address)
    p.op('INX');p.op('BNE','rel','clear')
    # NES power-on ignores some PPU writes until after two vblanks.
    for label in ('warmup1','warmup2'):
        p.label(label);p.op('LDA','abs',0x2002);p.op('BPL','rel',label)
    for address,value in ((0x5100,2),(0x5115,0x80),(0x5116,0x9e),(0x5105,0x44),(0x2000,0),(0x2001,0)):
        p.op('LDA','imm',value);p.op('STA','abs',address)
    def address(value:int,alias:int=0):
        p.op('LDA','imm',value>>8);p.op('STA','abs',0x2006+alias)
        p.op('LDA','imm',value&255);p.op('STA','abs',0x2006+alias)
    for i in range(12):
        alias=(i%4)*8;target=0x2000+((i*73)&0x3ff)+(0x400 if i&1 else 0)
        value=rng.randrange(256)
        p.op('LDA','imm',0);p.op('STA','abs',0x2000+alias)
        address(target,alias)
        p.op('LDX','imm',rng.randrange(256));p.op('LDY','imm',rng.randrange(256))
        p.op('LDA','imm',0x7f);p.op('CLC');p.op('ADC','imm',1)
        p.op('LDA','imm',value);p.op('SEC' if i&1 else 'CLC')
        p.op('STA','abs',0x2007+alias);p.record(f'ppu_store_flags_{i}')
        address(target,alias)
        p.op('LDA','abs',0x2007+alias) # buffered dummy read
        p.op('LDA','abs',0x2007+alias);p.record(f'nametable_readback_{i}')
    # +32 increment and attribute bytes.
    p.op('LDA','imm',4);p.op('STA','abs',0x2000)
    address(0x2380)
    for i in range(4):
        p.op('LDA','imm',0x30+i);p.op('STA','abs',0x2007)
    for i in range(4):
        address(0x2380+32*i)
        p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.record(f'increment32_{i}')
    # Immediate palette reads and universal-background aliasing.
    p.op('LDA','imm',0);p.op('STA','abs',0x2000)
    for i in range(16):
        address(0x3f00+i);p.op('LDA','imm',(i*3+seed)&0x3f);p.op('STA','abs',0x2007)
    for i in range(16):
        address(0x3f10+i if i%4==0 else 0x3f00+i)
        p.op('LDA','abs',0x2007);p.op('AND','imm',0x3f);p.record(f'palette_alias_{i}')
    # A status read must reset the address/scroll latch. Low status bits come
    # from the I/O latch, independently of vblank timing.
    p.op('LDA','imm',0x1b);p.op('STA','abs',0x2005)
    p.op('LDA','abs',0x2002);p.op('AND','imm',0x1f);p.record('status_open_bus')
    address(0x2000);p.op('LDA','imm',0x69);p.op('STA','abs',0x2007)
    address(0x2000);p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.record('status_latch_reset')
    # Port 2 is the bridge's intentionally disconnected second controller.
    p.op('SEC');p.op('LDA','abs',0x4017);p.op('AND','imm',0x41);p.record('second_controller')
    p.op('LDA','imm',0x5a);p.op('STA','zp',0x7e)
    p.label('done');p.op('JMP','abs','done');p.label('nmi');p.op('RTI')
    meta=write_program(out,p);meta['ppu_fixture_seed']=seed
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=0)
    a=p.parse_args();print(json.dumps(create(a.out,a.seed),indent=2))
