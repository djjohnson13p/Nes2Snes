#!/usr/bin/env python3
"""Actual NES boundary entry versus native SNES entry, with complete stack checks.

The test core asserts external requests at an authored instruction completion.
Its original interrupt-dispatch implementation supplies results. This is a test
of ALREADY SAMPLED requests, not line transitions on arbitrary physical cycles.
Inert (no-request) probes must also reproduce the unmodified core's full output.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from interrupt_boundary import Boundary, SUPPORTED, enter
from interrupt_fixture import cases, nes_fixture, native_fixture
from libretro_runner import Runner
from route_evidence import atomic_json


class Observation(C.Structure):
    _fields_=[('boundary_time',C.c_uint64),('next_time',C.c_uint64),
              ('pc',C.c_uint16),('next_pc',C.c_uint16)]+[(name,C.c_uint8) for name in
              ('before_p','after_p','next_p','s','next_s','a','x','y','next_a','next_x','next_y','complete')]+[
              ('before_stack',C.c_uint8*256),('after_stack',C.c_uint8*256)]


def configure(lib, row):
    lib.retro_n2s_interrupt_configure.argtypes=[C.c_uint]*4
    lib.retro_n2s_interrupt_configure.restype=C.c_int
    lib.retro_n2s_interrupt_status.argtypes=[C.c_uint];lib.retro_n2s_interrupt_status.restype=C.c_uint
    lib.retro_n2s_interrupt_data.argtypes=[];lib.retro_n2s_interrupt_data.restype=C.POINTER(Observation)
    if C.sizeof(Observation)!=544 or lib.retro_n2s_interrupt_status(2)!=544:
        raise RuntimeError('Interrupt harness ABI mismatch')
    if not lib.retro_n2s_interrupt_configure(row['pc'],row['opcode'],int(row['irq']),int(row['nmi'])):
        raise RuntimeError('Interrupt harness refused configuration')


def sample_nes(core: Path, out: Path, plan: list[dict], observed: bool):
    results=[]
    for row in plan:
        rom=nes_fixture(out/row['name'],row);r=Runner(core,rom)
        try:
            if observed:configure(r.lib,row)
            r.run(1);ram=r.memory()
            if ram[0x7E]!=0x5A:raise RuntimeError(f"{row['name']}: fixture did not complete")
            result=dict(name=row['name'],ram_sha256=hashlib.sha256(ram).hexdigest(),
                        image_sha256=hashlib.sha256(r.rgb().tobytes()).hexdigest(),
                        video_callbacks=r.frames,audio_frames=r.audio_frames)
            if observed:
                if r.lib.retro_n2s_interrupt_status(0)!=3 or r.lib.retro_n2s_interrupt_status(1):
                    raise RuntimeError('Incomplete or invalid interrupt observation')
                obs=r.lib.retro_n2s_interrupt_data().contents
                result['observation']={key:(bytes(getattr(obs,key)).hex() if key.endswith('_stack') else int(getattr(obs,key))) for key,_ in Observation._fields_}
            results.append(result)
        finally:r.close()
    atomic_json(out/'capture.json',dict(results=results))


def expected(row: dict, capture: dict) -> tuple[bytes,bytes,bytes,bytes]:
    """Prepare native input only from the pre-interrupt capture and fixture plan."""
    obs=capture['observation']
    if not isinstance(obs,dict) or set(obs)!={k for k,_ in Observation._fields_}:
        raise RuntimeError('Malformed independent boundary record')
    for key,ctype in Observation._fields_:
        if key.endswith('_stack'):
            try:
                valid=isinstance(obs[key],str) and len(bytes.fromhex(obs[key]))==256
            except ValueError:
                valid=False
        else:
            valid=type(obs[key]) is int and 0<=obs[key]<(1 << (8*C.sizeof(ctype)))
        if not valid:
            raise RuntimeError('Malformed independent boundary field: '+key)
    if type(obs['complete']) is not int or obs['complete']!=1:
        raise RuntimeError('Incomplete boundary observation')
    boundary=Boundary(row['opcode'],obs['before_p'],obs['after_p'],row['irq'],row['nmi'],
                      obs['s'],obs['pc'],0xE200,0xE300)
    initial=boundary.record();stack=bytes.fromhex(obs['before_stack'])
    # Independent outputs come from NES dispatch, NOT from the Python model.
    if obs['next_pc']==0xE300:kind=2
    elif obs['next_pc']==0xE200:kind=1
    elif obs['next_pc']==obs['pc']:kind=0
    else:raise RuntimeError('Unexpected target at the next instruction boundary')
    elapsed=obs['next_time']-obs['boundary_time']
    if elapsed!=(7 if kind else 0):raise RuntimeError('Unexplained interrupt elapsed time')
    if any(obs['next_'+key]!=obs[key] for key in ('a','x','y')):
        raise RuntimeError('Original interrupt changed A/X/Y before handler code')
    result=bytearray(initial)
    result[2]=obs['next_p'];result[5]=obs['next_s'];result[6:8]=obs['next_pc'].to_bytes(2,'little')
    result[8:10]=bytes((kind,elapsed))
    if kind==2:result[4]=0
    after_stack=bytes.fromhex(obs['after_stack'])
    modeled=enter(boundary,stack)
    if modeled!=(bytes(result),after_stack):raise RuntimeError(f"{row['name']}: model differs from original NES entry")
    return initial,stack,bytes(result),after_stack


def sample_native(core: Path, rom: Path, out: Path, count: int):
    r=Runner(core,rom)
    try:
        for _ in range(60):
            r.run(1)
            if r.memory()[0x7E] == 0x5A:
                break
        ram=r.memory()
        if ram[0x7E]!=0x5A:raise RuntimeError('Native interrupt fixture did not complete')
        atomic_json(out,dict(records=[ram[0x4000+284*i:0x4000+284*(i+1)].hex() for i in range(count)]))
    finally:r.close()


def check_native(values: list[tuple[bytes,bytes]], capture: dict):
    if len(capture.get('records',[]))!=len(values):raise RuntimeError('Missing native interrupt records')
    for i,((descriptor,stack),text) in enumerate(zip(values,capture['records'])):
        out=bytes.fromhex(text)
        if len(out)!=284 or out[:16]!=descriptor or out[16:272]!=stack:
            raise RuntimeError(f'Native interrupt state or stack mismatch at {i}')
        flags=(0x4D,0x6F,0x5D,0xFD)[i%4]
        x=0x78 if flags&0x10 else 0x5678;y=0xCD if flags&0x10 else 0xABCD
        context=(0x1234).to_bytes(2,'little')+x.to_bytes(2,'little')+y.to_bytes(2,'little')+bytes.fromhex('55037e')+bytes((flags,))+bytes.fromhex('f01f')
        if out[272:]!=context:raise RuntimeError(f'Native caller context mismatch at {i}')


def native_run(core: Path, out: Path, inputs: list[tuple[bytes,bytes]], kernel=None):
    rom=native_fixture(out,inputs,kernel)
    subprocess.run([sys.executable,__file__,'--sample','native','--core',str(core),'--rom',str(rom),
                    '--count',str(len(inputs)),'--out',str(out/'capture.json')],check=True,timeout=30,stdout=subprocess.DEVNULL)
    return json.loads((out/'capture.json').read_text())


def verify(plain: Path, probe: Path, snes: Path, out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    (out/'interrupt-boundary-verification.json').unlink(missing_ok=True)
    plan=cases();atomic_json(out/'plan.json',plan)
    no_request=[r for r in plan if not r['irq'] and not r['nmi']]
    atomic_json(out/'inert-plan.json',no_request)
    for role,core,selection in [('observed',probe,'plan.json'),('plain',plain,'inert-plan.json')]:
        subprocess.run([sys.executable,__file__,'--sample',role,'--core',str(core),'--out',str(out/role),
                        '--plan',str(out/selection)],check=True,timeout=240,stdout=subprocess.DEVNULL)
    captured=json.loads((out/'observed/capture.json').read_text())['results']
    inert=json.loads((out/'plain/capture.json').read_text())['results']
    if len(captured)!=len(plan) or len(inert)!=len(no_request):raise RuntimeError('Incomplete independent fixture matrix')
    inert_by_name={r['name']:r for r in inert};values=[];counts={0:0,1:0,2:0}
    for row,result in zip(plan,captured):
        if row['name']!=result['name']:raise RuntimeError('Wrong capture ordering')
        if row['name'] in inert_by_name and {k:v for k,v in result.items() if k!='observation'}!=inert_by_name[row['name']]:
            raise RuntimeError('Inert observer changed original NES outputs')
        value=expected(row,result);values.append(value);counts[value[2][8]]+=1
    for offset in range(0,len(values),64):
        batch=values[offset:offset+64]
        got=native_run(snes,out/f'native-{offset:04d}',[(a,b) for a,b,c,d in batch])
        check_native([(c,d) for a,b,c,d in batch],got)
    invalid=[]
    for opcode in set(range(256))-SUPPORTED:
        original=bytearray(Boundary(0xEA,0x30,0x30,True,True,0,0xABCD,0xE200,0xE300).record())
        original[0]=opcode;result=bytearray(original);result[10]=1
        invalid.append((bytes(original),bytes(range(256)),bytes(result),bytes(range(256))))
    for field,value in ((3,2),(3,255),(4,2),(4,255),(11,1),(11,255)):
        original=bytearray(Boundary(0xEA,0x30,0x30,True,True,0,0xABCD,0xE200,0xE300).record())
        original[field]=value;result=bytearray(original);result[10]=2
        invalid.append((bytes(original),bytes(range(256)),bytes(result),bytes(range(256))))
    for offset in range(0,len(invalid),64):
        batch=invalid[offset:offset+64]
        check_native([(c,d) for a,b,c,d in batch],native_run(snes,out/f'invalid-{offset:04d}',[(a,b) for a,b,c,d in batch]))
    # Actual executable negative controls: wrong IRQ-mask selection and stack B bit.
    base=(Path(__file__).resolve().parents[1]/'snes/src/guest_interrupt.inc').read_text()
    mutant_specs=[('wrong-delayed-I',base.replace('old_i:\n    lda GI+1','old_i:\n    lda GI+2'),
                   next(i for i,r in enumerate(plan) if r['opcode']==0x58 and r['irq'] and not r['nmi'] and captured[i]['observation']['before_p']&4)),
                  ('wrong-stack-B',base.replace('ora #$20','ora #$30'),next(i for i,v in enumerate(values) if v[2][8]))]
    controls=[]
    for name,kernel,index in mutant_specs:
        a,b,c,d=values[index];got=native_run(snes,out/name,[(a,b)],kernel)
        try:check_native([(c,d)],got)
        except RuntimeError:controls.append(dict(name=name,rejected=True))
        else:raise RuntimeError('Mutated native interrupt entry passed')
    report=dict(passed=True,completed_opcodes=len({r['opcode'] for r in plan}),valid_calls=len(values),
                descriptor_bytes=len(values)*16,stack_bytes=len(values)*256,caller_context_bytes=len(values)*12,
                decisions={('none','irq','nmi')[k]:v for k,v in counts.items()},
                initial_stack_positions=256,inert_plain_core_checks=len(inert),invalid_calls=len(invalid),
                negative_controls=controls,cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in
                    [('plain_nes',plain),('request_test_nes',probe),('snes',snes)]},
                production_runtime_changed=False,physical_polling_verified=False,scheduling_installed=False,
                scope='Already-sampled requests at completed instruction boundaries. Actual pinned NES dispatch versus native entry; not subcycle pin sampling, branch polling, interrupt hijack, DMA/DMC, live game scheduling or speed.')
    atomic_json(out/'interrupt-boundary-verification.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=['plain','observed','native']);p.add_argument('--count',type=int)
    for k in ('core','rom','out','plan','nes-plain','nes-probe','snes-core'):p.add_argument('--'+k,type=Path)
    a=p.parse_args()
    if a.sample=='native':sample_native(a.core,a.rom,a.out,a.count)
    elif a.sample:sample_nes(a.core,a.out,json.loads(a.plan.read_text()),a.sample=='observed')
    else:print(json.dumps(verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve()),indent=2))
