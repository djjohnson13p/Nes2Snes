#!/usr/bin/env python3
"""Record executed PRG locations, hardware accesses and MMC5 register values.

Requires FCEUmm built with instrument_fceumm.py. Coverage is only the scripted
session (intro/title/name entry/opening/early stage one), not the whole game.
Generated dumps may contain original game data: keep the output directory private.
"""
from __future__ import annotations
import argparse
import ctypes as C
import json
from pathlib import Path
import struct
from libretro_runner import Runner
from rom import Rom

NAMES={0:'counts.u32',1:'cpu-address.u16',2:'io-flags.u8',3:'io-min.u16',4:'io-max.u16',
       5:'io-read-counts.u32',6:'io-write-counts.u32',7:'mmc5-values.bits',
       8:'palette.bin',9:'nametables.bin',10:'bg-chr.bin',11:'spr-chr.bin',12:'oam.bin',13:'ppu.bin'}

def run_trace(core:Path, rom_path:Path, out:Path):
    out.mkdir(parents=True,exist_ok=True)
    rom=Rom.read(rom_path)
    if rom.mapper != 5:raise ValueError('This probe snapshot implementation is MMC5-specific.')
    r=Runner(core,rom_path)
    r.lib.retro_n2s_size.argtypes=[C.c_uint];r.lib.retro_n2s_size.restype=C.c_size_t
    r.lib.retro_n2s_data.argtypes=[C.c_uint];r.lib.retro_n2s_data.restype=C.c_void_p
    script=[]
    def step(frames,buttons=(),label=None):
        script.append({'frames':frames,'buttons':list(buttons),'label':label})
        r.run(frames,buttons)
        if label:
            r.save_png(out/(label+'.png'))
            (out/(label+'-ram.bin')).write_bytes(r.memory())
    try:
        step(120)
        for i in range(5):
            step(1,('start',));step(150,label=f'start-{i+1}')
        # Fifth Start pauses CV3 after the opening. Sixth resumes it.
        step(1,('start',));step(30,label='stage-one')
        for i in range(10):
            step(90,('right','b'),label=f'run-{i+1}')
            step(1);step(30,('right','a','b'));step(1)
        arrays={}
        for kind,name in NAMES.items():
            size=r.lib.retro_n2s_size(kind);ptr=r.lib.retro_n2s_data(kind)
            if not ptr and size:raise RuntimeError(f'Probe data {kind} missing.')
            data=C.string_at(ptr,size) if size else b''
            arrays[kind]=data;(out/name).write_bytes(data)
        counts=struct.unpack('<'+'I'*(len(arrays[0])//4),arrays[0])
        pcs=struct.unpack('<'+'H'*(len(arrays[1])//2),arrays[1])
        lows=struct.unpack('<'+'H'*(len(arrays[3])//2),arrays[3])
        highs=struct.unpack('<'+'H'*(len(arrays[4])//2),arrays[4])
        reads=struct.unpack('<16384I',arrays[5]);writes=struct.unpack('<16384I',arrays[6])
        register_values={}
        for address in range(0x5000,0x5207):
            bits=arrays[7][(address-0x5000)*32:(address-0x5000+1)*32]
            values=[v for v in range(256) if bits[v>>3] & (1 << (v&7))]
            if values:register_values[f'${address:04X}']=[f'${v:02X}' for v in values]
        io_sites=[{'prg_offset':f'{i:06X}','file_offset':f'{rom.prg_offset+i:06X}',
                   'cpu_address':f'${pcs[i]:04X}','opcode':f'{rom.prg[i]:02X}',
                   'read':bool(flag&1),'write':bool(flag&2),'min_address':f'${lows[i]:04X}',
                   'max_address':f'${highs[i]:04X}','execution_count':counts[i]}
                  for i,flag in enumerate(arrays[2]) if flag]
        summary={'rom_sha256':rom.metadata()['sha256'],'frames':r.frames,
                 'script':script,'observed_instruction_entry_points':sum(c>0 for c in counts),
                 'observed_instruction_executions':sum(counts),
                 'prg_bytes':len(rom.prg),'coverage_is_complete':False,
                 'scope':'Scripted intro/title/name-entry/opening and early stage-one input only.',
                 'bank_instruction_entry_points':[sum(c>0 for c in counts[i:i+8192])
                                                   for i in range(0,len(counts),8192)],
                 'io_sites':io_sites,'mmc5_written_values':register_values,
                 'io_register_counts':{f'${i+0x2000:04X}':{'reads':a,'writes':b}
                                       for i,(a,b) in enumerate(zip(reads,writes)) if a or b}}
        (out/'trace-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        r.save_png(out/'final-frame.png')
        return summary
    finally:r.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True);p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    s=run_trace(args.core,args.rom,args.out)
    print(json.dumps({k:v for k,v in s.items() if k not in ('script','io_sites','io_register_counts')},indent=2))
if __name__=='__main__':main()
