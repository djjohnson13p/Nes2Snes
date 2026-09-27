#!/usr/bin/env python3
"""Unmodified Nestopia endpoints for forced-blank, fixed-size CHR set switching.

Actual mapper/OAM state is read from raw serialized NES state. Native instruction
records compare host/non-host execution only, not NES instruction or pin timing.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from libretro_runner import Runner
from chr_sets import create_nes, create_native, initial, B_ADDRESS
from chr_sets_fixture import cases, switching, interleave, guard_cases
from chr_sets_state import decode_sets, native_registers
from palette_state import decode as decode_ppu
from verify_oam_ports import compare as compare_oam, compare_oam as compare_oam_fields
from verify_nametable_palette import compare_extra
from verify_palette_timeline import native_sample, check_host as previous_host
from verify_palette_controls import compare_guard as previous_guard
from verify_ppu_blank import exact_hex
from mmc5_timeline import reassemble
from route_evidence import atomic_json

ENDPOINT_BYTES = 5430 + 27


def nes_sample(core, rom, out, stop=None):
    if stop is not None and (type(stop) is not int or not 0x8000<=stop<=65535):
        raise ValueError('Invalid original prefix PC')
    r=Runner(core,rom)
    try:
        for _ in range(120):
            r.run(1)
            if stop is None:
                if r.memory()[0x7E]==0x5A:break
            elif int.from_bytes(bytes.fromhex(decode_ppu(r.state(), sprite_16=True)['cpu_registers'])[:2],'little')==stop:
                break
        else:raise RuntimeError('Original CHR-set program did not complete')
        raw=r.state();out.with_suffix('.nst').write_bytes(raw);state=decode_sets(raw)
        if bytes.fromhex(state['cpu_ram'])!=r.memory()[:2048]:raise RuntimeError('NST/RAM disagreement')
        state.update(core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                     rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),frames=r.frames)
        atomic_json(out,state)
    finally:r.close()


def capture(kind, core, rom, out, steps=31, host=False, stop=None):
    out.parent.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,__file__,'--sample',kind,'--core',str(core),'--rom',str(rom),
         '--out',str(out),'--steps',str(steps)]
    if host:cmd.append('--host')
    if stop is not None:cmd+=['--stop',str(stop)]
    subprocess.run(cmd,check=True,timeout=90,stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def compare_registers(reference, actual):
    a=exact_hex(reference.get('chr_set_registers'),27,'reference CHR registers')
    b=native_registers(actual)
    if a!=b:raise RuntimeError('Independent A/B register endpoint differs')


def compare(plan, reference, actual):
    result=compare_oam(plan,reference,actual)
    compare_registers(reference,actual)
    result['independent_endpoint_bytes']=ENDPOINT_BYTES
    return result


def check_host(base, actual, mode):
    count=previous_host(base,actual,mode)
    for key,size in (('chr_set_b',9),('oam',256),('oam_address',1)):
        if exact_hex(base.get(key),size,key)!=exact_hex(actual.get(key),size,key):
            raise RuntimeError('Host changed '+key)
    return count


def run_case(nes,snes,out,plan):
    d=out/plan['name'];ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
    rows=[];base=None;count=0
    for mode in (None,'free'):
        dest=d/('native' if mode is None else 'host')
        rom=create_native(dest,plan,initial(plan),**({'host_mode':mode} if mode else {}))
        actual=capture('native',snes,rom,dest/'capture.json',plan['steps'],bool(mode))
        rows.append(compare(plan,ref,actual))
        if mode:count=check_host(base,actual,mode)
        else:base=actual
    return rows,count


def run(nes,snes,out,limit=None,jobs=2):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Require 1..4 workers')
    plans=cases()
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(plans):raise ValueError('Invalid smoke limit')
        plans=plans[:limit]
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'chr-sets-verification.json';summary.unlink(missing_ok=True)
    atomic_json(out/'plans.json',plans);done={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures={pool.submit(run_case,nes,snes,out,p):i for i,p in enumerate(plans)}
        for f in as_completed(futures):
            i=futures[f];done[i]=f.result()
            print('CHR sets',len(done),'/',len(plans),plans[i]['name'],flush=True)
            atomic_json(out/'progress.json',dict(complete=False,programs=len(done)))
    rows=[];count=0
    for i in range(len(plans)):
        pair,nmis=done[i];rows.extend(pair);count+=nmis
    report=dict(passed=True,complete_matrix=limit is None,programs=len(plans),scenarios=len(rows),
        independent_endpoint_bytes=sum(r['independent_endpoint_bytes'] for r in rows),endpoint_bytes=ENDPOINT_BYTES,
        host_interrupts=count,results=rows,cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nestopia',nes),('snes',snes)]},
        scope='Blanked 8x16, fixed-size A/B reads and independent stable register/memory endpoints. Native instruction records are host noninterference only. No rendering, live mode changes, DMA/DMC, physical timing or CV3 replay.')
    atomic_json(summary,report);return report


def controls(nes,snes,out):
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'chr-sets-controls.json';summary.unlink(missing_ok=True)
    hosts=[];mutants=[];guards=[]
    for p in (switching(3,5,'ab',0x59,3,1024),switching(0,7,'ba',0xFD,2,1024),interleave('palette')):
        d=out/p['name'];ref=capture('nes',nes,create_nes(d/'nes',p),d/'nes/capture.json')
        base=capture('native',snes,create_native(d/'native',p,initial(p)),d/'native/capture.json')
        compare(p,ref,base)
        for mode in ('cost','time','capture','nested'):
            actual=capture('native',snes,create_native(d/mode,p,initial(p),host_mode=mode),d/mode/'capture.json',host=True)
            compare(p,ref,actual);hosts.append(dict(name=p['name'],mode=mode,host_interrupts=check_host(base,actual,mode)))
    for name,p,old,new in (
        ('force-a',switching(3,5,'ba',0x59,3,1024),'    lda f:CS_LAST','    lda #0'),
        ('lost-high',switching(3,5,'ba',0x59,0,1024),'    lda f:CS_B,x','    lda f:CS_B,x\n    and #$00FF'),
        ('upper-half',switching(3,5,'ba',0x59,3,1024),'    and #3\n    asl a','    and #7\n    asl a')):
        d=out/('mutant-'+name);ref=capture('nes',nes,create_nes(d/'nes',p),d/'nes/capture.json')
        create_native(d/'native',p,initial(p));path=d/'native/chr_sets.inc';text=path.read_text()
        if text.count(old)!=1:raise ValueError('Nonunique CHR mutation')
        path.write_text(text.replace(old,new))
        actual=capture('native',snes,reassemble(d/'native'),d/'native/capture.json')
        if actual.get('complete') is not True or actual['status'] or actual['completed_steps']!=p['steps']:
            raise RuntimeError('Mutant did not finish normally')
        try:compare(p,ref,actual)
        except (ValueError,RuntimeError) as exc:mutants.append(dict(name=name,rejected=True,completed=True,reason=str(exc)))
        else:raise RuntimeError('Incorrect CHR mapping passed')
    for p,stop,retired in guard_cases():
        d=out/p['name'];rom=create_nes(d/'nes',p);raw=bytearray(rom.read_bytes())
        offset=16+(p['prg_banks']-1)*8192+(stop&8191)
        raw[offset:offset+3]=bytes((0x4C,stop&255,stop>>8));rom.write_bytes(raw)
        ref=capture('nes',nes,rom,d/'nes/capture.json',stop=stop)
        actual=capture('native',snes,create_native(d/'native',p,initial(p)),d/'native/capture.json')
        row=previous_guard(p,ref,actual,stop,retired)
        compare_extra(ref,actual);compare_oam_fields(ref,actual);compare_registers(ref,actual)
        row['independent_prefix_bytes']=ENDPOINT_BYTES;guards.append(row)
    report=dict(passed=True,targeted_host_scenarios=len(hosts),host_interrupts=sum(h['host_interrupts'] for h in hosts),
        host_results=hosts,negative_controls=mutants,guards=guards,per_instruction_nes_equivalence_claimed=False)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample',choices=('nes','native'));p.add_argument('--host',action='store_true')
    p.add_argument('--steps',type=int,default=31);p.add_argument('--stop',type=int)
    p.add_argument('--controls',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--jobs',type=int,default=2)
    for k in ('core','rom','nes-core','snes-core','out'):p.add_argument('--'+k,type=Path)
    a=p.parse_args()
    if a.sample=='nes':nes_sample(a.core,a.rom,a.out,a.stop)
    elif a.sample=='native':native_sample(a.core,a.rom,a.out,a.steps,a.host,
        extra_ranges={'oam':(0x5900,256),'oam_address':(0x1C3B,1),'chr_set_b':(B_ADDRESS,9)})
    elif a.controls:print(json.dumps(controls(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve()),indent=2))
    else:print(json.dumps(run(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.limit,a.jobs),indent=2))
