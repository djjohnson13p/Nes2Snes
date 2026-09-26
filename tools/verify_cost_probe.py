#!/usr/bin/env python3
"""Calibrate the diagnostic core on an authored CPU fixture, not a game ROM."""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_native import build
from native_fixture import create
from verify_native_cpu import verify
from libretro_runner import Runner
from profile_frame_costs import cop_callers

def capture(core: Path, rom: Path, out: Path, probe: bool) -> None:
    out.mkdir(parents=True,exist_ok=True)
    r=Runner(core,rom)
    try:
        if probe:
            r.lib.retro_n2s_cost_reset.argtypes=[];r.lib.retro_n2s_cost_reset.restype=None
            r.lib.retro_n2s_cost_elapsed.argtypes=[];r.lib.retro_n2s_cost_elapsed.restype=C.c_uint64
            r.lib.retro_n2s_cost_reset()
        for _ in range(300):
            r.run(1);memory=r.memory()
            if memory[0x90f]:raise RuntimeError('Bridge fault during probe calibration')
            if memory[0x7e]==0x5a:break
        else:raise RuntimeError('Fixture did not complete')
        (out/'full-wram.bin').write_bytes(memory)
        report=dict(frames=r.frames,pixel_sha256=hashlib.sha256(r.rgb().tobytes()).hexdigest(),
                    ram_sha256=hashlib.sha256(memory).hexdigest(),audio_frames=r.audio_frames)
        if probe:
            report['cop_callers']=cop_callers(r.lib,int(r.lib.retro_n2s_cost_elapsed()))
            if report['cop_callers']['completed_calls']==0:
                raise RuntimeError('The caller probe was not exercised')
        (out/'capture.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:r.close()

def run(nes_core: Path, plain_core: Path, probe_core: Path, out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True);fixture=out/'fixture'
    create(fixture);build(fixture/'fixture.nes',fixture,fixture/'snes')
    checks={}
    for name,core in [('plain',plain_core),('probe',probe_core)]:
        checks[name]=verify(nes_core,core,fixture,out/(name+'-oracle'))
        cmd=[sys.executable,__file__,'--capture','--core',str(core),
             '--rom',str(fixture/'snes/native-prototype.sfc'),'--out',str(out/name)]
        if name=='probe':cmd.append('--probe')
        subprocess.run(cmd,check=True,timeout=60)
    plain=json.loads((out/'plain/capture.json').read_text())
    probe=json.loads((out/'probe/capture.json').read_text())
    for field in ('frames','pixel_sha256','ram_sha256','audio_frames'):
        if plain[field]!=probe[field]:raise RuntimeError('Diagnostic core changed '+field)
    if (out/'plain/full-wram.bin').read_bytes()!=(out/'probe/full-wram.bin').read_bytes():
        raise RuntimeError('Diagnostic core changed WRAM')
    report=dict(passed=True,scope=__doc__,records_per_core=checks['plain']['records_checked'],
                ram_bytes_matched=len((out/'plain/full-wram.bin').read_bytes()),
                completed_cop_calls=probe['cop_callers']['completed_calls'],
                frame_count=plain['frames'],overlapping_starts=probe['cop_callers']['overlapping_starts'],
                core_sha256={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in
                             [('nes',nes_core),('plain',plain_core),('probe',probe_core)]})
    (out/'probe-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',action='store_true');p.add_argument('--probe',action='store_true')
    for n in ('core','rom','nes-core','plain-core','probe-core','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.capture:
        if not all((a.core,a.rom,a.out)):p.error('Capture requires core, rom and out')
        capture(a.core,a.rom,a.out,a.probe)
    else:
        if not all((a.nes_core,a.plain_core,a.probe_core,a.out)):p.error('Require all three cores and out')
        print(json.dumps(run(a.nes_core,a.plain_core,a.probe_core,a.out),indent=2))
