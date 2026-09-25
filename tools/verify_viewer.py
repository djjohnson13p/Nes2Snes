#!/usr/bin/env python3
"""Boot-test and pixel-check every converted CHR page in an independent emulator."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from libretro_runner import Runner
from rom import Rom,sha256
from graphics import decode_nes_tile,synthetic_chr
from build_viewer import validate_sfc


def expected_page(chr_data:bytes,page:int):
    result=np.zeros((128,128),dtype=np.uint8)
    for tile in range(256):
        pos=(page*256+tile)*16
        result[(tile//16)*8:(tile//16+1)*8,(tile%16)*8:(tile%16+1)*8]=decode_nes_tile(chr_data[pos:pos+16])
    return result


def verify(core:Path,sfc:Path,chr_data:bytes,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    sfc_metadata=validate_sfc(sfc.read_bytes())
    r=Runner(core,sfc)
    details=[]
    try:
        r.run(12)
        for page in range(len(chr_data)//4096):
            if page:r.run(1,('r',));r.run(3)
            if r.memory()[0]!=page:raise AssertionError(f'Controller did not select page {page}.')
            # Grayscale red levels: 0,10,20,31 converted to 8-bit by the core.
            red=r.rgb()[40:168,64:192,0].astype(np.int16)
            palette=np.array([0,10*255//31,20*255//31,255],dtype=np.int16)
            observed=np.abs(red[:,:,None]-palette).argmin(axis=2)
            reference=expected_page(chr_data,page)
            errors=int(np.count_nonzero(observed!=reference))
            if errors:raise AssertionError(f'Page {page}: {errors} mismatched pixels.')
            details.append({'page':page,'pixels_checked':16384,'mismatched_pixels':errors})
        r.save_png(out/'last-page.png')
        # Last page wraps to first. Holding a button must not autorepeat.
        r.run(1,('r',));r.run(3)
        assert r.memory()[0]==0
        r.save_png(out/'first-page.png')
        r.run(10,('r',));r.run(3)
        assert r.memory()[0]==1 % (len(chr_data)//4096)
        r.run(1,('l',));r.run(3);assert r.memory()[0]==0
        r.run(1,('l',));r.run(3);assert r.memory()[0]==len(chr_data)//4096-1
        r.run(1,('b',));r.run(3);assert r.memory()[5]==1
        colored=r.rgb();assert np.any(colored[:,:,1]>colored[:,:,0])
        r.save_png(out/'palette-test.png')
        result={'passed':True,'emulator':'Snes9x libretro','core_sha256':sha256(core.read_bytes()),
                'rom':sfc_metadata,'pages_verified':len(details),'pixels_checked':sum(x['pixels_checked'] for x in details),
                'mismatched_pixels':0,'controller_next_previous_wrap_hold':True,'palette_control':True,
                'original_game_executed_on_snes':False,'physical_snes_tested':False,'pages':details}
        (out/'viewer-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:r.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True);p.add_argument('--sfc',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--rom',type=Path);g.add_argument('--synthetic',action='store_true')
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    data=Rom.read(a.rom).chr if a.rom else synthetic_chr()
    result=verify(a.core,a.sfc,data,a.out)
    print(json.dumps({k:v for k,v in result.items() if k!='pages'},indent=2))
if __name__=='__main__':main()
