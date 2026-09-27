#!/usr/bin/env python3
"""Run dependent native execution against the original NES event-stream test.

Only boot state, original program and authored request times are execution
inputs. NO expected per-instruction state, handler result or cycle capture is
fed into the SNES sequencer. This is a composed prototype, not game scheduling.
"""
from pathlib import Path
import argparse
import ctypes as C
import hashlib
import json
import struct
import subprocess
import sys
from libretro_runner import Runner
from route_evidence import atomic_json
from timeline_fixture import cases,create_nes,expected_initial
from timeline_program import create_native,validate_events,generate,validate_plan,memory_bytes

class Event(C.Structure):
    _fields_=[('cycle',C.c_uint32),('irq',C.c_uint8),('nmi',C.c_uint8),('reserved',C.c_uint8*2)]


def sample_nes(core: Path,folder: Path,plan: dict,probe: bool) -> dict:
    size=32+memory_bytes(plan)
    rom=create_nes(folder,plan);r=Runner(core,rom)
    try:
        if probe:
            lib=r.lib
            lib.retro_n2s_timeline_configure.argtypes=[C.c_uint,C.c_uint,C.POINTER(Event),C.c_uint];lib.retro_n2s_timeline_configure.restype=C.c_int
            lib.retro_n2s_timeline_status.argtypes=[C.c_uint];lib.retro_n2s_timeline_status.restype=C.c_uint
            lib.retro_n2s_timeline_data.argtypes=[];lib.retro_n2s_timeline_data.restype=C.c_void_p
            if lib.retro_n2s_timeline_status(2)!=size or lib.retro_n2s_timeline_status(5)!=8:raise RuntimeError('Timeline harness ABI mismatch')
            events=(Event*len(plan['events']))(*[Event(e['cycle'],e['irq'],e['nmi'],(C.c_uint8*2)(0,0)) for e in validate_events(plan['events'])])
            if not lib.retro_n2s_timeline_configure(plan['origin'],plan['steps'],events,len(events)):raise RuntimeError('Timeline harness refused configuration')
        r.run(1)
        report=dict(name=plan['name'],ram_sha256=hashlib.sha256(r.memory()).hexdigest(),image_sha256=hashlib.sha256(r.rgb().tobytes()).hexdigest(),video_callbacks=r.frames,audio_frames=r.audio_frames)
        if probe:
            if lib.retro_n2s_timeline_status(1) or lib.retro_n2s_timeline_status(3):raise RuntimeError('Incomplete or erroneous reference timeline')
            count=lib.retro_n2s_timeline_status(0)
            if count!=plan['steps']+1:raise RuntimeError('Missing reference steps')
            raw=C.string_at(lib.retro_n2s_timeline_data(),count*size)
            report['records']=[raw[i*size:(i+1)*size].hex() for i in range(count)]
        report['complete']=True
        atomic_json(folder/'capture.json',report);return report
    finally:r.close()


def sample_native(core: Path,rom: Path,out: Path,steps: int, *, ram_bytes: int=512) -> dict:
    if type(ram_bytes) is not int or ram_bytes not in (512,2048) or type(steps) is not int or not 1<=steps<=65536//(32+ram_bytes):
        raise ValueError('Capture shape exceeds native output bank')
    size=32+ram_bytes
    r=Runner(core,rom)
    try:
        # Completion is marker-based, not a guessed one-frame runtime allowance.
        for _ in range(240):
            r.run(1);ram=r.memory()
            if ram[0x1FFF] in (0x5A,0xEE):break
        if ram[0x1FFF]!=0x5A:
            atomic_json(out,dict(passed=False,marker=ram[0x1FFF],status=ram[0x18CE],completed_steps=int.from_bytes(ram[0x18D0:0x18D2],'little'),pc=ram[0x18C4:0x18C6].hex()))
            raise RuntimeError('Native timeline fault or missing completion')
        report=dict(complete=True,marker=0x5A,status=0,completed_steps=steps,records=[ram[0x10000+size*i:0x10000+size*(i+1)].hex() for i in range(steps)],host_frames=r.frames)
        atomic_json(out,report);return report
    finally:r.close()


