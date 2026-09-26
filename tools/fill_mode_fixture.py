#!/usr/bin/env python3
"""Authored fill-mode tile/color change fixture, with no mapper routing change."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from native_fixture import Program, write_program

def create(out: Path, tile: int = 117, color: int = 1, start_tile: int = 3,
           start_color: int = 0) -> dict:
    if any(type(v) is not int or not 0 <= v <= 255 for v in (tile,color,start_tile,start_color)):
        raise ValueError('Fill values must be bytes')
    p=Program()
    def write(address, value):
        p.op('LDA','imm',value);p.op('STA','abs',address)
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    write(0x2000,0);write(0x2001,0)
    write(0x5100,2);write(0x5115,0x80);write(0x5116,0x9e)
    write(0x5101,3);write(0x5104,0);write(0x5105,0)
    write(0x5204,0);write(0x70,0)
    p.op('LDX','imm',2);p.label('warmup')
    p.op('BIT','abs',0x2002);p.op('BPL','rel','warmup')
    p.op('DEX');p.op('BNE','rel','warmup')
    for bank in range(8):write(0x5120+bank,bank)
    write(0x2006,0x3f);write(0x2006,0)
    for palette in range(4):
        for index in range(4):
            white=index!=0 and (palette==3 or index==palette+1)
            write(0x2007,0x30 if white else 0x0f)
    write(0x5106,start_tile);write(0x5107,start_color);write(0x5105,0xff)
    write(0x2005,0);write(0x2005,0);write(0x2000,0x80);write(0x2001,0x0a)
    p.label('main');p.op('JMP','abs','main')
    p.label('nmi');p.op('PHA');p.op('INC','zp',0x70)
    p.op('LDA','zp',0x70);p.op('CMP','imm',32);p.op('BNE','rel','done')
    write(0x5106,tile);write(0x5107,color)
    p.label('done');p.op('PLA');p.op('RTI')
    meta=write_program(out,p)
    raw=bytearray((out/'fixture.nes').read_bytes())
    graphics=bytearray(0x20000)
    for t in range(8192):
        for y in range(8):
            codes=[((x*3 + y*5 + t*7 + (t >> 3)) ^ (x*y+t)) & 3 for x in range(8)]
            graphics[t*16+y]=sum(((c & 1)<<(7-x)) for x,c in enumerate(codes))
            graphics[t*16+y+8]=sum((((c>>1)&1)<<(7-x)) for x,c in enumerate(codes))
    raw[16+0x40000:]=graphics
    (out/'fixture.nes').write_bytes(raw)
    rgb=bytearray(192);rgb[0x30*3:0x30*3+3]=b'\xf8'*3
    (out/'rgb-palette.bin').write_bytes(rgb)
    meta.update(rom_sha256=hashlib.sha256(raw).hexdigest(),fill_mode_fixture=True,
                start_tile=start_tile,start_color=start_color,tile=tile,color=color,
                change_at_nmi=32,scope='Steady fill-mode pixel classes after a tile/color change with fixed $5105, $5104=0; not raster or extended-attribute timing.')
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    for field,default in [('tile',117),('color',1),('start-tile',3),('start-color',0)]:
        parser.add_argument('--'+field,type=int,default=default)
    args=parser.parse_args()
    print(json.dumps(create(args.out,args.tile,args.color,args.start_tile,args.start_color),indent=2))
