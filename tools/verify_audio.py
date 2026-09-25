#!/usr/bin/env python3
"""Execute original tone fixture and measure independent SNES core PCM output.

This checks DSP output, mute behavior, pitch and the bounded mailbox. It is not a
comparison against the NES APU's complete envelopes, counters or audio waveform.
"""
from __future__ import annotations
import argparse,ctypes as C,hashlib,json,wave
from pathlib import Path
import numpy as np
from libretro_runner import Runner
from audio_program import pitch
class Geometry(C.Structure):
    _fields_=[('base_width',C.c_uint),('base_height',C.c_uint),('max_width',C.c_uint),('max_height',C.c_uint),('aspect_ratio',C.c_float)]
class Timing(C.Structure):_fields_=[('fps',C.c_double),('sample_rate',C.c_double)]
class AVInfo(C.Structure):_fields_=[('geometry',Geometry),('timing',Timing)]
class AudioRunner(Runner):
    def __init__(self,*a,**kw):self.chunks=[];super().__init__(*a,**kw)
    def audio_batch(self,data,count):
        if data and count:self.chunks.append(C.string_at(data,count*4))
        return super().audio_batch(data,count)
    def audio_info(self):
        info=AVInfo();self.lib.retro_get_system_av_info.argtypes=[C.POINTER(AVInfo)]
        self.lib.retro_get_system_av_info(C.byref(info));return info

def verify(core:Path,rom:Path,fixture:Path,out:Path,expect_silent:bool=False)->dict:
    out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((fixture/'audio-fixture.json').read_text())
    r=AudioRunner(core,rom);segments={x['name']:[] for x in meta['audio_segments']}
    allpcm=[]
    try:
        info=r.audio_info(); previous=0
        for host in range(1800):
            r.chunks.clear();r.run(1);m=r.memory();data=b''.join(r.chunks);allpcm.append(data)
            if m[0x90f]:raise RuntimeError('Bridge fault: '+m[0x90c:0x910].hex())
            # The fixture's own NMI counter supplies the tone schedule.
            frame=m[0x40]
            for seg in meta['audio_segments']:
                if seg['first']<=previous<=seg['last']:segments[seg['name']].append(data)
            previous=frame
            if frame>=237:break
        else:raise RuntimeError('Audio fixture did not progress')
        checks=[]
        for seg in meta['audio_segments']:
            pcm=np.frombuffer(b''.join(segments[seg['name']]),dtype='<i2').reshape(-1,2).astype(np.float64)
            if len(pcm)<2048:raise AssertionError('Insufficient audio samples')
            mono=pcm.mean(axis=1);rms=float(np.sqrt(np.mean(mono*mono)))
            result=dict(name=seg['name'],samples=len(pcm),rms=rms,peak=int(np.max(np.abs(pcm))))
            if expect_silent or seg['name']=='silence':
                if rms>1:raise AssertionError(f'Expected silence: {result}')
            else:
                if rms<20:raise AssertionError(f'Missing voice output: {result}')
                if seg['timer'] is not None:
                    spectrum=np.abs(np.fft.rfft((mono-mono.mean())*np.hanning(len(mono))))
                    freqs=np.fft.rfftfreq(len(mono),1/info.timing.sample_rate)
                    dominant=float(freqs[int(spectrum[1:].argmax())+1])
                    expected=32000*pitch(seg['timer'],seg['triangle'])/(4096*32)
                    result.update(frequency_hz=dominant,expected_hz=expected)
                    if abs(dominant-expected)>max(5,expected*.02):raise AssertionError(f'Unexpected pitch: {result}')
                else:
                    result['zero_crossings']=int(np.count_nonzero(np.diff(np.signbit(mono))))
                    if result['zero_crossings']<100:raise AssertionError('Noise output lacks transitions')
            checks.append(result)
        if not expect_silent and (m[0xa80]!=1 or m[0xa82]):raise AssertionError('SPC mailbox failed')
        with wave.open(str(out/'fixture.wav'),'wb') as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(round(info.timing.sample_rate));w.writeframes(b''.join(allpcm))
        result=dict(pass_=True,scope='Four original procedural tones and mute; not full NES APU equivalence.',
                    rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    sample_rate=info.timing.sample_rate,host_frames=r.frames,spc_ready=m[0xa80],spc_fault=m[0xa82],
                    dsp_commands=int.from_bytes(m[0xa84:0xa86],'little'),expect_silent=expect_silent,segments=checks)
        (out/'audio-verification.json').write_text(json.dumps(result,indent=2)+'\n');return result
    finally:r.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('core','rom','fixture','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--expect-silent',action='store_true');a=p.parse_args()
    print(json.dumps(verify(a.core,a.rom,a.fixture,a.out,a.expect_silent),indent=2))