def compare(plan: dict,original: dict,native: dict) -> dict:
    validate_plan(plan)
    if any(type(native.get(k)) is not int for k in ('marker','status','completed_steps')) or any(r.get('fault') is not None for r in (original,native)):
        raise ValueError('Malformed or fault-bearing execution report')
    if original.get('complete') is not True or native.get('complete') is not True or native.get('marker')!=0x5A or native.get('status')!=0 or native.get('completed_steps')!=plan['steps']:
        raise ValueError('Failed or incomplete execution cannot pass')
    if original.get('name')!=plan['name']:raise ValueError('Reference plan identity mismatch')
    expected=original.get('records');actual=native.get('records')
    if not isinstance(expected,list) or len(expected)!=plan['steps']+1 or not isinstance(actual,list) or len(actual)!=plan['steps']:raise ValueError('Incomplete dependent instruction stream')
    if bytes.fromhex(expected[0])!=expected_initial(plan):raise ValueError('Original boot state differs from declared test inputs')
    entries={'irq':0,'nmi':0};ops={};latest=0;crossings=0
    for i,(a,b) in enumerate(zip(expected[1:],actual),1):
        one,two=bytes.fromhex(a),bytes.fromhex(b)
        if len(one)!=32+memory_bytes(plan) or len(two)!=32+memory_bytes(plan):raise ValueError('Malformed timeline row')
        if one!=two:
            mismatch=[j for j,(x,y) in enumerate(zip(one,two)) if x!=y]
            raise RuntimeError(f"{plan['name']} step {i}: {len(mismatch)} differences; offsets {mismatch[:16]}; expected header {one[:32].hex()}, actual {two[:32].hex()}")
        if plan.get('memory_model')=='mmc5-prg-rom':
            pc=int.from_bytes(one[4:6],'little')
            if any(v>=plan['prg_banks'] for v in one[20:25]) or pc<0x8000 or one[24]!=one[20+((pc-0x8000)//8192)]:
                raise ValueError('Invalid physical mapper or execution-bank capture')
        now=int.from_bytes(one[:4],'little')
        if int.from_bytes(one[18:20],'little')!=i or now!=latest+one[14]+one[15] or any(one[25 if plan.get('memory_model')=='mmc5-prg-rom' else 20:32]):raise ValueError('Nonclosing or unordered timeline record')
        if one[16] not in (0,1,2) or one[15]!=(7 if one[16] else 0):raise ValueError('Invalid interrupt cost/decision')
        if one[13]!=sum(e['cycle']<=now-one[15] for e in plan['events']):raise ValueError('Event cursor does not match the declared instruction-boundary policy')
        if one[17] in (0x10,0x30,0x50,0x70,0x90,0xB0,0xD0,0xF0) and one[14]==4:crossings+=1
        if one[16]:entries['irq' if one[16]==1 else 'nmi']+=1
        latest=now;ops[f'{one[17]:02x}']=ops.get(f'{one[17]:02x}',0)+1
    if one[13]!=len(plan['events']):raise ValueError('The test stopped before exercising every declared event')
    return dict(name=plan['name'],steps=plan['steps'],cycles=latest,entries=entries,branch_page_crossings=crossings,executed_opcodes=ops,record_bytes=plan['steps']*(32+memory_bytes(plan)),passed=True)



def compare_rebased(plan: dict,original: dict,native: dict,epoch: int) -> dict:
    """Exact declared clock-origin change; no state-byte or cycle tolerances."""
    if type(epoch) is not int or not 0<=epoch<=0xFFFF0000 or plan['events']:
        raise ValueError('Rebase test requires a bounded epoch and no external requests')
    import copy
    rebased=copy.deepcopy(native)
    for i,text in enumerate(native.get('records',[])):
        row=bytearray.fromhex(text)
        if len(row)!=32+memory_bytes(plan):raise ValueError('Malformed rebased record')
        now=int.from_bytes(row[:4],'little')
        if now<epoch:raise ValueError('Native clock wrapped or lost its epoch')
        row[:4]=(now-epoch).to_bytes(4,'little');rebased['records'][i]=row.hex()
    result=compare(plan,original,rebased)
    return dict(epoch=epoch,steps=result['steps'],passed=True)


def run_one(core: Path,folder: Path,plan: dict,*,retirement: str|None=None,program_text: str|None=None) -> dict:
    rom=create_native(folder,plan,expected_initial(plan),retirement=retirement,program_text=program_text)
    subprocess.run([sys.executable,__file__,'--sample','native','--core',str(core),'--rom',str(rom),'--steps',str(plan['steps']),'--ram-bytes',str(memory_bytes(plan)),'--out',str(folder/'capture.json')],check=True,timeout=60,stdout=subprocess.DEVNULL)
    return json.loads((folder/'capture.json').read_text())


def verify(plain: Path,probe: Path,snes: Path,out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True);summary=out/'timeline-verification.json';summary.unlink(missing_ok=True)
    plan=cases();atomic_json(out/'plan.json',plan)
    rows=[];inert=0
    for case in plan:
        name=case['name'];print('Checking',name,flush=True)
        folder=out/name;folder.mkdir(exist_ok=True);atomic_json(folder/'plan.json',case)
        subprocess.run([sys.executable,__file__,'--sample','probe','--core',str(probe),'--plan',str(folder/'plan.json'),'--out',str(folder/'nes')],check=True,timeout=30,stdout=subprocess.DEVNULL)
        reference=json.loads((folder/'nes/capture.json').read_text())
        if not case['events']:
            subprocess.run([sys.executable,__file__,'--sample','plain','--core',str(plain),'--plan',str(folder/'plan.json'),'--out',str(folder/'plain')],check=True,timeout=30,stdout=subprocess.DEVNULL)
            check=json.loads((folder/'plain/capture.json').read_text())
            if check!={k:v for k,v in reference.items() if k!='records'}:raise RuntimeError('No-request harness changed original execution')
            inert+=1
        candidate=run_one(snes,folder/'snes',case);rows.append(compare(case,reference,candidate))
        atomic_json(out/'progress.json',dict(complete=False,results=rows))
    controls=[];case=plan[4];reference=json.loads((out/case['name']/'nes/capture.json').read_text())
    base=(Path(__file__).resolve().parents[1]/'snes/src/guest_timeline.inc').read_text()
    mutants={'lost-entry-cost':base.replace('    lda GI+9\n    sta GT+21','    lda #0\n    sta GT+21'),
             'one-shot-events':base.replace('    bra event_loop','    jmp enter_boundary')}
    for name,text in mutants.items():
        if text==base:raise RuntimeError('Mutation did not change source')
        actual=run_one(snes,out/('wrong-'+name),case,retirement=text)
        try:compare(case,reference,actual)
        except (RuntimeError,ValueError):controls.append(dict(name=name,rejected=True))
        else:raise RuntimeError('Deliberately broken timeline passed')
    # Real native fault gates, not merely report-file mutation.
    case=plan[0];text=generate(bytes.fromhex(case['code']),case['origin'],case['starts'])
    bad_pc=text.replace(f'    lda #${case["origin"]+1:04X}\n    sta GT+4', '    lda #$9000\n    sta GT+4',1)
    clock=text.replace(f'ins_{case["origin"]:04x}:', f'ins_{case["origin"]:04x}:\n    lda #$FFFF\n    sta GT+2\n    lda #$FFF3\n    sta GT',1)
    rebased_checks=[]
    reference=json.loads((out/case['name']/'nes/capture.json').read_text())
    for epoch in (0xFFF0,0x12FFF0):
        code=text.replace(f'ins_{case["origin"]:04x}:', f'ins_{case["origin"]:04x}:\n    lda #${epoch>>16:04X}\n    sta GT+2\n    lda #${epoch&65535:04X}\n    sta GT',1)
        actual=run_one(snes,out/f'epoch-{epoch:08x}',case,program_text=code)
        rebased_checks.append(compare_rebased(case,reference,actual,epoch))
    fault_guards=[]
    for name,code,status,ordinal in [('unknown-pc',bad_pc,0xE1,1),('clock-overflow',clock,4,0)]:
        folder=out/('guard-'+name)
        try:run_one(snes,folder,case,program_text=code)
        except subprocess.CalledProcessError:
            failure=json.loads((folder/'capture.json').read_text())
            if failure.get('marker')!=0xEE or failure.get('status')!=status or failure.get('completed_steps')!=ordinal:
                raise RuntimeError('Native guard did not stop at the expected boundary')
            fault_guards.append(dict(name=name,rejected=True,**failure))
        else:raise RuntimeError('Unsafe timeline input completed instead of faulting')
    result=dict(passed=True,programs=len(rows),dependent_boundaries=sum(r['steps'] for r in rows),
                compared_state_bytes=sum(r['record_bytes'] for r in rows),
                guest_ram_bytes=sum(r['steps'] for r in rows)*512,
                inert_plain_comparisons=inert,negative_controls=controls,fault_guards=fault_guards,
                clock_epoch_checks=rebased_checks,rebased_boundaries=sum(r["steps"] for r in rebased_checks),
                branch_page_crossings=sum(r['branch_page_crossings'] for r in rows),
                irq_entries=sum(r['entries']['irq'] for r in rows),nmi_entries=sum(r['entries']['nmi'] for r in rows),
                cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('nes_plain',plain),('nes_stimulus',probe),('snes',snes)]},
                results=rows,production_scheduler_changed=False,physical_polling_verified=False,
                scope='Dependent execution of authored RAM/control programs with one boot input and after-instruction request policy. Not hardware pin timing, bus stalls, mapper/PPU scheduling, private gameplay, or a speed improvement.')
    atomic_json(summary,result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=['plain','probe','native']);p.add_argument('--steps',type=int);p.add_argument('--ram-bytes',type=int,choices=(512,2048),default=512)
    for k in ('core','rom','plan','out','nes-plain','nes-probe','snes-core'):p.add_argument('--'+k,type=Path)
    a=p.parse_args()
    if a.sample=='native':sample_native(a.core,a.rom,a.out,a.steps,ram_bytes=a.ram_bytes)
    elif a.sample:sample_nes(a.core,a.out,json.loads(a.plan.read_text()),a.sample=='probe')
    else:print(json.dumps(verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve()),indent=2))
