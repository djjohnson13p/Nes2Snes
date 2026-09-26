#!/usr/bin/env python3
"""Replay a finalized route with a read-only idle observer and check noninterference.

Success means the observer reproduced the source captures, not that the source
route is correct. Failed/faulted source routes remain explicitly unsuccessful.
All captured gameplay and raw measurements belong in private ignored directories.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from gameplay_route import validate_actions
from idle_observer import Observer, validate_config
from libretro_runner import Runner
from route_evidence import atomic_json, load_route


def timeline(report: dict) -> list[dict]:
    segments=report.get('input_segments')
    if not isinstance(segments,list) or not 1<=len(segments)<=10000:
        raise ValueError('Require a nonempty bounded recorded timeline')
    total=0
    for i,row in enumerate(segments):
        if not isinstance(row,dict) or set(row)!={'frames','buttons'} or type(row['frames']) is not int or not 1<=row['frames']<=1000000:
            raise ValueError('Invalid input segment')
        validate_actions([dict(name=f'segment-{i}',updates=1,buttons=row['buttons'])])
        total+=row['frames']
    if total>2000000 or type(report.get('total_emulator_calls')) is not int or total!=report['total_emulator_calls']:
        raise ValueError('Invalid total recorded frame count')
    markers=report['tail_records']
    if markers and markers[-1]['emulator_calls']>total:
        raise ValueError('Checkpoint lies outside the timeline')
    return segments


def observe(core: Path, rom: Path, source: Path, out: Path,
            tick_pc: int, sample_pc: int, addresses: tuple[int,...],capacity: int=32768)->dict:
    validate_config(tick_pc,sample_pc,addresses,capacity)
    report,_=load_route(source);segments=timeline(report)
    if hashlib.sha256(rom.read_bytes()).hexdigest()!=report.get('rom_sha256'):
        raise ValueError('Replay ROM does not match the captured source')
    markers={r['emulator_calls']:r['name'] for r in report['tail_records']}
    out.mkdir(parents=True,exist_ok=True);runner=Runner(core,rom)
    rows=[];calls=0;pixels=0;ram_bytes=0
    try:
        observer=Observer(runner.lib,tick_pc,sample_pc,addresses,capacity)
        for segment in segments:
            for _ in range(segment['frames']):
                calls+=1;observer.before_frame(calls);runner.run(1,tuple(segment['buttons']))
                if calls not in markers:continue
                name=markers[calls];stem='tail-'+name
                expected=(source/(stem+'.ram')).read_bytes();actual=runner.memory()
                with Image.open(source/(stem+'.png')) as image:
                    expected_image=np.array(image.convert('RGB'))
                actual_image=runner.rgb()
                if len(expected)!=len(actual) or expected_image.shape!=actual_image.shape:
                    raise RuntimeError('Replay capture dimensions differ')
                mismatch=sum(x!=y for x,y in zip(expected,actual))
                pixel_mismatch=int(np.any(expected_image!=actual_image,axis=2).sum())
                pixels+=int(actual_image.shape[0]*actual_image.shape[1]);ram_bytes+=len(actual)
                rows.append(dict(name=name,ram_mismatches=mismatch,pixel_mismatches=pixel_mismatch))
        observation=observer.finish()
        failure_matches=None
        if report['status']=='failed':
            expected=(source/'failure.ram').read_bytes()
            failure_matches=expected==runner.memory()
        result=dict(passed=len(rows)==len(markers) and all(r['ram_mismatches']==r['pixel_mismatches']==0 for r in rows)
                    and failure_matches is not False,
                    source_route_passed=report['status']=='completed_budget' and report.get('fault') is None,
                    source_status=report['status'],source_fault=report.get('fault'),
                    failure_ram_matches=failure_matches,platform=report['platform'],checkpoints=len(rows),
                    pixel_positions_compared=pixels,ram_bytes_compared=ram_bytes,results=rows,
                    observation=observation,
                    rom_sha256=report['rom_sha256'],core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    source_report_sha256=hashlib.sha256((source/'route-report.json').read_bytes()).hexdigest(),
                    scope='Read-only observer replay matches the source route on the SAME platform and host-input timeline. Passing this check does not override a source failure or prove NES/SNES timing or gameplay equivalence.')
        atomic_json(out/'idle-route-observation.json',result);return result
    finally:runner.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('core','rom','source','out'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('tick-pc','sample-pc'):p.add_argument('--'+key,type=lambda v:int(v,0),required=True)
    p.add_argument('--ram-byte',type=lambda v:int(v,0),action='append',required=True)
    p.add_argument('--capacity',type=int,default=32768)
    a=p.parse_args();r=observe(a.core,a.rom,a.source,a.out,a.tick_pc,a.sample_pc,tuple(a.ram_byte),a.capacity)
    print(json.dumps({k:v for k,v in r.items() if k not in ('observation','results')},indent=2))
    raise SystemExit(not r['passed'])
