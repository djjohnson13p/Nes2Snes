#!/usr/bin/env python3
"""Create a commercial-data-free frozen scene plus an independent NES pixel oracle."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from graphics import synthetic_chr,decode_nes_tile


def create(out:Path):
    out.mkdir(parents=True,exist_ok=True)
    bg=synthetic_chr(2);spr=synthetic_chr(2)
    nt=bytes((x*7+y*11)&255 for y in range(30) for x in range(32))+bytes((n*37)&255 for n in range(64))
    palette=bytes(0 if c==0 else 1+p*3+c-1 for p in range(8) for c in range(4))
    rgb=bytes(v for i in range(64) for v in ((i*37)&255,(i*67)&255,(i*97)&255))
    oam=bytearray([240,0,0,0]*64)
    for i in range(8):
        y=36+(i//2)*44;x=32+(i%2)*120
        # Exercise both pattern tables, 4 sprite palettes, horizontal/vertical flips and priority.
        attr=(i&3)|(0x40 if i&1 else 0)|(0x80 if i&2 else 0)|(0x20 if i&4 else 0)
        oam[i*4:i*4+4]=bytes((y,16+i,attr,x))
    files={'bg-chr.bin':bg,'spr-chr.bin':spr,'nametables.bin':nt*4,'palette.bin':palette,
           'rgb-palette.bin':rgb,'oam.bin':oam,'ppu.bin':bytes((0x30,0x1E,0,0)),'scroll.bin':bytes(5)}
    for name,data in files.items():(out/name).write_bytes(data)
    # Independent NES-style per-pixel composition, before any SNES conversion.
    pixels=np.zeros((240,256),dtype=np.uint8);opaque=np.zeros_like(pixels,dtype=bool)
    for y in range(240):
        for x in range(256):
            tx,ty=x//8,y//8
            tile=nt[ty*32+tx]
            pattern=bg[4096+tile*16:4096+(tile+1)*16]
            c=((pattern[y&7]>>(7-(x&7)))&1)|(((pattern[8+(y&7)]>>(7-(x&7)))&1)<<1)
            attr=nt[960+(ty//4)*8+tx//4];shift=(4 if ty&2 else 0)+(2 if tx&2 else 0)
            p=(attr>>shift)&3
            pixels[y,x]=palette[p*4+c] if c else palette[0]
            opaque[y,x]=bool(c)
    claimed=np.zeros_like(pixels,dtype=bool)
    for i in range(64):
        y,tile,attr,x=oam[i*4:i*4+4]
        if y>=239:continue
        first=(tile&1)*256+(tile&254)
        for dy in range(16):
            sy=y+1+dy
            if sy>=240:continue
            source_y=15-dy if attr&0x80 else dy
            pattern=spr[(first+source_y//8)*16:(first+source_y//8+1)*16]
            for dx in range(8):
                sx=x+dx
                if sx>=256 or claimed[sy,sx]:continue
                source_x=7-dx if attr&0x40 else dx
                c=((pattern[source_y&7]>>(7-source_x))&1)|(((pattern[8+(source_y&7)]>>(7-source_x))&1)<<1)
                if not c:continue
                claimed[sy,sx]=True
                if not (attr&0x20 and opaque[sy,sx]):pixels[sy,sx]=palette[16+(attr&3)*4+c]
    colors=np.frombuffer(rgb,dtype=np.uint8).reshape(64,3)
    Image.fromarray(colors[pixels[8:232]]).save(out/'nes-reference.png')
    (out/'capture.json').write_text(json.dumps({'source':'procedural scene oracle','pixel_format':1,
        'frozen_snapshot':True,'raster_state_complete':True,'width':256,'height':224},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    create(p.parse_args().out)
