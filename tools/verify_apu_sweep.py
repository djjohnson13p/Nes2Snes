#!/usr/bin/env python3
"""Validate quantized sweep/counter state and real SNES DSP mute/tone output.

This separately implemented model is not an independent NES hardware oracle.
"""
from __future__ import annotations
import argparse,hashlib,json,wave
from pathlib import Path
import numpy as np
from apu_sweep_model import SweepCounters
from verify_audio import AudioRunner

def verify(core:Path,rom:Path,fixture:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((fixture/'sweep-fixture.json').read_text())
    model=SweepCounters()
    for address,value in meta['initial_audio_writes']:model.write(address,value)
    expected={}
    for frame in range(1,meta['last_frame']+1):
        for address,value in meta['events'].get(str(frame),[]):model.write(address,value)
        model.frame()
        expected[frame]={
            **{0xaa0+4*c:model.lengths[c] for c in range(4)},
            **{0xab0+4*c:model.decay[c] for c in (0,1,3)},
            **{0xac0+4*c:model.divider[c] for c in (0,1,3)},
            **{0xad0+4*c:model.restart[c] for c in (0,1,3)},
            0xae0:model.linear,0xae1:model.reload,0xae2:model.phase,
            **{0xa00+16*c:model.volume(c) for c in range(4)},
            **{0xaf2+4*c:model.periods[c]&255 for c in (0,1)},
            **{0xaf3+4*c:model.periods[c]>>8 for c in (0,1)},
            **{0xaf4+4*c:model.sweep_dividers[c] for c in (0,1)},
            **{0xaf5+4*c:model.sweep_reload[c] for c in (0,1)}}
    r=AudioRunner(core,rom);seen=set();samples={s[0]:[] for s in meta['segments']};pcm_all=[]
    checks=0;last_audio_frame=0
    try:
        rate=r.audio_info().timing.sample_rate
        for host in range(4000):
            r.chunks.clear();r.run(1);m=r.memory();pcm=b''.join(r.chunks);pcm_all.append(pcm)
            if m[0x90f]:raise RuntimeError('Bridge fault: '+m[0x90c:0x910].hex())
            if m[0xa82]:raise RuntimeError('SPC mailbox fault')
            updates=int.from_bytes(m[0xaea:0xaec],'little')
            rendered=int.from_bytes(m[0xaf0:0xaf2],'little')
            for name,first,last,kind in meta['segments']:
                if first<=last_audio_frame<=rendered<=last:samples[name].append(pcm)
            last_audio_frame=rendered
            if rendered and rendered==updates and rendered not in seen and rendered in expected:
                errors=[dict(address=hex(a),expected=v,actual=m[a]) for a,v in expected[rendered].items() if m[a]!=v]
                if errors:raise AssertionError(dict(frame=rendered,errors=errors))
                seen.add(rendered);checks+=len(expected[rendered])
            if rendered>=meta['last_frame']:break
        else:raise RuntimeError('Sweep fixture stalled')
        if seen!=set(expected):raise AssertionError(f'Missed completed output frames: {set(expected)-seen}')
        results=[]
        for name,first,last,kind in meta['segments']:
            data=np.frombuffer(b''.join(samples[name]),dtype='<i2').astype(np.float64)
            if len(data)<1024:raise AssertionError(f'Insufficient PCM in {name}')
            rms=float(np.sqrt(np.mean(data*data)))
            if kind=='silent' and rms>1:raise AssertionError(f'{name}: expected silence, RMS={rms}')
            if kind=='audible' and rms<20:raise AssertionError(f'{name}: expected tone, RMS={rms}')
            results.append(dict(name=name,kind=kind,rms=rms,samples=len(data)))
        with wave.open(str(out/'sweeps.wav'),'wb') as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(round(rate));w.writeframes(b''.join(pcm_all))
        report=dict(passed=True,frames_checked=len(seen),state_bytes_checked=checks,
                    host_frames=r.frames,pcm_segments=results,
                    rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    scope='Frame-quantized sweep/counter state, actual overflow/mute PCM; not independent NES cycle or waveform equivalence')
        (out/'sweep-verification.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:r.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('core','rom','fixture','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(json.dumps(verify(a.core,a.rom,a.fixture,a.out),indent=2))
