#!/usr/bin/env python3
"""Calibrate each observer against its plain emulator and authored program log.

Separate processes avoid process-global libretro state. Tests do not assert equal
idle-state values between NES and SNES: that difference is the measurement target.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_native import build
from idle_fixture import create
from idle_observer import Observer
from libretro_runner import Runner
from route_evidence import atomic_json


def sample(core: Path, rom: Path, meta: dict, out: Path, probe: bool) -> None:
    r=Runner(core,rom)
    observer=Observer(r.lib,meta['tick_pc'],meta['sample_pc'],tuple(meta['addresses'])) if probe else None
    frames=0;images=hashlib.sha256()
    try:
        for frames in range(1,1001):
            if observer:observer.before_frame(frames)
            r.run(1);images.update(r.rgb().tobytes())
            if r.memory()[0x7e]==0x5a:break
        else:raise RuntimeError('Fixture did not finish')
        ram=r.memory();data=dict(frames=frames,video_callbacks=r.frames,audio_frames=r.audio_frames,
                                 frame_sequence_sha256=images.hexdigest(),
                                 ram_sha256=hashlib.sha256(ram).hexdigest(),
                                 logged_seed=list(ram[0x600:0x620]),
                                 logged_ticks=[ram[0x620+i]+256*ram[0x640+i]+65536*ram[0x660+i] for i in range(32)],
                                 final_samples=ram[0x41])
        if observer:data['observation']=observer.finish()
        atomic_json(out,data)
    finally:r.close()


def check_capture(a: dict, b: dict) -> None:
    """Strict calibration acceptance; retain differing captures as failures."""
    required = {'frames', 'video_callbacks', 'audio_frames', 'frame_sequence_sha256',
                'ram_sha256', 'logged_seed', 'logged_ticks', 'final_samples'}
    if set(a) != required or set(b) != required | {'observation'}:
        raise ValueError('Invalid calibration capture fields')
    if any(a[k] != b[k] for k in a):
        raise RuntimeError('Observer changed emulated output')
    observation = b['observation']
    if (observation.get('complete') is not True or observation.get('overflow') is not False
            or observation.get('samples') != 32 or a['final_samples'] != 32
            or len(observation.get('records', [])) != 32
            or len(a['logged_seed']) != 32 or len(a['logged_ticks']) != 32):
        raise RuntimeError('Incomplete or overflowing sample count')
    previous_ticks = 0
    for i, record in enumerate(observation['records']):
        if record['sample'] != i+1 or record['ticks'] < previous_ticks:
            raise RuntimeError('Invalid sample ordering')
        if record['ram']['0040'] != a['logged_seed'][i] or record['ram']['0041'] != i:
            raise RuntimeError('Sampled RAM differs from independently executed NMI log')
        if (record['ticks'] != a['logged_ticks'][i]
                or record['ram']['0042'] + 256*record['ram']['0043'] + 65536*record['ram']['0044'] != a['logged_ticks'][i]):
            raise RuntimeError('Instruction counts differ from independent NMI counter log')
        previous_ticks = record['ticks']


def verify(nes_plain: Path,nes_probe: Path,snes_plain: Path,snes_probe: Path,out: Path)->dict:
    out.mkdir(parents=True,exist_ok=True);meta=create(out/'fixture')
    build(out/'fixture/fixture.nes',out/'fixture',out/'fixture/snes')
    rows=[]
    for platform,plain,probe in [('nes',nes_plain,nes_probe),('snes',snes_plain,snes_probe)]:
        rom=out/'fixture'/('fixture.nes' if platform=='nes' else 'snes/native-prototype.sfc')
        for role,core in [('plain',plain),('probe',probe)]:
            subprocess.run([sys.executable,__file__,'--sample',role,'--core',str(core),'--rom',str(rom),
                            '--meta',str(out/'fixture/idle-fixture.json'),'--out',str(out/(platform+'-'+role+'.json'))],
                            check=True,timeout=90)
        a=json.loads((out/(platform+'-plain.json')).read_text());b=json.loads((out/(platform+'-probe.json')).read_text())
        check_capture(a,b)
        observation=b['observation']
        rows.append(dict(platform=platform,passed=True,samples=32,records_verified=32,
                         ram_bytes_compared=2048 if platform=='nes' else 131072,
                         core_sha256={'plain':hashlib.sha256(plain.read_bytes()).hexdigest(),
                                      'probe':hashlib.sha256(probe.read_bytes()).hexdigest()},
                         plain_output=a,observation=observation))
    result=dict(passed=True,platforms=2,samples_verified=64,results=rows,
                scope='Each observed core matches its unmodified counterpart and authored in-ROM log. Cross-platform RNG parity, cycle accuracy and game completion are not claimed.')
    atomic_json(out/'idle-observer-verification.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=['plain','probe'])
    for name in ('core','rom','meta','nes-plain','nes-probe','snes-plain','snes-probe','out'):
        p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.sample:sample(a.core,a.rom,json.loads(a.meta.read_text()),a.out,a.sample=='probe')
    else:
        r=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_plain.resolve(),a.snes_probe.resolve(),a.out.resolve())
        print(json.dumps({k:v for k,v in r.items() if k!='results'},indent=2))
