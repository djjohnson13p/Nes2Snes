#!/usr/bin/env python3
"""Unmodified NES final endpoints for blanked OAM/palette/mapper state.

Native records compare host/no-host execution only. This is not a per-instruction
NES timing oracle. Raw NST states and refused original-program prefixes are kept.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import palette_timeline
from oam_ports import create_nes, create_native, underlying, OAM_ADDRESS, ADDRESS_REGISTER
from oam_ports_fixture import cases, address_case, interleave_case, guard_cases
from oam_state import nestopia_oam
from timeline_fixture import expected_initial
from verify_ppu_blank import exact_hex
from verify_palette_timeline import capture as palette_capture, native_sample, compare as palette_compare, check_host
from verify_palette_controls import compare_guard as palette_guard
from verify_nametable_palette import compare_extra
from mmc5_timeline import reassemble
from route_evidence import atomic_json

EXTRA = {'oam':256, 'oam_address':1}
ENDPOINT_BYTES = 5173 + sum(EXTRA.values())


def initial(plan):
    return expected_initial(palette_timeline.underlying(underlying(plan)))


def capture(kind, core, rom, out, steps=31, host=False, stop_pc=None):
    out.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'nes':
        result=palette_capture(kind,core,rom,out,stop_pc=stop_pc)
        raw,addr,latch=nestopia_oam(out.with_suffix('.nst').read_bytes())
        if latch != bytes.fromhex(result['ppu_state'])[-1]:
            raise ValueError('OAM and palette parsers disagree on shared latch')
        # The pinned core stores already-masked OAM attributes. Compare raw bytes;
        # do not clear bits in a CPU result or tolerate a malformed snapshot.
        if any(raw[i]&0x1C for i in range(2,256,4)):
            raise ValueError('Unexpected physical OAM attribute bits')
        result.update(oam=raw.hex(),oam_address=bytes((addr,)).hex())
        atomic_json(out,result)
        return result
    if kind!='native':raise ValueError('Unknown capture platform')
    cmd=[sys.executable,__file__,'--sample','--core',str(core),'--rom',str(rom),
         '--out',str(out),'--steps',str(steps)]
    if host:cmd.append('--host')
    subprocess.run(cmd,check=True,timeout=90,stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def compare_oam(reference,actual):
    for key,size in EXTRA.items():
        a=exact_hex(reference.get(key),size,'reference '+key)
        b=exact_hex(actual.get(key),size,'native '+key)
        if a!=b:raise RuntimeError('Independent '+key+' differs')
    memory=bytes.fromhex(actual['oam'])
    if any(memory[i]&0x1C for i in range(2,256,4)):
        raise ValueError('Native attribute storage contains absent bits')
    count=actual.get('completed_steps')
    if type(count) is not int or not 1<=count<=31:raise ValueError('Invalid OAM endpoint count')
    retired=exact_hex(actual['ppu_records'][count-1],16,'retired OAM address')
    if retired[13:14]!=bytes.fromhex(actual['oam_address']):
        raise ValueError('Final OAM address differs from retired record')


def compare(plan,reference,actual):
    result=palette_compare(plan,reference,actual)
    compare_extra(reference,actual);compare_oam(reference,actual)
    result['independent_endpoint_bytes']=ENDPOINT_BYTES
    return result


def run_case(nes,snes,out,plan):
    folder=out/plan['name']
    reference=capture('nes',nes,create_nes(folder/'nes',plan),folder/'nes/capture.json')
    rows=[];baseline=None;nmis=0
    for mode in (None,'free'):
        d=folder/('native' if mode is None else 'host')
        rom=create_native(d,plan,initial(plan),**({'host_mode':mode} if mode else {}))
        actual=capture('native',snes,rom,d/'capture.json',steps=plan['steps'],host=bool(mode))
        rows.append(compare(plan,reference,actual))
        if mode:nmis=check_host(baseline,actual,mode)
        else:baseline=actual
    return rows,nmis


def run(nes,snes,out,limit=None,jobs=2):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Require 1..4 case workers')
    plans=cases()
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(plans):raise ValueError('Invalid smoke limit')
        plans=plans[:limit]
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'oam-ports-verification.json';summary.unlink(missing_ok=True)
    atomic_json(out/'plans.json',plans);done={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        pending={pool.submit(run_case,nes,snes,out,p):i for i,p in enumerate(plans)}
        for f in as_completed(pending):
            i=pending[f];done[i]=f.result()
            print('OAM',len(done),'/',len(plans),plans[i]['name'],flush=True)
            atomic_json(out/'progress.json',dict(complete=False,programs=len(done)))
    rows=[];nmis=0
    for i in range(len(plans)):
        pair,count=done[i];rows.extend(pair);nmis+=count
    report=dict(passed=True,complete_matrix=limit is None,programs=len(plans),scenarios=len(rows),
                independent_endpoint_bytes=sum(r['independent_endpoint_bytes'] for r in rows),
                endpoint_bytes=ENDPOINT_BYTES,host_interrupts=nmis,results=rows,
                cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nestopia',nes),('snes',snes)]},
                scope='Stable blanked original-program endpoints, including raw OAM and address. Native records establish host noninterference only. No DMA, rendering, OAM decay, revision quirks, NES cycle sampling or commercial gameplay.')
    atomic_json(summary,report);return report


def controls(nes,snes,out,fce=None):
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'oam-ports-controls.json';summary.unlink(missing_ok=True)
    hosts=[];mutants=[];guards=[]
    for plan in (address_case(255,0xE7,True),interleave_case('chr'),interleave_case('palette')):
        d=out/plan['name'];ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
        base=capture('native',snes,create_native(d/'native',plan,initial(plan)),d/'native/capture.json')
        compare(plan,ref,base)
        for mode in ('cost','time','capture','nested'):
            rom=create_native(d/mode,plan,initial(plan),host_mode=mode)
            actual=capture('native',snes,rom,d/mode/'capture.json',host=True)
            compare(plan,ref,actual)
            hosts.append(dict(name=plan['name'],mode=mode,host_interrupts=check_host(base,actual,mode)))
    for name,plan,old,new in (
        ('attribute-mask',address_case(2,0xFF),'    and #$E3','    nop\n    nop'),
        ('read-increment',address_case(255,0xE7), '    lda f:$7E5900,x\n    sta PV+9',
         '    lda f:$7E5900,x\n    inc OA\n    sta PV+9'),
        ('write-latch',address_case(2,0xFF),'    lda GT+6\n    sta PV+9\n    txa',
         '    lda GT+6\n    and #$E3\n    sta PV+9\n    txa')):
        d=out/('mutant-'+name);ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
        create_native(d/'native',plan,initial(plan));path=d/'native/oam_ports.inc';text=path.read_text()
        if text.count(old)!=1:raise ValueError('Nonunique OAM mutation anchor')
        path.write_text(text.replace(old,new))
        actual=capture('native',snes,reassemble(d/'native'),d/'native/capture.json')
        if actual['complete'] is not True or actual['status'] or actual['completed_steps']!=plan['steps']:
            raise RuntimeError('Mutant crashed instead of producing a wrong endpoint')
        try:compare(plan,ref,actual)
        except (ValueError,RuntimeError) as exc:mutants.append(dict(name=name,rejected=True,completed=True,reason=str(exc)))
        else:raise RuntimeError('Broken OAM implementation passed')
    for plan,stop,retired in guard_cases():
        d=out/plan['name'];rom=create_nes(d/'nes-prefix',plan);raw=bytearray(rom.read_bytes())
        pos=16+(plan['prg_banks']-1)*8192+(stop&8191)
        raw[pos:pos+3]=bytes((0x4C,stop&255,stop>>8));rom.write_bytes(raw)
        ref=capture('nes',nes,rom,d/'nes-prefix/capture.json',stop_pc=stop)
        actual=capture('native',snes,create_native(d/'native',plan,initial(plan)),d/'native/capture.json')
        row=palette_guard(plan,ref,actual,stop,retired)
        compare_extra(ref,actual);compare_oam(ref,actual)
        row['independent_prefix_bytes']=ENDPOINT_BYTES;guards.append(row)
    diagnostic=None
    if fce is not None:
        plan=address_case(2,0xFF);d=out/'alternate-reference';rom=create_nes(d,plan)
        reference=capture('nes',nes,rom,d/'nestopia.json')
        subprocess.run([sys.executable,str(Path(__file__).with_name('verify_palette_controls.py')),
            '--fce-sample','--nes-core',str(fce),'--rom',str(rom),'--out',str(d/'fceumm.json')],
            check=True,timeout=90,stdout=subprocess.DEVNULL)
        alternate=json.loads((d/'fceumm.json').read_text())
        a=exact_hex(reference['cpu_ram'],2048,'primary diagnostic RAM')
        b=exact_hex(alternate['cpu_ram'],2048,'alternate diagnostic RAM')
        differences=[dict(address=i,nestopia=x,fceumm=y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        diagnostic=dict(agreement=not differences,excluded_from_acceptance_totals=True,
                        differences=differences,core_sha256=alternate['core_sha256'])
    report=dict(passed=True,targeted_host_scenarios=len(hosts),host_interrupts=sum(r['host_interrupts'] for r in hosts),
                host_results=hosts,negative_controls=mutants,guards=guards,alternate_reference=diagnostic,per_instruction_nes_equivalence_claimed=False)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample',action='store_true');p.add_argument('--host',action='store_true')
    p.add_argument('--steps',type=int,default=31);p.add_argument('--controls',action='store_true')
    p.add_argument('--limit',type=int);p.add_argument('--jobs',type=int,default=2)
    for key in ('core','rom','nes-core','snes-core','fce-core','out'):p.add_argument('--'+key,type=Path)
    a=p.parse_args()
    if a.sample:
        native_sample(a.core,a.rom,a.out,a.steps,a.host,
                      extra_ranges={'oam':(OAM_ADDRESS,256),'oam_address':(ADDRESS_REGISTER,1)})
    elif a.controls:print(json.dumps(controls(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.fce_core.resolve() if a.fce_core else None),indent=2))
    else:print(json.dumps(run(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.limit,a.jobs),indent=2))
