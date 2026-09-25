#!/usr/bin/env python3
"""Build an original, minimal SPC700 DSP-command receiver and procedural waves.

Experimental preview: four NES-like voices, not cycle-accurate NES APU emulation.
No external sound driver, samples or commercial bytes are embedded in this file.
"""
from __future__ import annotations
import struct
from pathlib import Path

CPU_NTSC = 1789773
ENTRY, DIRECTORY, SAMPLES = 0x0400, 0x0800, 0x0900

class Spc:
    def __init__(self): self.code=bytearray(); self.labels={}; self.fixups=[]
    def emit(self,*b): self.code.extend(b)
    def store(self,addr,value): self.emit(0x8F,value,addr) # MOV dp,#imm
    def label(self,name):
        if name in self.labels: raise ValueError('Duplicate SPC label')
        self.labels[name]=len(self.code)
    def branch(self,op,name):
        self.emit(op,0); self.fixups.append((len(self.code)-1,name))
    def finish(self):
        for off,name in self.fixups:
            delta=self.labels[name]-off-1
            if not -128<=delta<=127: raise ValueError('SPC branch out of range')
            self.code[off]=delta&255
        return bytes(self.code)

def brr_wave(samples:list[int])->bytes:
    if len(samples)!=32 or any(not -8<=x<=7 for x in samples):
        raise ValueError('Expected 32 signed nibble samples')
    result=bytearray()
    for start in (0,16):
        result.append(0xA3 if start else 0xA0) # range 10, filter 0, final end+loop
        for i in range(start,start+16,2): result.append(((samples[i]&15)<<4)|(samples[i+1]&15))
    return bytes(result)

def program()->bytes:
    s=Spc(); s.emit(0x20,0xCD,0xEF,0xBD) # CLRP; MOV X,#EF; MOV SP,X
    s.emit(0xE4,0xF4,0xC4,0x20) # remember the upload-launch token
    def dsp(reg,value): s.store(0xF2,reg);s.store(0xF3,value)
    dsp(0x6C,0xE0);dsp(0x5C,0xFF);dsp(0x4C,0)
    for reg in (0x4D,0x2D,0x2C,0x3C,0x0D,0x7D):dsp(reg,0)
    dsp(0x0C,100);dsp(0x1C,100);dsp(0x5D,DIRECTORY>>8)
    for voice in range(8):
        b=voice*16
        for reg,value in ((0,0),(1,0),(2,0),(3,0x10),(4,4 if voice==2 else 0),(5,0),(6,0),(7,0x7F)):
            dsp(b+reg,value)
    dsp(0x3D,8);dsp(0x6C,0x3F);dsp(0x5C,0);dsp(0x4C,15)
    s.store(0xF4,0x7F) # explicit ready marker, not just the IPL transfer echo
    s.label('wait');s.emit(0xE4,0x20,0x64,0xF4);s.branch(0xF0,'wait')
    s.emit(0xE4,0xF5,0xC4,0xF2,0xE4,0xF6,0xC4,0xF3)
    s.emit(0xE4,0xF4,0xC4,0x20,0xC4,0xF4);s.branch(0x2F,'wait')
    code=s.finish()
    if ENTRY+len(code)>DIRECTORY:raise ValueError('SPC code overlaps directory')
    image=bytearray(SAMPLES-ENTRY);image[:len(code)]=code
    waves=[brr_wave([7]*n+[-7]*(32-n)) for n in (4,8,16,24)]
    waves.append(brr_wave(list(range(-8,8))+list(range(7,-9,-1))))
    for index,wave in enumerate(waves):
        address=ENTRY+len(image)
        struct.pack_into('<HH',image,DIRECTORY-ENTRY+4*index,address,address)
        image.extend(wave)
    return bytes(image)

def pitch(timer:int,triangle:bool=False)->int:
    if not 0<=timer<=2047:raise ValueError('APU timer outside 11-bit range')
    divider=32 if triangle else 16
    return min(0x3FFF,round(CPU_NTSC/(divider*(timer+1))*32*4096/32000))

def write_assets(out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    image=program();(out/'audio-spc.bin').write_bytes(image)
    for name,triangle in [('pulse-pitch',False),('triangle-pitch',True)]:
        (out/(name+'.bin')).write_bytes(struct.pack('<2048H',*(pitch(t,triangle) for t in range(2048))))
    return {'program_bytes':len(image),'entry':ENTRY,'directory':DIRECTORY,'procedural_wave_count':5,
            'scope':'Approximate 2 pulse + triangle + noise preview; no envelopes, lengths, sweep, DMC or expansion audio.'}
