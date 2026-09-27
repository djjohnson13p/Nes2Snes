#!/usr/bin/env python3
"""Independent CPU-mode ExRAM and multiplier execution, not PPU rendering.

2-KiB CPU state is compared at each recorded instruction boundary. Full ExRAM
and cartridge RAM are separate final-boundary snapshots, not per-step coverage.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
from mmc5_cpu_io import PROFILE,initial_exram,create_native
from mmc5_cpu_io_fixture import cases,fault_cases
from mmc5_timeline import reassemble
from timeline_fixture import expected_initial
from verify_ram_timeline import nes_capture
from verify_host_nmi import execute,check_host
from verify_timeline import compare
from verify_wram_timeline import check_ram,guard as ram_guard
from route_evidence import atomic_json


def check_exram(reference: dict,native: dict) -> dict:
    for report,key in ((reference,'initial_exram'),(reference,'exram'),(native,'exram')):
        if not isinstance(report.get(key),str) or len(report[key])!=2048:
            raise ValueError('Missing full ExRAM endpoint snapshot')
        if len(bytes.fromhex(report[key]))!=1024:
            raise ValueError('Malformed full ExRAM endpoint snapshot')
    if bytes.fromhex(reference['initial_exram'])!=initial_exram():
        raise ValueError('Original ExRAM boot differs from declared initial memory')
    a,b=bytes.fromhex(reference['exram']),bytes.fromhex(native['exram'])
    if a!=b:raise RuntimeError('ExRAM endpoint differs from original execution')
    return dict(exram_bytes_checked=1024,exram_sha256=hashlib.sha256(a).hexdigest())


def native_capture(core: Path,folder: Path,plan: dict,mode=None):
    rom=create_native(folder,plan,expected_initial(plan),host_mode=mode)
    return execute(core,rom,folder/'capture.json',plan['steps'],host_expected=mode is not None,
                   ram_bytes=2048,cartridge_bytes=32768,exram=True)


def guard(plan,native,previous):
    result=ram_guard(plan,native,previous);check_exram(previous,native)
    last=bytes.fromhex(native['records'][native['completed_steps']-1])
    context=bytes.fromhex(native['final_guest_context'])
    if last[28:31]!=context[24:27]:raise ValueError('Rejected operation changed CPU-I/O registers')
    return dict(result,exram_bytes_unchanged=1024)


def verify(plain:Path,probe:Path,snes:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True);summary=out/'cpu-io-verification.json';summary.unlink(missing_ok=True)
    plans=cases();atomic_json(out/'plans.json',plans);rows=[];hosts=[];refs={};natives={};controls=0;forms=set()
    for i,plan in enumerate(plans):
        print(f'CPU I/O {i+1}/{len(plans)} {plan["name"]}',flush=True)
        folder=out/plan['name'];a=nes_capture(probe,folder/'nes',plan,probe=True);n=native_capture(snes,folder/'native',plan)
        result=compare(plan,a,n);result.update(check_ram(a,n));result.update(check_exram(a,n))
        refs[plan['name']]=a;natives[plan['name']]=n;rows.append(result)
        raw=(folder/'nes/fixture.nes').read_bytes()[16:16+plan['prg_banks']*8192]
        if (folder/'native/fixture.sfc').read_bytes()[32768:32768+len(raw)]!=raw:raise RuntimeError('Original cartridge input changed')
        if plan['name'].startswith('ex-access'):
            op=plan['name'].split('-')[2]
            if op not in result['executed_opcodes']:raise RuntimeError('Declared ExRAM opcode not executed')
            forms.add(op)
        if not plan['events']:
            control=nes_capture(plain,folder/'plain',plan,probe=False)
            expected={k:v for k,v in a.items() if k not in ('records','initial_cartridge_ram','cartridge_ram','initial_exram','exram')}
            if control!=expected:raise RuntimeError('CPU I/O observer changed no-request execution')
            controls+=1
        h=native_capture(snes,folder/'host-free',plan,'free');hr=check_host(plan,a,h,'free')
        hr.update(check_ram(a,h));hr.update(check_exram(a,h))
        if h['protected_memory']!=n['protected_memory']:raise RuntimeError('Host NMI corrupted CPU I/O scratch')
        hosts.append(hr);atomic_json(out/'progress.json',dict(complete=False,plans_completed=len(rows)))
    for name in ('ex-transition-02-03-nmi','ex-mul-immediate','ex-jump-wrap'):
        plan=next(p for p in plans if p['name']==name)
        for mode in ('cost','time','capture','nested'):
            n=native_capture(snes,out/'stress'/name/mode,plan,mode);r=check_host(plan,refs[name],n,mode)
            r.update(check_ram(refs[name],n));r.update(check_exram(refs[name],n))
            if n['protected_memory']!=natives[name]['protected_memory']:raise RuntimeError('Targeted interruption changed CPU I/O scratch')
            hosts.append(r)
    mutants=[]
    changes=(('readonly-write','ex-access-8d-m03-x3-5cff','    lda EX_MODE\n    cmp #2','    lda #2\n    cmp #2'),
             ('mirrored-exram','ex-access-9d-m02-x3-5cff','    and #$03FF','    and #$00FF'),
             ('stale-product','ex-mul-immediate','    jsr ExMultiply','    nop\n    nop\n    nop'))
    for name,case,old,new in changes:
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name);create_native(folder,plan,expected_initial(plan))
        path=folder/('program.inc' if name=='stale-product' else 'mmc5_prg.inc');t=path.read_text()
        if old not in t:raise RuntimeError('Absent mutation anchor')
        path.write_text(t.replace(old,new));n=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048,cartridge_bytes=32768,exram=True)
        if n.get('marker')!=0x5A:raise RuntimeError('Mutation must complete with wrong results, not merely crash')
        try:compare(plan,refs[case],n);check_ram(refs[case],n);check_exram(refs[case],n)
        except (ValueError,RuntimeError):mutants.append(dict(name=name,rejected=True,completed=True))
        else:raise RuntimeError('Broken I/O implementation accepted')
    guards=[]
    for plan in fault_cases():
        folder=out/plan['name'];n=native_capture(snes,folder/'native',plan)
        before=copy.deepcopy(plan);before['steps']=n['completed_steps']
        a=nes_capture(probe,folder/'prior',before,probe=True);guards.append(guard(plan,n,a))
    totals=rows+hosts
    report=dict(passed=True,profile=PROFILE,plans=len(plans),scenarios=len(totals),
        boundaries=sum(r['steps'] for r in totals),internal_state_bytes=sum(r['record_bytes'] for r in totals),
        final_exram_bytes=sum(r['exram_bytes_checked'] for r in totals),
        final_cartridge_bytes=sum(r['cartridge_bytes_checked'] for r in totals),
        access_forms=len(forms),multiplier_pairs=320,no_request_controls=controls,host_scenarios=len(hosts),
        host_interrupts=sum(r['host']['count'] for r in hosts),negative_controls=mutants,fault_guards=guards,
        cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('nes_plain',plain),('nes_io_probe',probe),('snes',snes)]},
        production_runtime_changed=False,new_game_replay=False,
        scope='CPU ExRAM modes 2/3 and absolute LDA/STA multiplier I/O on the sampled timeline. No rendering modes, PPU behavior, open bus, physical bus/event timing, CV3 scheduling or speed claim.',
        results=rows,host_results=hosts)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();r=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in r.items() if k not in ('results','host_results')},indent=2))
