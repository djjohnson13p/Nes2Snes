#!/usr/bin/env python3
"""Verify live native object buffers against an independent OAM encoding model.

This tests encoding/cache invalidation, not physical PPU scanline limits.
"""
from __future__ import annotations
import argparse,hashlib,json,struct
from pathlib import Path
from libretro_runner import Runner

def expected_objects(oam:bytes,ctrl:int)->bytes:
    if len(oam)!=256:raise ValueError('NES OAM must contain exactly 256 bytes')
    result=bytearray()
    hidden=bytes([0,240,0,0])
    for offset in range(0,256,4):
        y,tile,flags,x=oam[offset:offset+4]
        if y>=239:
            result.extend(hidden*2);continue
        sy=(y-7)&255
        attr=(flags&0xc0)|((flags&3)<<1)|(0x10 if flags&0x20 else 0x30)
        if ctrl&0x20:
            attr|=tile&1
            top=(tile&0xfe)+(1 if flags&0x80 else 0)
            result.extend(bytes([x,sy,top,attr,x,(sy+8)&255,top^1,attr]))
        else:
            attr|=(ctrl>>3)&1
            result.extend(bytes([x,sy,tile,attr])+hidden)
    return bytes(result)

def verify(core:Path,rom:Path,out:Path,frames:int=160)->dict:
    if not 1<=frames<=4096:raise ValueError('frames must be between 1 and 4096')
    out.mkdir(parents=True,exist_ok=True)
    r=Runner(core,rom);seen=set();m=b'';mode_seen=set()
    try:
        for _ in range(frames*12+600):
            r.run(1);m=r.memory()
            if m[0x90f]:raise RuntimeError(f'Bridge fault {m[0x90c:0x910].hex()}')
            g=int.from_bytes(m[0x906:0x908],'little')
            ready=m[0x946] # queued frame was completely converted
            presented=int.from_bytes(m[0x974:0x976],'little')
            # Pipelined builds expose a queued completed frame; synchronous
            # builds expose a presented completed frame before next guest NMI.
            if g and (ready or (presented==g and not m[0x904])) and g not in seen:
                expected=expected_objects(m[0x3800:0x3900],m[0x910])
                actual=m[0x12000:0x12200]
                if actual!=expected:
                    mismatches=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
                    raise RuntimeError(f'OAM mismatch at frame {g}, offsets {mismatches[:16]}')
                seen.add(g);mode_seen.add(m[0x910]&0x28)
                if len(seen)>=frames:break
        else:raise RuntimeError(f'Only observed {len(seen)} completed frames')
        converted=int.from_bytes(m[0x976:0x97a],'little')
        cached=int.from_bytes(m[0x97a:0x97e],'little')
        if not converted or not cached:raise RuntimeError('Both conversion and cache paths must execute')
        if frames>=64 and mode_seen!={0,8,32,40}:raise RuntimeError('Did not exercise all sprite mode combinations')
        result=dict(frames_checked=len(seen),oam_bytes_checked=len(seen)*512,mismatch_count=0,
                    sprite_modes=sorted(mode_seen),converted_objects=converted,cached_objects=cached,
                    core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                    scope='Original procedural dynamic OAM encoding and cache invalidation; not full PPU accuracy.')
        (out/'object-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('core','rom','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--frames',type=int,default=160);a=p.parse_args()
    print(json.dumps(verify(a.core,a.rom,a.out,a.frames),indent=2))
