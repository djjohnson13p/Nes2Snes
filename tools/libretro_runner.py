#!/usr/bin/env python3
"""Small headless libretro test frontend. Uses externally supplied emulator cores.

No core is bundled with the project. Keep each core/game session in its own
process; libretro libraries have process-global state. This is a test harness,
not an accuracy claim or a replacement for hardware testing.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys


class GameInfo(C.Structure):
    _fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
class Variable(C.Structure):
    _fields_=[('key',C.c_char_p),('value',C.c_char_p)]
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
BATCH=C.CFUNCTYPE(C.c_size_t,C.c_void_p,C.c_size_t)
POLL=C.CFUNCTYPE(None)
INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
BUTTONS={'b':0,'y':1,'select':2,'start':3,'up':4,'down':5,'left':6,'right':7,
         'a':8,'x':9,'l':10,'r':11}


class Runner:
    def __init__(self, core: Path, rom: Path, options: dict[str,str]|None=None):
        self.lib=C.CDLL(str(core.resolve()))
        self.format=0
        self.frame=None
        self.width=self.height=self.pitch=0
        self.buttons=0
        self.frames=0
        self.audio_frames=0
        self.variables={}
        self.overrides=options or {}
        self.directory=str(rom.resolve().parent).encode()
        self.errors=[]
        self.callbacks=(ENV(self.environment),VIDEO(self.video),AUDIO(lambda l,r:None),
                        BATCH(self.audio_batch),POLL(lambda:None),INPUT(self.input))
        setters=('retro_set_environment','retro_set_video_refresh','retro_set_audio_sample',
                 'retro_set_audio_sample_batch','retro_set_input_poll','retro_set_input_state')
        for name,cb in zip(setters,self.callbacks):
            f=getattr(self.lib,name);f.argtypes=[type(cb)];f.restype=None;f(cb)
        self.lib.retro_init.argtypes=[];self.lib.retro_init.restype=None
        self.lib.retro_run.argtypes=[];self.lib.retro_run.restype=None
        self.lib.retro_load_game.argtypes=[C.POINTER(GameInfo)]
        self.lib.retro_load_game.restype=C.c_bool
        self.lib.retro_get_memory_size.argtypes=[C.c_uint]
        self.lib.retro_get_memory_size.restype=C.c_size_t
        self.lib.retro_get_memory_data.argtypes=[C.c_uint]
        self.lib.retro_get_memory_data.restype=C.c_void_p
        self.lib.retro_serialize_size.argtypes=[]
        self.lib.retro_serialize_size.restype=C.c_size_t
        self.lib.retro_serialize.argtypes=[C.c_void_p,C.c_size_t]
        self.lib.retro_serialize.restype=C.c_bool
        self.lib.retro_set_controller_port_device.argtypes=[C.c_uint,C.c_uint]
        self.lib.retro_set_controller_port_device.restype=None
        self.lib.retro_init()
        raw=rom.read_bytes()
        self.rom_buffer=C.create_string_buffer(raw)
        self.game=GameInfo(str(rom.resolve()).encode(), C.cast(self.rom_buffer,C.c_void_p),len(raw),None)
        if not self.lib.retro_load_game(C.byref(self.game)):
            raise RuntimeError('Core rejected the ROM.')
        self.lib.retro_set_controller_port_device(0,1)
        self.closed=False

    def environment(self, cmd, data):
        try:
            if cmd == 3: # GET_CAN_DUPE
                C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
            if cmd in (9,30,31): # system/assets/save directory
                C.cast(data,C.POINTER(C.c_char_p))[0]=self.directory;return True
            if cmd == 10: # pixel format
                f=C.cast(data,C.POINTER(C.c_int))[0]
                if f not in (0,1,2):return False
                self.format=f;return True
            if cmd == 15: # GET_VARIABLE
                v=C.cast(data,C.POINTER(Variable)).contents
                if not v.key:return False
                value=self.overrides.get(v.key.decode(),self.variables.get(v.key.decode()))
                if value is None:return False
                if isinstance(value,str):value=value.encode()
                self.variables[v.key.decode()]=value # retain backing memory
                v.value=value;return True
            if cmd == 16: # SET_VARIABLES, legacy API accepted by both cores
                entries=C.cast(data,C.POINTER(Variable))
                for n in range(4096):
                    v=entries[n]
                    if not v.key:break
                    spec=(v.value or b'').decode()
                    if '; ' in spec:self.variables[v.key.decode()]=spec.split('; ',1)[1].split('|')[0].encode()
                return True
            if cmd == 17: # variables have not changed
                C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
            if cmd == 52: # core options version: use legacy variables
                C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
            if cmd == 51: # input bitmasks, no data argument
                return True
            if cmd == 59:
                C.cast(data,C.POINTER(C.c_uint))[0]=1;return True
            if cmd in (1,6,8,11,18,35,36,37,44):return True
            return False
        except Exception as exc:
            self.errors.append(f'environment({cmd}): {exc}');return False

    def video(self, data, width, height, pitch):
        if data and data != C.c_void_p(-1).value:
            self.width,self.height,self.pitch=width,height,pitch
            self.frame=C.string_at(data,pitch*height)
        self.frames+=1

    def audio_batch(self, data, count):
        self.audio_frames+=count;return count

    def input(self, port, device, index, button):
        if port or device != 1:return 0
        if button == 256:return self.buttons
        return int(bool(self.buttons & (1 << button))) if button < 16 else 0

    def run(self, frames: int, buttons: tuple[str,...]=()):
        if frames < 0:raise ValueError('Frame count cannot be negative.')
        self.buttons=sum(1<<BUTTONS[b.lower()] for b in set(buttons))
        for _ in range(frames):self.lib.retro_run()
        if self.errors:raise RuntimeError('; '.join(self.errors))

    def rgb(self):
        import numpy as np
        if self.frame is None:raise RuntimeError('Core has not supplied a video frame.')
        if self.format == 1:
            raw=np.frombuffer(self.frame,dtype='<u4').reshape(self.height,self.pitch//4)[:,:self.width]
            r=(raw>>16)&255;g=(raw>>8)&255;b=raw&255
        else:
            raw=np.frombuffer(self.frame,dtype='<u2').reshape(self.height,self.pitch//2)[:,:self.width].astype('uint32')
            if self.format == 2:
                r=((raw>>11)&31)*255//31;g=((raw>>5)&63)*255//63;b=(raw&31)*255//31
            else:
                r=((raw>>10)&31)*255//31;g=((raw>>5)&31)*255//31;b=(raw&31)*255//31
        return np.stack((r,g,b),axis=-1).astype('uint8')

    def save_png(self,path: Path):
        from PIL import Image
        path.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(self.rgb()).save(path)

    def memory(self,kind=2) -> bytes:
        size=self.lib.retro_get_memory_size(kind)
        ptr=self.lib.retro_get_memory_data(kind)
        return C.string_at(ptr,size) if ptr and size else b''

    def state(self) -> bytes:
        size=self.lib.retro_serialize_size()
        if not size:raise RuntimeError('Core does not offer a save state.')
        out=C.create_string_buffer(size)
        if not self.lib.retro_serialize(out,size):raise RuntimeError('Serialization failed.')
        return out.raw

    def close(self):
        if not self.closed:
            self.lib.retro_unload_game();self.lib.retro_deinit();self.closed=True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True);p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--frames',type=int,default=120);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    r=Runner(args.core,args.rom)
    try:
        r.run(args.frames);r.save_png(args.out)
        print(json.dumps({'frames':r.frames,'width':r.width,'height':r.height,'pixel_format':r.format,
                          'frame_sha256':hashlib.sha256(r.frame or b'').hexdigest(),'audio_frames':r.audio_frames},indent=2))
    finally:r.close()

if __name__=='__main__':main()
