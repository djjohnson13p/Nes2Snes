#!/usr/bin/env python3
"""Compare explicit sweep events with an unmodified FCEUmm state oracle.

The authored NES fixture runs no NMI. Closely spaced $4017 five-step resets
supply explicit clocks; NOPs exceed the hardware write delay. Sweep is disabled
before entering an idle loop. Parse the NES core's documented tagged FCS save
state, not a patched emulator API. This checks event semantics, not cycle timing.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, subprocess, sys
from pathlib import Path
from native_fixture import Program, write_program
from build_native import build
from libretro_runner import Runner

CASES = [
    (1000, 0x89, 1, None), (1000, 0x89, 2, None),
    (500, 0x81, 1, None), (500, 0x81, 4, None),
    (0x600, 0x01, 3, None), (0x400, 0x80, 3, None),
    (0x700, 0x88, 3, None), (7, 0x89, 2, None),
    (8, 0x89, 1, None), (0x7ff, 0x81, 4, None),
    (1000, 0xa9, 4, ('reload', 0xa9)),
    (1000, 0x89, 1, ('low', 0x23)),
    (1000, 0x89, 1, ('high', 0x0a)),
    *[(600, 0x87 | (d<<4), d+2, None) for d in range(8)],
    *[(900, 0x88 | s, 3, None) for s in range(1,8)],
]

def fcs_periods(data: bytes) -> list[int]:
    if data[:3] != b'FCS' or len(data)<16:
        raise ValueError('Unrecognized FCEUmm save state')
    fields={}; offset=16
    while offset+5<=len(data):
        kind=data[offset]; size=int.from_bytes(data[offset+1:offset+5],'little')
        offset+=5
        if size>len(data)-offset:
            raise ValueError('Truncated FCS section')
        end=offset+size
        if kind==5:  # FCEU sound state section; individually tagged entries
            pos=offset
            while pos+8<=end:
                tag=data[pos:pos+4]; n=int.from_bytes(data[pos+4:pos+8],'little')&0x7fffffff
                pos+=8
                if n>end-pos:raise ValueError('Truncated sound state entry')
                if tag in (b'CRF1',b'CRF2'):
                    if tag in fields or n!=4:raise ValueError('Unexpected pulse-state layout')
                    fields[tag]=int.from_bytes(data[pos:pos+n],'little',signed=True)
                pos+=n
        offset=end
    if set(fields)!={b'CRF1',b'CRF2'}:raise ValueError('Missing pulse state in independent oracle')
    return [fields[b'CRF1'],fields[b'CRF2']]

def fixture(out:Path,index:int,c0:bool)->dict:
    period,control,clocks,after=CASES[index]
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    def write(a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
    setup=[(0x2000,0),(0x2001,0),(0x4017,0x40),(0x5100,2),
           (0x5115,0x9e if c0 else 0x80),(0x5116,0x87 if c0 else 0x9e),
           (0x4015,3),(0x4000,0xbf),(0x4004,0xbf)]
    for a,v in setup:write(a,v)
    for c in (0,1):
        for reg,v in ((1,control),(2,period&255),(3,8|(period>>8))):write(0x4000+c*4+reg,v)
    for clock in range(clocks):
        write(0x4017,0xc0)
        for _ in range(16):p.op('NOP')
        if after and clock==0:
            kind,v=after;reg={'reload':1,'low':2,'high':3}[kind]
            for c in (0,1):write(0x4000+c*4+reg,v)
    # Stop pitch updates without changing the timer. Halting length is already set.
    for c in (0,1):write(0x4001+c*4,control&0x7f)
    write(0x4017,0x40);p.op('LDA','imm',0x5a);p.op('STA','zp',0x7e)
    p.label('done');p.op('JMP','abs','done');p.label('nmi');p.op('RTI')
    meta=write_program(out,p);meta.update(period=period,control=control,clocks=clocks,after=after)
    return meta

def one(nes_core:Path,snes_core:Path,out:Path,index:int,mode:str)->dict:
    meta=fixture(out,index,mode=='c0')
    build(out/'fixture.nes',out,out/'snes',experimental_audio=True,audio_counters=True,audio_sweep=True,
          direct=mode!='generic',quick_io=mode!='generic')
    observed=[]
    for platform,core,rom in [('nes',nes_core,out/'fixture.nes'),('snes',snes_core,out/'snes/native-prototype.sfc')]:
        r=Runner(core,rom)
        try:
            for _ in range(300):
                r.run(1);m=r.memory()
                if platform=='snes' and m[0x90f]:raise RuntimeError('Guest execution fault')
                if m[0x7e]==0x5a:break
            else:raise RuntimeError('Oracle fixture did not finish')
            if platform=='nes':values=fcs_periods(r.state())
            else:values=[int.from_bytes(m[0xaf2+c*4:0xaf4+c*4],'little') for c in (0,1)]
            observed.append(values)
        finally:r.close()
    if observed[0]!=observed[1]:raise AssertionError(dict(case=index,mode=mode,nes=observed[0],snes=observed[1],input=meta))
    report=dict(passed=True,case=index,mode=mode,nes_periods=observed[0],snes_periods=observed[1],
                input={k:meta[k] for k in ('period','control','clocks','after')})
    (out/'oracle.json').write_text(json.dumps(report,indent=2)+'\n');return report

def verify(nes_core:Path,snes_core:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True);rows=[]
    for mode,indices in [('direct',range(len(CASES))),('generic',range(13)),('c0',range(13))]:
        for index in indices:
            folder=out/f'{mode}-{index:02d}';folder.mkdir(exist_ok=True)
            # Fresh process for each libretro session pair avoids leftover globals.
            cmd=[sys.executable,__file__,'--nes-core',str(nes_core.resolve()),'--snes-core',str(snes_core.resolve()),
                 '--out',str(folder),'--case',str(index),'--mode',mode]
            with (folder/'run.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
            rows.append(json.loads((folder/'oracle.json').read_text()))
        print(f'Passed {mode}: {len(indices)} cases',flush=True)
    result=dict(passed=True,cases=len(rows),period_values_checked=2*len(rows),records=rows,
                nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
                snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
                scope='Explicit sweep events versus unmodified FCEUmm periods; not cycle-accurate sound equivalence.')
    (out/'sweep-oracle.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('nes-core','snes-core','out'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--case',type=int);p.add_argument('--mode',choices=['direct','generic','c0'],default='direct');a=p.parse_args()
    result=verify(a.nes_core,a.snes_core,a.out) if a.case is None else one(a.nes_core,a.snes_core,a.out,a.case,a.mode)
    print(json.dumps(result,indent=2))
