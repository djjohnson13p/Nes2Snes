#!/usr/bin/env python3
"""Extend observed CPU coverage with idle intro and adaptive first-stage play.

A coverage sample, not a claim to cover the whole game. Use the same authorized
ROM and pinned, instrumented emulator as the base trace.
"""
from pathlib import Path
import argparse, ctypes as C, json, struct, hashlib
from libretro_runner import Runner
from trace_rom import NAMES
from rom import Rom

def extend(core,rom_path,trace,idle=3600,play=3600):
    if idle<0 or play<0:raise ValueError('Frame counts must be nonnegative.')
    meta=json.loads((trace/'trace-summary.json').read_text())
    rom=Rom.read(rom_path)
    if meta['rom_sha256']!=rom.metadata()['sha256']:raise ValueError('ROM/trace mismatch')
    r=Runner(core,rom_path)
    r.lib.retro_n2s_size.argtypes=[C.c_uint];r.lib.retro_n2s_size.restype=C.c_size_t
    r.lib.retro_n2s_data.argtypes=[C.c_uint];r.lib.retro_n2s_data.restype=C.c_void_p
    try:
        r.run(idle)
        r.lib.retro_reset()
        r.run(120)
        for _ in range(10):
            if r.memory()[0x18]==4:break
            r.run(2,('start',));r.run(145)
        else:raise RuntimeError('Adaptive CV3 startup did not reach main state 4.')
        remaining=play
        pattern=((60,('right',)),(25,('right','a')),(25,('b',)),(10,()))
        while remaining:
            for count,buttons in pattern:
                step=min(count,remaining);r.run(step,buttons);remaining-=step
                if not remaining:break
        for kind in (0,1,2,3,4):
            name=NAMES[kind];old=(trace/name).read_bytes()
            n=r.lib.retro_n2s_size(kind);data=C.string_at(r.lib.retro_n2s_data(kind),n)
            if kind==0:
                aa=struct.unpack('<262144I',old);bb=struct.unpack('<262144I',data)
                merged=struct.pack('<262144I',*[min(a+b,0xffffffff) for a,b in zip(aa,bb)])
            elif kind==2:merged=bytes(a|b for a,b in zip(old,data))
            else:
                aa=struct.unpack('<262144H',old);bb=struct.unpack('<262144H',data)
                if kind==3:vv=[min(a,b) if a and b else a or b for a,b in zip(aa,bb)]
                elif kind==4:vv=[max(a,b) for a,b in zip(aa,bb)]
                else:
                    for a,b in zip(aa,bb):
                        if a and b and a!=b:raise ValueError('Same physical byte observed at multiple CPU addresses')
                    vv=[a or b for a,b in zip(aa,bb)]
                merged=struct.pack('<262144H',*vv)
            (trace/name).write_bytes(merged)
        (trace/'rgb-palette.bin').write_bytes(C.string_at(r.lib.retro_n2s_data(14),192))
        counts=struct.unpack('<262144I',(trace/NAMES[0]).read_bytes())
        meta['coverage_extensions']=meta.get('coverage_extensions',[])+[{'idle_frames':idle,'additional_play_frames':play,'total_emulator_frames':r.frames}]
        meta['observed_instruction_entry_points']=sum(c>0 for c in counts)
        meta['observed_instruction_executions']=sum(counts)
        meta['coverage_is_complete']=False
        # Base I/O summaries are retained as base-pass observations, not relabelled as totals.
        meta['io_summary_scope']='original base trace only; coverage arrays include extensions'
        (trace/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
        print(json.dumps({k:v for k,v in meta.items() if k in ('coverage_extensions','observed_instruction_entry_points','coverage_is_complete')},indent=2))
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--core',type=Path,required=True);p.add_argument('--rom',type=Path,required=True);p.add_argument('--trace',type=Path,required=True);p.add_argument('--idle',type=int,default=3600);p.add_argument('--play',type=int,default=3600);a=p.parse_args();extend(a.core,a.rom,a.trace,a.idle,a.play)
