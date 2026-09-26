#!/usr/bin/env python3
"""Original two-color MMC5 IRQ fixture for the frame-scheduled raster renderer.

No commercial bytes. The middle handler waits deliberately so its PPUADDR reload
occurs during the requested line + 1. This tests that scheduling contract, not
arbitrary cycle-timed raster code. A separate NES emulator is the pixel oracle.
"""
from __future__ import annotations
import argparse,hashlib,json,struct
from pathlib import Path
from native_fixture import Program,write_program


def create(out:Path, y:int=178, delay:int=12)->dict:
    if not 0<=y<240 or not 0<=delay<=40:raise ValueError('Require Y 0..239 and delay 0..40')
    p=Program()
    def write(a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
    def banks(start):
        for i in range(4):write(0x5128+i, start if start==127 else start+i)
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    write(0x2000,0);write(0x2001,0);write(0x5100,2);write(0x5115,0x80);write(0x5116,0x9e)
    write(0x5101,3);write(0x5104,0);write(0x5105,0x44)
    # Palette is two colors on every subpalette.
    write(0x2006,0x3f);write(0x2006,0)
    for i in range(32):write(0x2007,0x0f if i%4==0 else 0x30)
    for nt in range(2):
        write(0x2006,0x20+4*nt);write(0x2006,0)
        p.op('LDY','imm',4);p.op('LDX','imm',0);p.label('fill'+str(nt))
        p.op('TXA');p.op('EOR','imm',0x37*nt);p.op('STA','abs',0x2007)
        p.op('INX');p.op('BNE','rel','fill'+str(nt));p.op('DEY');p.op('BNE','rel','fill'+str(nt))
    # $70 is the frame count; $71 is the software IRQ phase.
    write(0x70,0);write(0x71,0);write(0x2000,0xb0);write(0x2001,0x0a)
    p.op('CLI');p.label('main');p.op('JMP','abs','main')
    def save():
        p.op('PHA');p.op('TXA');p.op('PHA');p.op('TYA');p.op('PHA')
    def restore():
        p.op('PLA');p.op('TAY');p.op('PLA');p.op('TAX');p.op('PLA');p.op('RTI')
    p.label('nmi');save();p.op('INC','zp',0x70);write(0x71,0)
    write(0x5105,0);banks(0)
    p.op('LDA','abs',0x2002);write(0x2006,0x20);write(0x2006,0)
    write(0x2005,0);write(0x2005,0);write(0x2000,0xb0)
    write(0x5203,40);write(0x5204,0x80);restore()
    p.label('irq');save();p.op('LDA','abs',0x5204);p.op('INC','zp',0x71)
    p.op('LDA','zp',0x71);p.op('CMP','imm',1);p.op('BNE','rel','phase2')
    banks(127);write(0x5105,0x55);write(0x5203,48);p.op('JMP','abs','iret')
    p.label('phase2');p.op('CMP','imm',2);p.op('BNE','rel','phase3')
    if delay:
        p.op('LDX','imm',delay);p.label('delay');p.op('DEX');p.op('BNE','rel','delay')
    p.op('LDA','abs',0x2002)
    # $2006/$2005/$2005/$2006 permits all three fine-Y bits.
    write(0x2006,0x08);write(0x2005,y);write(0x2005,0)
    write(0x2006,((y&0xf8)<<2)&255)
    # This clears t but must NOT clear the vertical position just loaded in v.
    write(0x2005,0);write(0x2005,0);write(0x2000,0xb0)
    write(0x5203,56);p.op('JMP','abs','iret')
    p.label('phase3');banks(4);write(0x5204,0)
    p.label('iret');restore()
    meta=write_program(out,p);raw=bytearray((out/'fixture.nes').read_bytes())
    struct.pack_into('<H',raw,16+0x3fffe,p.labels['irq'])
    chr=bytearray(0x20000)
    for bank in range(8):
        for t in range(64):
            for row in range(8):
                value=sum((1<<(7-x)) for x in range(8) if (3*x+5*row+7*t+11*bank)%13<6)
                chr[bank*1024+t*16+row]=value
    raw[16+0x40000:]=chr
    (out/'fixture.nes').write_bytes(raw)
    # Geometry comparisons use black/white classes, not emulator RGB equality.
    rgb=bytearray(192);rgb[0x30*3:0x30*3+3]=bytes((248,248,248))
    (out/'rgb-palette.bin').write_bytes(rgb)
    meta.update(rom_sha256=hashlib.sha256(raw).hexdigest(),raster_fixture=True,
                y_reload=y,requested_irqs=[40,48,56],reload_delay_iterations=delay,
                scope='IRQ address latch and 240-line geometry; deliberate timing contract, no cycle-accuracy proof')
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--y',type=int,default=178);p.add_argument('--delay',type=int,default=12)
    a=p.parse_args();print(json.dumps(create(a.out,a.y,a.delay),indent=2))
