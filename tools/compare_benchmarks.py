#!/usr/bin/env python3
"""Compare private native-game benchmark captures without publishing game art."""
from pathlib import Path
import argparse
import json

def compare(before:Path,after:Path,out:Path)->dict:
    import numpy as np
    from PIL import Image
    old=json.loads((before/'benchmark.json').read_text())
    new=json.loads((after/'benchmark.json').read_text())
    if old['core_sha256']!=new['core_sha256']:
        raise ValueError('Benchmark cores differ')
    source={r['label']:r for r in old['records']}
    rows=[]; pixels=0; mismatches=0
    for r in new['records']:
        a=source[r['label']]
        if a['guest_frames']!=r['guest_frames']:raise ValueError('Guest sample lengths differ')
        aa=np.array(Image.open(before/(r['label']+'.png')))
        bb=np.array(Image.open(after/(r['label']+'.png')))
        if aa.shape!=bb.shape:raise ValueError('Frame geometry differs')
        n=int(np.any(aa!=bb,axis=-1).sum())
        pixels+=aa.shape[0]*aa.shape[1];mismatches+=n
        rows.append(dict(label=r['label'],guest_frames=r['guest_frames'],
                         before_snes_frames=a['snes_frames'],after_snes_frames=r['snes_frames'],
                         speed_multiplier=a['snes_frames']/r['snes_frames'],pixel_mismatches=n))
    result=dict(before_sfc_sha256=old['sfc_sha256'],after_sfc_sha256=new['sfc_sha256'],
                core_sha256=new['core_sha256'],samples=rows,
                total_pixels_compared=pixels,total_pixel_mismatches=mismatches,
                scope='Five selected early-game frames, not complete gameplay or raster equivalence; speed measured in emulated SNES frames, not host wall time.')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n')
    if mismatches:raise RuntimeError('Selected frames differ; inspect before claiming equivalence')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('before','after','out'):p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args();print(json.dumps(compare(a.before,a.after,a.out),indent=2))
