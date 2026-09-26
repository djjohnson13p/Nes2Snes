#!/usr/bin/env python3
"""Measure presented-frame cadence and derive a bounded optimization budget.

Frame tags are sampled in the video callback, not inferred after retro_run.
One-display-per-tag is a provisional benchmark target, NOT whole-game completion
or evidence that an original game's intentional slowdown should be removed.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from replay_native import TaggedRunner, ALIGNMENT, inputs

SAMPLES = (('walking',916,1036),('jumping',1036,1061),
           ('attacking',1061,1086),('settling',1086,1146))

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def optimistic_speedup(share: float, removed_fraction: float) -> float:
    """Serial fixed-workload projection; not a vblank/scheduling forecast."""
    for value in (share,removed_fraction):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Cost fractions must be finite numbers')
        if not 0 <= value <= 1:raise ValueError('Cost fractions must be in 0..1')
    remaining=1-share*removed_fraction
    if remaining <= 0:raise ValueError('Projection would remove the entire workload')
    return 1/remaining

def summarize(records: list[dict], samples=SAMPLES) -> list[dict]:
    """Validate contiguous tags and strictly increasing presentation positions."""
    if not records:raise ValueError('No frame evidence')
    by_id={}
    previous=None
    for row in records:
        tag,host=row['game_frame'],row['display_frame']
        if type(tag) is not int or type(host) is not int or tag < 0 or host < 0:
            raise ValueError('Frame IDs must be nonnegative integers')
        if tag in by_id:raise ValueError('Duplicate game-frame record')
        if previous is not None and (tag != previous[0]+1 or host <= previous[1]):
            raise ValueError('Frame tags must be contiguous and display positions increasing')
        by_id[tag]=row
        previous=(tag,host)
    result=[]
    for name,start,end in samples:
        if type(start) is not int or type(end) is not int or end <= start:
            raise ValueError('Invalid sample interval')
        if not all(n in by_id for n in range(start,end+1)):
            raise ValueError(f'Missing evidence for {name}')
        spacing=[by_id[n]['display_frame']-by_id[n-1]['display_frame'] for n in range(start+1,end+1)]
        elapsed=sum(spacing);count=end-start
        result.append(dict(name=name,start_tag=start,end_tag=end,tagged_game_frames=count,
            display_frames=elapsed,display_frames_per_tag=elapsed/count,
            one_to_one_cadence=all(n==1 for n in spacing),
            extra_display_frames=elapsed-count,max_display_spacing=max(spacing),
            spacing_histogram={str(k):v for k,v in sorted(Counter(spacing).items())},
            required_time_reduction_fraction=1-count/elapsed,
            required_throughput_increase_fraction=elapsed/count-1))
    return result

def validate_profile(profile: dict, rom_hash: str) -> None:
    if profile['rom_sha256'] != rom_hash:raise ValueError('Profile uses a different ROM')
    total=profile['elapsed_master_clocks']
    if type(total) is not int or total <= 0:raise ValueError('Invalid elapsed clocks')
    regions=profile['regions'];names=[r['region'] for r in regions]
    if len(set(names)) != len(names):raise ValueError('Duplicate profile region')
    costs=[r['master_clocks'] for r in regions]
    if any(type(c) is not int or c < 0 for c in costs):raise ValueError('Invalid attributed clocks')
    residual=profile['unattributed_master_clocks']
    if type(residual) is not int or residual < 0 or sum(costs)+residual != total:
        raise ValueError('Profile clocks do not balance')
    caller=profile.get('cop_callers',{})
    if caller.get('overlapping_starts',0):raise ValueError('Overlapping caller accounting')
    # This is an overlapping attribution view, never another additive region.
    span=caller.get('completed_master_clocks',0)
    if type(span) is not int or not 0 <= span <= total:
        raise ValueError('Invalid overlapping COP-span total')

def collect(core: Path, rom: Path, build_manifest: Path, out: Path) -> dict:
    build=json.loads(build_manifest.read_text())
    rom_hash=sha(rom)
    if build['sha256'] != rom_hash:raise ValueError('Build manifest does not match ROM bytes')
    input_hash=hashlib.sha256(inputs()).hexdigest()
    if build.get('test_input_replay_sha256') != input_hash:
        raise ValueError('Require the fixed benchmark replay, not live input or another route')
    r=TaggedRunner(core,rom);rows=[];last=None;conflicts=[]
    try:
        for _ in range(30000):
            r.run(1);m=r.memory()
            if m[0x90F]:raise RuntimeError('Bridge fault: '+m[0x90C:0x910].hex())
            tag=r.render_tag
            if tag is None or tag < SAMPLES[0][1]:continue
            if tag > SAMPLES[-1][2]:break
            pixel=hashlib.sha256(r.rgb().tobytes()).hexdigest()
            if tag == last:
                if pixel != rows[-1]['pixel_sha256']:
                    conflicts.append(dict(game_frame=tag,display_frame=r.frames))
                continue
            rows.append(dict(game_frame=tag,display_frame=r.frames,pixel_sha256=pixel))
            last=tag
            if tag==SAMPLES[-1][2]:break
        else:raise RuntimeError('Timed out reaching the fixed replay interval')
        segments=summarize(rows)
        relevant={k:(v.decode() if isinstance(v,bytes) else v) for k,v in r.variables.items()
                  if any(t in k.lower() for t in ('overclock','reduce','frameskip','region'))}
        result=dict(schema=1,alignment=ALIGNMENT,rom_sha256=rom_hash,core_sha256=sha(core),
                    build_manifest_sha256=sha(build_manifest),input_sha256=input_hash,
                    observed_instruction_sites=build['observed_instruction_sites'],
                    source_scope='Exact supplied build manifest; private trace identity must accompany a release.',
                    core_options=relevant,records=rows,segments=segments,
                    repeated_tag_pixel_conflicts=conflicts,
                    scope=__doc__,complete_game_verified=False)
        if conflicts:raise RuntimeError('One presented frame tag had differing images')
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('core','rom','build-manifest','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=collect(a.core,a.rom,a.build_manifest,a.out)
    print(json.dumps({k:v for k,v in r.items() if k!='records'},indent=2))
