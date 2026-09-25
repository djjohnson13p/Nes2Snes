#!/usr/bin/env python3
"""Convert a frozen NES display snapshot to native SNES BG/OBJ/CGRAM.

Not a game port: no original instructions, updates, collision or audio execute.
Supports one static nametable and no mid-frame CHR/palette/scroll changes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import subprocess
from build_viewer import ROOT,tool,finalize_rom,validate_sfc
from graphics import nes_to_snes,nametable_to_snes


def sprite_oam(nes:bytes,ctrl:int,crop_top:int=8)->bytes:
    if len(nes)!=256:raise ValueError('Expected 64 NES OAM entries.')
    # Two 8x8 SNES objects per 8x16 NES sprite. Keep original object order.
    result=bytearray([0,240,0,0]*128+list(bytes(32)))
    out=0
    for i in range(64):
        y,tile,attr,x=nes[4*i:4*i+4]
        if y>=239:continue
        tall=bool(ctrl&0x20)
        first=((tile&1)*256+(tile&254)) if tall else ((ctrl&8)*32+tile)
        parts=(1,0) if tall and attr&0x80 else ((0,1) if tall else (0,))
        for row,part in enumerate(parts):
            index=first+part
            priority=1 if attr&0x20 else 3
            flags=((index>>8)&1)|((attr&3)<<1)|(priority<<4)|(attr&0xC0)
            result[out*4:out*4+4]=bytes((x,(y+1-crop_top+row*8)&255,index&255,flags))
            out+=1
    return bytes(result)


def prepare(snapshot:Path,out:Path,nametable:int|None=None):
    def read(name,n):
        b=(snapshot/name).read_bytes()
        if len(b)!=n:raise ValueError(f'{name}: expected {n} bytes, found {len(b)}.')
        return b
    ppu=read('ppu.bin',4);ctrl=ppu[0]
    if ppu[1]!=0x1E:raise ValueError('Static renderer currently requires PPUMASK=$1E (no emphasis/clipping).')
    nts=read('nametables.bin',4096);bg=read('bg-chr.bin',8192);spr=read('spr-chr.bin',8192)
    palette=read('palette.bin',32);rgb=read('rgb-palette.bin',192);oam=read('oam.bin',256)
    scroll=read('scroll.bin',5);temp=int.from_bytes(scroll[:2],'little')
    nt=((temp>>10)&3) if nametable is None else nametable
    if not 0<=nt<=3:raise ValueError('Nametable must be 0..3.')
    # This renderer currently rejects scrolling rather than silently misrender it.
    coarse_x=temp&31;coarse_y=(temp>>5)&31;fine_y=(temp>>12)&7
    if coarse_x or coarse_y or fine_y or scroll[4]:
        raise ValueError(f'Static scene needs zero scroll; captured temp=${temp:04X}, fineX={scroll[4]}.')
    out.mkdir(parents=True,exist_ok=True)
    (out/'background.2bpp').write_bytes(nes_to_snes(bg[4096 if ctrl&0x10 else 0:8192 if ctrl&0x10 else 4096]))
    (out/'sprites.4bpp').write_bytes(nes_to_snes(spr,4))
    (out/'tilemap.bin').write_bytes(nametable_to_snes(nts[nt*1024:(nt+1)*1024],priority=True))
    cgram=[0]*256
    def color(code):
        r,g,b=rgb[(code&63)*3:(code&63)*3+3]
        return (r>>3)|((g>>3)<<5)|((b>>3)<<10)
    for p in range(4):
        for c in range(4):
            cgram[p*4+c]=color(palette[p*4+c] if c else palette[0])
            cgram[128+p*16+c]=color(palette[16+p*4+c] if c else palette[0])
    (out/'cgram.bin').write_bytes(struct.pack('<256H',*cgram))
    (out/'oam.bin').write_bytes(sprite_oam(oam,ctrl))
    return {'nametable':nt,'ppu_control':f'${ctrl:02X}','crop_top':8,'scene_is_static':True,
            'source_capture':json.loads((snapshot/'capture.json').read_text())}


def build(snapshot:Path,out:Path,nametable:int|None=None):
    assets=out/'scene-assets';metadata=prepare(snapshot,assets,nametable)
    subprocess.run([tool('ca65'),'--bin-include-dir',str(assets),'-o',str(out/'scene.o'),
                    str(ROOT/'snes/src/scene.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),'-o',str(out/'scene-core.bin'),
                    str(out/'scene.o')],check=True)
    raw=finalize_rom((out/'scene-core.bin').read_bytes(),b'')
    (out/'frozen-scene.sfc').write_bytes(raw)
    metadata.update(validate_sfc(raw));metadata['original_game_logic_executed']=False
    (out/'scene-build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--nametable',type=int);a=p.parse_args()
    print(json.dumps(build(a.snapshot,a.out,a.nametable),indent=2))
