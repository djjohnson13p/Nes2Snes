#!/usr/bin/env python3
"""Compare a native SNES frozen scene against its NES reference frame.

The reference must be full 8-bit RGB. Quantization models SNES RGB555 plus the
Snes9x core's RGB565 video callback, not physical analog display characteristics.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from build_viewer import validate_sfc
from libretro_runner import Runner
from rom import sha256


def quantize_reference(rgb):
    c=np.asarray(rgb,dtype=np.uint16)>>3
    result=c*255//31
    result[:,:,1]=((c[:,:,1]<<1)|(c[:,:,1]>>4))*255//63
    return result.astype(np.uint8)


def verify(core:Path,sfc:Path,snapshot:Path,out:Path):
    capture=json.loads((snapshot/'capture.json').read_text())
    if capture.get('pixel_format')!=1:raise ValueError('Reference must be captured as full 8-bit RGB (libretro XRGB8888).')
    original=np.array(Image.open(snapshot/'nes-reference.png').convert('RGB'))
    if original.shape!=(224,256,3):raise ValueError('Expected a 256x224 reference frame.')
    out.mkdir(parents=True,exist_ok=True)
    r=Runner(core,sfc)
    try:
        r.run(12)
        if r.format!=2:raise ValueError('This color-precision comparison expects RGB565 from Snes9x.')
        observed=r.rgb();expected=quantize_reference(original)
        if observed.shape!=expected.shape:raise AssertionError('Reference and SNES dimensions differ.')
        mismatches=int(np.count_nonzero(np.any(observed!=expected,axis=2)))
        r.save_png(out/'snes-scene.png')
        Image.fromarray(expected).save(out/'quantized-reference.png')
        result={'passed':mismatches==0,'pixels_checked':224*256,'normalized_mismatched_pixels':mismatches,
                'raw_rgb_different_pixels':int(np.count_nonzero(np.any(observed!=original,axis=2))),
                'comparison':'NES RGB quantized to RGB555, then Snes9x RGB565 output expansion',
                'rom':validate_sfc(sfc.read_bytes()),'core_sha256':sha256(core.read_bytes()),
                'scene_is_static':True,'original_game_logic_executed':False,'physical_snes_tested':False}
        (out/'scene-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        if mismatches:raise AssertionError(f'{mismatches} scene pixels differ after color quantization.')
        return result
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True);p.add_argument('--sfc',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(verify(a.core,a.sfc,a.snapshot,a.out),indent=2))
