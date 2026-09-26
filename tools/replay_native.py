#!/usr/bin/env python3
"""Test-only fixed guest-frame input and render-aligned CV3 regression capture.

The optional input mode is compiled out of ordinary interactive builds. This
bounded route does not establish full-game correctness. Keep all output private.
"""
from __future__ import annotations
import ctypes as C
import argparse
import hashlib
import json
from pathlib import Path
from libretro_runner import Runner


ALIGNMENT = 'video-callback-presented-id-v1'

class TaggedRunner(Runner):
    """Read the presented-frame ID when the emulator delivers the video frame.

    Sampling after retro_run, or taking its previous value, can associate the
    image with a different upload when the guest's execution time changes.
    """
    def __init__(self, *args, **kwargs):
        self.render_tag = None
        super().__init__(*args, **kwargs)

    def video(self, data, width, height, pitch):
        super().video(data, width, height, pitch)
        if data and data != C.c_void_p(-1).value:
            size = self.lib.retro_get_memory_size(2)
            ptr = self.lib.retro_get_memory_data(2)
            if not ptr or size < 0x976:
                self.errors.append('Presented-frame tag requires SNES WRAM')
                return
            self.render_tag = int.from_bytes(C.string_at(ptr + 0x974, 2), 'little')

SAMPLES = {'stage-idle':916, 'walk-right':1036, 'jump-right':1061,
           'attack':1086, 'settle':1146}

def inputs() -> bytes:
    result=bytearray(4096)
    for start in (122,269,416,563,710):
        result[start:start+2]=bytes([8,8])
    result[917:1037]=bytes([128])*120
    result[1037:1062]=bytes([129])*25
    result[1062:1087]=bytes([2])*25
    return bytes(result)

def capture(core:Path,rom:Path,out:Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    r=TaggedRunner(core,rom)
    results=[]
    pending={value:key for key,value in SAMPLES.items()}
    try:
        for _ in range(20000):
            r.run(1)
            m=r.memory()
            if len(m)<0x20000:raise RuntimeError('Expected full SNES WRAM')
            if m[0x90f]:raise RuntimeError(f'Bridge fault: {m[0x90c:0x910].hex()}')
            presented=r.render_tag
            if presented in pending:
                name=pending.pop(presented)
                if m[0x18]!=4:raise RuntimeError('Replay did not reach main game state')
                r.save_png(out/(name+'.png'))
                (out/(name+'.ram')).write_bytes(m)
                results.append(dict(name=name,render_frame=presented,
                                    snes_frame=r.frames,pixel_sha256=hashlib.sha256(r.rgb().tobytes()).hexdigest(),
                                    fault=m[0x90f]))
            if not pending:break
        else:raise RuntimeError(f'Replay did not reach samples: {pending}')
        result=dict(alignment=ALIGNMENT,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                    core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    input_sha256=hashlib.sha256(inputs()).hexdigest(),samples=results,
                    scope='Five render-aligned captures on one fixed guest-input route; not full-game proof.')
        (out/'replay.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-input',type=Path)
    p.add_argument('--core',type=Path);p.add_argument('--rom',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.write_input:
        a.write_input.parent.mkdir(parents=True,exist_ok=True)
        a.write_input.write_bytes(inputs())
    else:
        if not all((a.core,a.rom,a.out)):p.error('Require --core --rom --out')
        print(json.dumps(capture(a.core,a.rom,a.out),indent=2))
