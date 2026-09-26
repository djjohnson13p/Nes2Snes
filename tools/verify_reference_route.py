#!/usr/bin/env python3
"""Replay the exact recorded NES host-input timeline in an unmodified core.

This validates that instrumentation supplied the same observed images and RAM,
not that the SNES port is perfect. Outputs contain game-derived data and belong
in an ignored/private build directory.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
from libretro_runner import Runner
from gameplay_route import validate_actions


def verify(core:Path,rom:Path,source:Path,out:Path)->dict:
    report=json.loads((source/'route-report.json').read_text())
    if report.get('platform')!='nes' or report.get('status')!='completed_budget':
        raise ValueError('Require a completed NES trace route')
    if hashlib.sha256(rom.read_bytes()).hexdigest()!=report['rom_sha256']:
        raise ValueError('Recorded input belongs to another ROM')
    actions=validate_actions(report['tail_actions']);markers=report['tail_records']
    if len(markers)!=len(actions) or any(a['name']!=m['name'] for a,m in zip(actions,markers)):
        raise ValueError('Action marker sequence does not match validated names')
    if any(type(m['emulator_calls']) is not int or m['emulator_calls']<=0 for m in markers):
        raise ValueError('Invalid frame marker')
    if any(a['emulator_calls']>=b['emulator_calls'] for a,b in zip(markers,markers[1:])):
        raise ValueError('Frame markers must be strictly ordered')
    segments=report['input_segments'];total=0
    allowed={'a','b','start','select','up','down','left','right'}
    if not isinstance(segments,list) or len(segments)>10000:raise ValueError('Invalid input timeline')
    for s in segments:
        if not isinstance(s,dict) or set(s)!={'frames','buttons'} or type(s['frames']) is not int or not 0<s['frames']<=1000000:
            raise ValueError('Invalid input segment')
        if not isinstance(s['buttons'],list) or any(not isinstance(b,str) or b not in allowed for b in s['buttons']):
            raise ValueError('Invalid recorded button')
        total+=s['frames']
    if total>2000000 or total!=report['total_emulator_calls'] or markers[-1]['emulator_calls']>total:
        raise ValueError('Invalid total frame budget')
    out.mkdir(exist_ok=True,parents=True);r=Runner(core,rom);calls=0;index=0;results=[]
    try:
        for s in segments:
            remaining=s['frames']
            while remaining:
                take=remaining
                if index<len(markers):take=min(take,markers[index]['emulator_calls']-calls)
                if take:r.run(take,tuple(s['buttons']));calls+=take;remaining-=take
                if index<len(markers) and calls==markers[index]['emulator_calls']:
                    name='tail-'+markers[index]['name'];r.save_png(out/(name+'.png'))
                    ram=r.memory();(out/(name+'.ram')).write_bytes(ram)
                    expected=(source/(name+'.ram')).read_bytes()
                    a=np.asarray(Image.open(source/(name+'.png')).convert('RGB'));b=r.rgb()
                    if a.shape!=b.shape or len(expected)!=len(ram):raise ValueError('Capture dimensions differ')
                    results.append(dict(name=markers[index]['name'],pixels_checked=int(a.shape[0]*a.shape[1]),
                                        rgb_pixel_mismatches=int(np.any(a!=b,axis=2).sum()),ram_bytes_checked=len(ram),
                                        ram_byte_mismatches=sum(x!=y for x,y in zip(expected,ram))))
                    index+=1
                elif take==0:raise RuntimeError('Input timeline made no progress')
    finally:r.close()
    result=dict(passed=len(results)==len(markers) and all(x['rgb_pixel_mismatches']==x['ram_byte_mismatches']==0 for x in results),
                scope='Unmodified NES reference vs instrumented NES observations at identical host-frame input times. Not SNES equivalence.',
                rom_sha256=report['rom_sha256'],reference_core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                probe_core_sha256=report['core_sha256'],results=results)
    (out/'reference-verification.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('core','rom','source','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();v=verify(a.core,a.rom,a.source,a.out)
    print(json.dumps({k:v for k,v in v.items() if k!='results'},indent=2));raise SystemExit(not v['passed'])
