#!/usr/bin/env python3
"""Independent endpoints for rewritten live CHR modes, with stale-read guards.

Mode/write provenance is a native admission policy, not NES hardware state.
Independent counts exclude policy bytes and any unresolved stale-read diagnostic.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from chr_mode_rewrite import create_nes, create_native, initial, POLICY_ADDRESS
from chr_mode_rewrite_fixture import cases, transition, interleave, guard_cases, seal
from chr_sets_state import native_registers as fixed_registers
from verify_chr_sets import nes_sample, check_host as fixed_host
from verify_oam_ports import compare as compare_oam, compare_oam as compare_oam_fields
from verify_nametable_palette import compare_extra
from verify_palette_timeline import native_sample
from verify_palette_controls import compare_guard as previous_guard
from verify_ppu_blank import exact_hex
from mmc5_timeline import reassemble
from route_evidence import atomic_json

ENDPOINT_BYTES = 5457


def native_registers(state):
    policy=exact_hex(state.get('chr_rewrite_policy'),3,'rewrite policy')
    if policy[0]>3 or int.from_bytes(policy[1:],'little')>0xFFF:
        raise ValueError('Invalid mode/provenance bits')
    rows=state.get('chr_records');count=state.get('completed_steps')
    if not isinstance(rows,list) or type(count) is not int or not 1<=count<=len(rows):
        raise ValueError('Missing retired mode records')
    clean=list(rows)
    for i in range(count):
        raw=bytearray(exact_hex(rows[i],48,'mode capture'))
        if raw[0]!=raw[43] or raw[43]>3 or raw[45]>15 or any(raw[46:]):
            raise ValueError('Invalid captured mode/provenance')
        if i==count-1 and raw[43:46]!=policy:
            raise ValueError('Final policy differs from retired record')
        raw[43:]=bytes(5);clean[i]=raw.hex()
    return fixed_registers(dict(state,chr_records=clean))


def compare_registers(reference,actual):
    if exact_hex(reference.get('chr_set_registers'),27,'reference CHR registers')!=native_registers(actual):
        raise RuntimeError('Independent CHR register endpoint differs')


def compare(plan,reference,actual):
    result=compare_oam(plan,reference,actual)
    compare_registers(reference,actual)
    result['independent_endpoint_bytes']=ENDPOINT_BYTES
    return result


def check_host(base,actual,mode):
    count=fixed_host(base,actual,mode)
    if exact_hex(base.get('chr_rewrite_policy'),3,'base policy')!=exact_hex(actual.get('chr_rewrite_policy'),3,'host policy'):
        raise RuntimeError('Host changed rewrite provenance')
    return count


def capture(kind,core,rom,out,steps=31,host=False,stop=None):
    out.parent.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,__file__,'--sample',kind,'--core',str(core),'--rom',str(rom),
         '--out',str(out),'--steps',str(steps)]
    if host:cmd.append('--host')
    if stop is not None:cmd+=['--stop',str(stop)]
    subprocess.run(cmd,check=True,timeout=90,stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def run_case(nes,snes,out,plan):
    d=out/plan['name'];ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
    rows=[];base=None;nmis=0
    for mode in (None,'free'):
        dest=d/('native' if mode is None else 'host')
        rom=create_native(dest,plan,initial(plan),**({'host_mode':mode} if mode else {}))
        actual=capture('native',snes,rom,dest/'capture.json',plan['steps'],bool(mode))
        rows.append(compare(plan,ref,actual))
        if mode:nmis=check_host(base,actual,mode)
        else:base=actual
    return rows,nmis


def run(nes,snes,out,limit=None,jobs=2):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Require 1..4 workers')
    plans=cases()
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(plans):raise ValueError('Invalid smoke limit')
        plans=plans[:limit]
    out.mkdir(parents=True,exist_ok=True);summary=out/'chr-mode-verification.json';summary.unlink(missing_ok=True)
    atomic_json(out/'plans.json',plans);done={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        pending={pool.submit(run_case,nes,snes,out,p):i for i,p in enumerate(plans)}
        for f in as_completed(pending):
            i=pending[f];done[i]=f.result()
            print('CHR mode',len(done),'/',len(plans),plans[i]['name'],flush=True)
            atomic_json(out/'progress.json',dict(complete=False,programs=len(done)))
    rows=[];nmis=0
    for i in range(len(plans)):
        pair,count=done[i];rows.extend(pair);nmis+=count
    result=dict(passed=True,complete_matrix=limit is None,programs=len(plans),scenarios=len(rows),
        independent_endpoint_bytes=len(rows)*ENDPOINT_BYTES,endpoint_bytes=ENDPOINT_BYTES,
        host_interrupts=nmis,results=rows,cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nestopia',nes),('snes',snes)]},
        scope='Rewritten-bank live size changes under forced blank and 8x16 mode. Independent final program endpoints; native instruction records only establish host noninterference. Stale-bank semantics, rendering, physical timing and CV3 integration are not claimed.')
    atomic_json(summary,result);return result


def check_guard(p,ref,actual,stop,retired):
    row=previous_guard(p,ref,actual,stop,retired)
    compare_extra(ref,actual);compare_oam_fields(ref,actual);compare_registers(ref,actual)
    row['independent_prefix_bytes']=ENDPOINT_BYTES
    return row


def original_prefix(out,p,stop):
    rom=create_nes(out,p);raw=bytearray(rom.read_bytes())
    offset=16+(p['prg_banks']-1)*8192+(stop&8191)
    raw[offset:offset+3]=bytes((0x4C,stop&255,stop>>8));rom.write_bytes(raw)
    return rom


def controls(nes,snes,out):
    out.mkdir(parents=True,exist_ok=True);summary=out/'chr-mode-controls.json';summary.unlink(missing_ok=True)
    hosts=[];mutants=[];guards=[]
    for p in (transition(3,0,'b',5,1024,3),transition(0,3,'a',7,1024,3),interleave('palette')):
        d=out/p['name'];ref=capture('nes',nes,create_nes(d/'nes',p),d/'nes/capture.json')
        base=capture('native',snes,create_native(d/'native',p,initial(p)),d/'native/capture.json')
        compare(p,ref,base)
        for mode in ('cost','time','capture','nested'):
            actual=capture('native',snes,create_native(d/mode,p,initial(p),host_mode=mode),d/mode/'capture.json',host=True)
            compare(p,ref,actual);hosts.append(dict(name=p['name'],mode=mode,host_interrupts=check_host(base,actual,mode)))
    for name,p,old,new in (
        ('bank-offset',transition(3,0,'b',5,1024,3),'    lda MR_ADDR\n    and f:CL_GROUP,x','    lda #0\n    and f:CL_GROUP,x'),
        ('bank-high',transition(3,0,'b',5,1024,0),'    lda f:CS_B,x\n    sta MR_INDEX','    lda f:CS_B,x\n    and #$000F\n    sta MR_INDEX')):
        d=out/('mutant-'+name);ref=capture('nes',nes,create_nes(d/'nes',p),d/'nes/capture.json')
        create_native(d/'native',p,initial(p));path=d/'native/chr_mode_rewrite.inc';text=path.read_text()
        if text.count(old)!=1:raise ValueError('Nonunique mutation')
        path.write_text(text.replace(old,new));actual=capture('native',snes,reassemble(d/'native'),d/'native/capture.json')
        if actual.get('complete') is not True or actual['status'] or actual['completed_steps']!=p['steps']:
            raise RuntimeError('Wrong-result control did not finish')
        try:compare(p,ref,actual)
        except (ValueError,RuntimeError) as exc:mutants.append(dict(name=name,rejected=True,completed=True,reason=str(exc)))
        else:raise RuntimeError('Incorrect mapper passed')
    for p,stop,retired in guard_cases():
        d=out/p['name'];ref=capture('nes',nes,original_prefix(d/'nes',p,stop),d/'nes/capture.json',stop=stop)
        actual=capture('native',snes,create_native(d/'native',p,initial(p)),d/'native/capture.json')
        guards.append(check_guard(p,ref,actual,stop,retired))
    # This mutant incorrectly retains authorization from the preceding mode.
    p,stop,retired=guard_cases()[0];d=out/'mutant-stale-authorization'
    ref=capture('nes',nes,original_prefix(d/'nes',p,stop),d/'nes/capture.json',stop=stop)
    create_native(d/'native',p,initial(p));path=d/'native/chr_mode_rewrite.inc';text=path.read_text()
    old='    lda #0\n    sta f:CL_VALID'
    if text.count(old)!=1:raise ValueError('Nonunique provenance mutation')
    path.write_text(text.replace(old,'    lda #$0FFF\n    sta f:CL_VALID'))
    actual=capture('native',snes,reassemble(d/'native'),d/'native/capture.json')
    if actual.get('complete') is not True:raise RuntimeError('Authorization mutant did not finish')
    try:check_guard(p,ref,actual,stop,retired)
    except (ValueError,RuntimeError) as exc:mutants.append(dict(name='stale-authorization',rejected=True,completed=True,reason=str(exc)))
    else:raise RuntimeError('Stale-bank authorization was accepted')
    # Preserved external-reference discrepancy, not an accepted native pathway.
    from native_fixture import Program
    from ppu_blank_fixture import put,address
    from mmc5_chr_blank import chr_image
    p=Program(0xE100);put(p,0x5127,3);put(p,0x5101,0);address(p,0x11)
    p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    plan=seal(p,'cm-stale-reference',3,64);d=out/'reference-diagnostic'
    ref=capture('nes',nes,create_nes(d,plan),d/'nestopia.json')
    observed=bytes.fromhex(ref['cpu_ram'])[0x680];latched=chr_image(64)[0x11]
    diagnostic=dict(agreement=observed==latched,nestopia_read=observed,
        documented_latched_address_read=latched,excluded_from_acceptance_totals=True,
        scope='Documented latch mapping predicts bank 0 after a mode-3 write of 3 followed by mode 0. This is not a physical-console measurement; stale native reads remain refused.')
    result=dict(passed=True,targeted_host_scenarios=len(hosts),host_interrupts=sum(h['host_interrupts'] for h in hosts),
        host_results=hosts,negative_controls=mutants,guards=guards,stale_reference_diagnostic=diagnostic,
        per_instruction_nes_equivalence_claimed=False)
    atomic_json(summary,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample',choices=('nes','native'));p.add_argument('--host',action='store_true')
    p.add_argument('--steps',type=int,default=31);p.add_argument('--stop',type=int)
    p.add_argument('--controls',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--jobs',type=int,default=2)
    for k in ('core','rom','nes-core','snes-core','out'):p.add_argument('--'+k,type=Path)
    a=p.parse_args()
    if a.sample=='nes':nes_sample(a.core,a.rom,a.out,a.stop)
    elif a.sample=='native':native_sample(a.core,a.rom,a.out,a.steps,a.host,
        extra_ranges={'oam':(0x5900,256),'oam_address':(0x1C3B,1),'chr_set_b':(0x5A00,9),'chr_rewrite_policy':(POLICY_ADDRESS,3)})
    elif a.controls:print(json.dumps(controls(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve()),indent=2))
    else:print(json.dumps(run(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.limit,a.jobs),indent=2))
