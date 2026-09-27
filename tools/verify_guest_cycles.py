#!/usr/bin/env python3
"""Independent NES durations versus Python and native SNES cycle accounting.

The observed NES core measures before/after actual instruction dispatch. Its
unmodified counterpart must reproduce all outputs. Native inputs contain only
pre-instruction state, never measured cycles or expected results.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from guest_cycles import Instruction, metadata
from opcodes6502 import OPS
from guest_cycle_fixture import cases, create_nes, create_native
from libretro_runner import Runner
from route_evidence import atomic_json


class CycleRecord(C.Structure):
    _fields_=[('start',C.c_uint64),('end',C.c_uint64),('pc',C.c_uint16),
              ('operand',C.c_uint16),('pointer',C.c_uint16),('next_pc',C.c_uint16),
              ('opcode',C.c_uint8),('p',C.c_uint8),('x',C.c_uint8),('y',C.c_uint8),
              ('a',C.c_uint8),('s',C.c_uint8),('valid',C.c_uint8),('reserved',C.c_uint8)]


class CycleObserver:
    def __init__(self, lib, pcs: list[int], capacity: int=1048576):
        if not isinstance(pcs,list) or not 1<=len(pcs)<=32766 or len(set(pcs))!=len(pcs) or any(type(pc) is not int or not 0x8000<=pc<=0xFFFD for pc in pcs):
            raise ValueError('Require unique bounded cartridge instruction addresses')
        if type(capacity) is not int or not 1<=capacity<=1048576:raise ValueError('Invalid capture capacity')
        self.lib=lib
        lib.retro_n2s_cycle_configure.argtypes=[C.POINTER(C.c_uint16),C.c_uint32,C.c_uint32]
        lib.retro_n2s_cycle_configure.restype=C.c_int
        lib.retro_n2s_cycle_status.argtypes=[C.c_uint];lib.retro_n2s_cycle_status.restype=C.c_uint32
        lib.retro_n2s_cycle_data.argtypes=[];lib.retro_n2s_cycle_data.restype=C.POINTER(CycleRecord)
        lib.retro_n2s_cycle_disable.argtypes=[];lib.retro_n2s_cycle_disable.restype=None
        if C.sizeof(CycleRecord)!=32 or lib.retro_n2s_cycle_status(2)!=32:raise RuntimeError('Cycle observer ABI mismatch')
        values=(C.c_uint16*len(pcs))(*pcs)
        if not lib.retro_n2s_cycle_configure(values,len(pcs),capacity):raise RuntimeError('Cycle observer configuration refused')

    def finish(self) -> list[dict]:
        self.lib.retro_n2s_cycle_disable()
        n=self.lib.retro_n2s_cycle_status(0)
        if self.lib.retro_n2s_cycle_status(1) or self.lib.retro_n2s_cycle_status(3):raise RuntimeError('Cycle observer incomplete or overflowing')
        if not n:raise RuntimeError('Empty cycle observation')
        data=self.lib.retro_n2s_cycle_data();out=[];previous=0
        if not data:raise RuntimeError('Missing cycle observation')
        for i in range(n):
            row={k:int(getattr(data[i],k)) for k,_ in CycleRecord._fields_}
            if row['valid']!=1 or row['end']<=row['start'] or row['start']<previous:raise RuntimeError('Invalid cycle record ordering or validity')
            previous=row['end'];out.append(row)
        return out


def instruction(row: dict) -> Instruction:
    if row['opcode'] not in OPS:raise ValueError('Unknown observed opcode')
    size=OPS[row['opcode']][2]
    operand=row['operand'] if size==3 else row['operand']&255 if size==2 else 0
    return Instruction(row['opcode'],row['pc'],operand,row['p'],row['x'],row['y'],row['pointer'])


def sample_nes(core: Path, out: Path, observed: bool, rows: list[dict]) -> None:
    results=[]
    for case in rows:
        rom=create_nes(out/case['name'],case);r=Runner(core,rom)
        try:
            observer=CycleObserver(r.lib,[case['pc']],8) if observed else None
            r.run(1)
            ram=r.memory()
            if ram[0x7E]!=0x5A:raise RuntimeError(f"{case['name']}: fixture did not finish")
            row=dict(name=case['name'],ram_sha256=hashlib.sha256(ram).hexdigest(),
                     image_sha256=hashlib.sha256(r.rgb().tobytes()).hexdigest(),
                     video_callbacks=r.frames,audio_frames=r.audio_frames)
            if observer:row['observed']=observer.finish()
            results.append(row)
        finally:r.close()
    atomic_json(out/'capture.json',dict(results=results))


def sample_native(core: Path, rom: Path, out: Path, count: int) -> None:
    r=Runner(core,rom)
    try:
        r.run(3);ram=r.memory()
        if ram[0x7E]!=0x5A:raise RuntimeError('Native fixture did not finish')
        atomic_json(out,dict(records=[ram[0x4000+26*i:0x4000+26*(i+1)].hex() for i in range(count)]))
    finally:r.close()


def check_nes(plain: dict, observed: dict, plan: list[dict]) -> list[dict]:
    if len(plain.get('results',[]))!=len(plan) or len(observed.get('results',[]))!=len(plan):raise RuntimeError('Missing independent capture rows')
    result=[]
    for wanted,a,b in zip(plan,plain['results'],observed['results']):
        if a['name']!=wanted['name'] or {k:v for k,v in b.items() if k!='observed'}!=a:raise RuntimeError('Observer changed outputs or capture order')
        observations=b.get('observed',[])
        if len(observations)!=1:raise RuntimeError('Each isolated opcode must execute exactly once')
        row=observations[0]
        if row['pc']!=wanted['pc'] or row['opcode']!=wanted['opcode']:raise RuntimeError('Different instruction was measured')
        cpu=instruction(row);measured=row['end']-row['start'];predicted=cpu.cost()
        if measured!=predicted:raise RuntimeError(f"{a['name']}: actual {measured} cycles != modeled {predicted}; possible external timing, not accepted")
        result.append(dict(name=a['name'],instruction={k:getattr(cpu,k) for k in Instruction.__dataclass_fields__},measured_cycles=measured))
    return result


def check_native(inputs: list[bytes], costs: list[int], capture: dict, statuses: list[int]|None=None) -> None:
    records=capture.get('records',[])
    if len(records)!=len(inputs) or len(costs)!=len(inputs):raise RuntimeError('Incomplete native output')
    statuses=statuses or [0]*len(inputs)
    if len(statuses)!=len(inputs):raise ValueError('Status length mismatch')
    for i,(original,cost,status,text) in enumerate(zip(inputs,costs,statuses,records)):
        output=bytes.fromhex(text)
        if len(output)!=26 or output[:11]!=original[:11] or output[13]!=original[13] or output[11:13]!=bytes((cost,status)):
            raise RuntimeError(f'Native state/cycle/status mismatch at record {i}')
        flag=(0x4D,0x6F,0x5D,0xFD)[i%4]
        x=0x78 if flag&0x10 else 0x5678;y=0xCD if flag&0x10 else 0xABCD
        expected=(0x1234).to_bytes(2,'little')+x.to_bytes(2,'little')+y.to_bytes(2,'little')+bytes.fromhex('55037e')+bytes((flag,))+bytes.fromhex('f01f')
        if output[14:]!=expected:raise RuntimeError(f'Native caller context changed at record {i}')


def native_run(core: Path, folder: Path, inputs: list[bytes], *, kernel: str|None=None, table: str|None=None) -> dict:
    rom=create_native(folder,inputs,kernel=kernel,table=table)
    subprocess.run([sys.executable,__file__,'--sample','native','--core',str(core),'--rom',str(rom),'--count',str(len(inputs)),'--out',str(folder/'capture.json')],check=True,timeout=30,stdout=subprocess.DEVNULL)
    return json.loads((folder/'capture.json').read_text())


def verify(nes_plain: Path,nes_observed: Path,snes: Path,out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True);plan=cases();atomic_json(out/'plan.json',plan)
    for role,core in [('plain',nes_plain),('observed',nes_observed)]:
        subprocess.run([sys.executable,__file__,'--sample',role,'--core',str(core),'--plan',str(out/'plan.json'),'--out',str(out/role)],check=True,timeout=240,stdout=subprocess.DEVNULL)
    plain=json.loads((out/'plain/capture.json').read_text());observed=json.loads((out/'observed/capture.json').read_text())
    measured=check_nes(plain,observed,plan)
    for start in range(0,len(measured),64):
        batch=measured[start:start+64];inputs=[Instruction(**r['instruction']).record() for r in batch]
        output=native_run(snes,out/f'native-{start:03d}',inputs)
        check_native(inputs,[r['measured_cycles'] for r in batch],output)
    # Every unofficial opcode must fail; actual native execution, not model mocks.
    invalid=[]
    for op in range(256):
        if op not in OPS:invalid.append(bytes((op,))+bytes(13))
    for start in range(0,len(invalid),64):
        batch=invalid[start:start+64];check_native(batch,[0]*len(batch),native_run(snes,out/f'unknown-{start:03d}',batch),[1]*len(batch))
    missing=[]
    for op in OPS:
        if metadata(op)[1]==3:
            row=bytearray(Instruction(op,0x8100,0xFF,pointer=0x200).record());row[10]=0;missing.append(bytes(row))
    check_native(missing,[0]*len(missing),native_run(snes,out/'missing-pointers',missing),[2]*len(missing))
    # Execute deliberately bad components against independently measured rows.
    test=next(r for r in measured if r['instruction']['opcode']==0xBD and r['measured_cycles']==5)
    inp=[Instruction(**test['instruction']).record()];kernel=(Path(__file__).resolve().parents[1]/'snes/src/guest_cycles.inc').read_text()
    mutants={'crossing':kernel.replace('crossing:\n    bcc done\n    inc GC_COST','crossing:\n    bcc done\n    nop'),
             'fixed-cost':kernel.replace('    sta GC_COST\n    lda f:GuestCycleAdjust,x','    dec a\n    sta GC_COST\n    lda f:GuestCycleAdjust,x')}
    controls=[]
    for name,bad in mutants.items():
        output=native_run(snes,out/('mutated-'+name),inp,kernel=bad)
        try:check_native(inp,[test['measured_cycles']],output)
        except RuntimeError:controls.append(dict(name=name,rejected=True))
        else:raise RuntimeError('Mutated native cost unexpectedly passed')
    result=dict(passed=True,official_opcodes=len({r['instruction']['opcode'] for r in measured}),
                independently_measured_cases=len(measured),native_output_bytes=len(measured)*14,
                caller_context_bytes=len(measured)*12,unknown_opcodes_rejected=len(invalid),
                missing_pointer_cases=len(missing),negative_controls=controls,
                cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nes_plain',nes_plain),('nes_observed',nes_observed),('snes',snes)]},
                source_runtime_changed=False,scheduling_installed=False,results=measured,
                scope='Documented NES instruction execution costs only. Independent FCEUmm measurements and same-platform noninterference; not DMA/DMC/interrupt elapsed timing, actual interrupt polling, gameplay or runtime speed.')
    atomic_json(out/'guest-cycle-verification.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=['plain','observed','native'])
    p.add_argument('--count',type=int)
    for name in ('core','rom','out','plan','nes-plain','nes-observed','snes-core'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.sample=='native':sample_native(a.core,a.rom,a.out,a.count)
    elif a.sample:sample_nes(a.core,a.out,a.sample=='observed',json.loads(a.plan.read_text()))
    else:
        result=verify(a.nes_plain.resolve(),a.nes_observed.resolve(),a.snes_core.resolve(),a.out.resolve())
        print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
