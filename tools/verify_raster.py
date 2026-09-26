#!/usr/bin/env python3
"""Independent NES/SNES two-color geometry tests for optional raster scrolling.

Two partial transition scanlines are reported separately, never counted as an
exact match. The fixture fixes its reload delay; it is not a test of arbitrary
raster routines or clock-accurate execution.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
from raster_fixture import create
from build_native import build,ROOT

Y_CASES=(0,1,7,8,63,178,239)
TRANSITION_ROWS=(32,48)

def verify(nes_core:Path,snes_core:Path,out:Path,cases=Y_CASES)->dict:
    out.mkdir(parents=True,exist_ok=True);records=[]
    for y in cases:
        fixture=out/f'y{y:03d}';create(fixture,y)
        built=build(fixture/'fixture.nes',fixture,fixture/'snes',raster_scroll=True)
        for tag,core,rom,frames in [('nes',nes_core,fixture/'fixture.nes',120),('snes',snes_core,fixture/'snes/native-prototype.sfc',240)]:
            subprocess.run([sys.executable,str(ROOT/'tools/libretro_runner.py'),'--core',str(core),'--rom',str(rom),
                            '--frames',str(frames),'--out',str(fixture/(tag+'.png'))],check=True,stdout=subprocess.DEVNULL)
        a=np.asarray(Image.open(fixture/'nes.png').convert('RGB'));b=np.asarray(Image.open(fixture/'snes.png').convert('RGB'))
        if a.shape!=(224,256,3) or b.shape!=a.shape:raise ValueError('Unexpected frame shape')
        aa=np.max(a,axis=2)>128;bb=np.max(b,axis=2)>128;d=aa!=bb
        stable=np.ones((224,256),dtype=bool);stable[list(TRANSITION_ROWS)]=False
        row=dict(y=y,rom_sha256=built['sha256'],stable_pixels=int(stable.sum()),stable_pixel_mismatches=int(d[stable].sum()),
                 full_frame_pixels=int(d.size),full_frame_pixel_mismatches=int(d.sum()),
                 transition_rows=list(TRANSITION_ROWS),transition_pixel_mismatches=int(d[~stable].sum()),
                 passed=not bool(d[stable].any()))
        (fixture/'verification.json').write_text(json.dumps(row,indent=2)+'\n');records.append(row)
        print(json.dumps(row),flush=True)
    result=dict(scope='Black/white pattern geometry against independent NES core; transition rows are known inexact; fixed reload timing contract only',
                cases=records,passed=all(x['passed'] for x in records),
                stable_pixels=sum(x['stable_pixels'] for x in records),stable_pixel_mismatches=sum(x['stable_pixel_mismatches'] for x in records),
                full_frame_pixel_mismatches=sum(x['full_frame_pixel_mismatches'] for x in records),
                nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
                commercial_game_content=False)
    (out/'raster-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('nes-core','snes-core','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();r=verify(a.nes_core,a.snes_core,a.out);raise SystemExit(not r['passed'])
