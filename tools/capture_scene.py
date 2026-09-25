#!/usr/bin/env python3
"""Capture one frozen MMC5 display state for scene-conversion experiments.

This is not a gameplay port or a complete raster-state capture. The default
script visits the CV3 title. Per-scanline bank changes must be handled separately.
"""
from __future__ import annotations
import argparse
import ctypes as C
import json
from pathlib import Path
from libretro_runner import Runner
from rom import Rom, sha256

SNAPSHOTS={8:'palette.bin',9:'nametables.bin',10:'bg-chr.bin',11:'spr-chr.bin',
           12:'oam.bin',13:'ppu.bin',14:'rgb-palette.bin',15:'scroll.bin'}


def capture(core:Path,rom_path:Path,out:Path,pulses:int=1):
    rom=Rom.read(rom_path)
    if rom.mapper!=5:raise ValueError('Snapshot probe currently requires MMC5.')
    if not 0<=pulses<=20:raise ValueError('Start pulse count must be 0..20.')
    out.mkdir(parents=True,exist_ok=True)
    r=Runner(core,rom_path)
    r.lib.retro_n2s_size.argtypes=[C.c_uint];r.lib.retro_n2s_size.restype=C.c_size_t
    r.lib.retro_n2s_data.argtypes=[C.c_uint];r.lib.retro_n2s_data.restype=C.c_void_p
    try:
        r.run(120)
        for _ in range(pulses):r.run(1,('start',));r.run(150)
        for kind,name in SNAPSHOTS.items():
            size=r.lib.retro_n2s_size(kind);ptr=r.lib.retro_n2s_data(kind)
            if not ptr or not size:raise ValueError(f'Probe snapshot {kind} unavailable; rebuild the current probe.')
            (out/name).write_bytes(C.string_at(ptr,size))
        r.save_png(out/'nes-reference.png')
        metadata={'rom_sha256':sha256(rom.raw),'core_sha256':sha256(core.read_bytes()),
                  'pixel_format':r.format,'frames':r.frames,'start_pulses':pulses,'frozen_snapshot':True,
                  'raster_state_complete':False,'width':r.width,'height':r.height}
        (out/'capture.json').write_text(json.dumps(metadata,indent=2)+'\n')
        return metadata
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True);p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--start-pulses',type=int,default=1)
    a=p.parse_args();print(json.dumps(capture(a.core,a.rom,a.out,a.start_pulses),indent=2))
