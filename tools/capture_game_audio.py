#!/usr/bin/env python3
"""Capture ordinary-controller stage-one PCM while running the bounded benchmark.

Input-derived WAV/screenshots remain in ignored build/. This is not an audio
accuracy test; procedural tones are tested separately by verify_audio.py.
"""
from __future__ import annotations
import argparse,json,wave
from pathlib import Path
import numpy as np
import benchmark_native
from verify_audio import AudioRunner

def capture(core:Path,rom:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True);sessions=[]
    class RecordingRunner(AudioRunner):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.stage=[];self.rate=self.audio_info().timing.sample_rate;sessions.append(self)
        def run(self,frames,buttons=()):
            self.chunks.clear();super().run(frames,buttons)
            m=self.memory()
            if m[0x18]==4:self.stage.extend(self.chunks)
            if sum(len(x) for x in self.stage)>64*1024*1024:raise RuntimeError('PCM capture exceeded 64 MiB limit')
        def close(self):
            if not self.closed:self.final_memory=self.memory()
            super().close()
    previous=benchmark_native.Runner;benchmark_native.Runner=RecordingRunner
    try:benchmark_native.benchmark(core,rom,out/'benchmark')
    finally:benchmark_native.Runner=previous
    r=sessions[0];raw=b''.join(r.stage);pcm=np.frombuffer(raw,dtype='<i2')
    if len(pcm)==0 or not np.any(pcm):raise RuntimeError('No stage-one sound recorded')
    m=r.final_memory
    if m[0xa80]!=1 or m[0xa82]:raise RuntimeError('SPC receiver failed')
    with wave.open(str(out/'stage-one-audio-preview.wav'),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(round(r.rate));w.writeframes(raw)
    result=dict(seconds=len(pcm)/2/r.rate,sample_rate=r.rate,peak=int(np.abs(pcm.astype('int32')).max()),
                rms=float(np.sqrt(np.mean(pcm.astype('float64')**2))),clipped_samples=int(np.count_nonzero((pcm==32767)|(pcm==-32768))),
                spc_ready=m[0xa80],spc_fault=m[0xa82],dsp_commands=int.from_bytes(m[0xa84:0xa86],'little'),
                scope='Live four-voice approximation during ordinary-controller benchmark; not a fidelity comparison.')
    (out/'audio-capture.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('core','rom','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(json.dumps(capture(a.core,a.rom,a.out),indent=2))
