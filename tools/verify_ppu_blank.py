#!/usr/bin/env python3
"""Original-NES register/nametable transfers versus protected native execution."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
from mmc5_ppu_blank import PROFILE,initial_ppu,initial_ciram,create_native
from ppu_blank_fixture import cases,fault_cases
from mmc5_timeline import reassemble
from timeline_fixture import expected_initial
from verify_ram_timeline import nes_capture
from verify_host_nmi import execute,check_host
from verify_timeline import compare
from verify_wram_timeline import check_ram
from verify_cpu_io_timeline import check_exram,guard as cpu_guard
from route_evidence import atomic_json


def exact_hex(value,size,label):
    if not isinstance(value,str) or len(value)!=size*2:
        raise ValueError('Missing or malformed '+label)
    raw=bytes.fromhex(value)
    if len(raw)!=size:raise ValueError('Incomplete '+label)
    return raw


def check_ppu(plan,reference,native):
    a,b=reference.get('ppu_records'),native.get('ppu_records')
    if not isinstance(a,list) or len(a)!=plan['steps']+1 or not isinstance(b,list) or len(b)!=plan['steps']:
        raise ValueError('Incomplete PPU instruction records')
    if exact_hex(a[0],16,'initial PPU')!=initial_ppu():raise ValueError('Original PPU boot differs')
    if exact_hex(reference.get('initial_ciram'),2048,'initial CIRAM')!=initial_ciram():raise ValueError('Original CIRAM boot differs')
    for i,(x,y) in enumerate(zip(a[1:],b),1):
        first=exact_hex(x,16,'reference PPU');second=exact_hex(y,16,'native PPU')
        if first!=second:raise RuntimeError(f"{plan['name']}: PPU step {i} expected {first.hex()}, got {second.hex()}")
        if first[0]&0xC0 or first[1]&0x18 or first[2]>1 or first[3]>7 or any(first[13:]):raise ValueError('Invalid blank PPU state')
        if any((first[10]>>s)&3==2 for s in (0,2,4,6)) or first[12]>3:raise ValueError('Unsupported nametable mapping state')
    first=exact_hex(reference.get('ciram'),2048,'reference CIRAM');second=exact_hex(native.get('ciram'),2048,'native CIRAM')
    if first!=second:raise RuntimeError('CIRAM final endpoint differs')
    if exact_hex(native.get('ppu_state'),16,'final PPU')!=exact_hex(b[-1],16,'last PPU'):
        raise ValueError('Final PPU state differs from completed endpoint')
    return dict(ppu_register_bytes=plan['steps']*16,final_ciram_bytes=2048,ciram_sha256=hashlib.sha256(first).hexdigest())


def native_capture(core,folder,plan,mode=None):
    rom=create_native(folder,plan,expected_initial(plan),host_mode=mode)
    return execute(core,rom,folder/'capture.json',plan['steps'],host_expected=mode is not None,
                   ram_bytes=2048,cartridge_bytes=32768,exram=True,ppu_blank=True)


def guard(plan,native,previous):
    result=cpu_guard(plan,native,previous)
    if exact_hex(native.get('ciram'),2048,'guard CIRAM')!=exact_hex(previous.get('ciram'),2048,'prior CIRAM'):
        raise ValueError('Guard changed CIRAM')
    state=exact_hex(native.get('ppu_state'),16,'guard PPU')
    if state!=exact_hex(previous['ppu_records'][-1],16,'prior PPU'):
        raise ValueError('Guard changed PPU registers')
    return dict(result,ciram_bytes_unchanged=2048,ppu_register_bytes_unchanged=16)



def reference_disagreement(plain,probe,out):
    """Preserve an independently executed non-passing accuracy result.

    The documented fill-attribute register uses only its low two bits. Pinned
    FCEUmm expands all supplied bits, so value four produces $54 rather than $00.
    The native profile rejects upper-bit values; this is not an admitted pass.
    """
    from ppu_blank_fixture import fill_case
    plan=fill_case(0x11,4)
    observed=nes_capture(probe,out/'observed',plan,probe=True)
    control=nes_capture(plain,out/'plain',plan,probe=False)
    omitted=('records','initial_cartridge_ram','cartridge_ram','initial_exram','exram',
             'ppu_records','initial_ciram','ciram')
    if control!={k:v for k,v in observed.items() if k not in omitted}:
        raise RuntimeError('Fill diagnostic observation changed original execution')
    if observed.get('complete') is not True or len(observed.get('records',[]))!=plan['steps']+1:
        raise RuntimeError('Incomplete fill reference diagnostic')
    record=exact_hex(observed['records'][-1],2080,'fill diagnostic CPU record')
    value=record[32+0x682]
    if value!=0x54 or record[32+0x681]!=0x11:
        raise RuntimeError('Pinned fill-attribute disagreement changed; review the reference')
    result=dict(reference_accuracy_passed=False,diagnostic_reproduced=True,
        no_request_plain_matches=True,register=0x5107,written=4,
        documented_attribute=0,observed_attribute=value,comparison_address=0x682,
        native_behavior='Guarded before register mutation; excluded from supported mapping passes.',
        scope='One authored upper-bit fill-register diagnostic against the pinned original core; not physical hardware verification.')
    atomic_json(out/'reference-disagreement.json',result)
    return result



def verify(plain,probe,snes,out):
    out.mkdir(parents=True,exist_ok=True);summary=out/'ppu-blank-verification.json';summary.unlink(missing_ok=True)
    plans=cases();atomic_json(out/'plans.json',plans);rows=[];hosts=[];refs={};natives={};control_count=0
    for i,plan in enumerate(plans):
        print(f'Blank PPU {i+1}/{len(plans)} {plan["name"]}',flush=True)
        folder=out/plan['name'];a=nes_capture(probe,folder/'nes',plan,probe=True);n=native_capture(snes,folder/'native',plan)
        result=compare(plan,a,n);result.update(check_ram(a,n));result.update(check_exram(a,n));result.update(check_ppu(plan,a,n))
        refs[plan['name']]=a;natives[plan['name']]=n;rows.append(result)
        if not plan['events']:
            control=nes_capture(plain,folder/'plain',plan,probe=False)
            expected={k:v for k,v in a.items() if k not in ('records','initial_cartridge_ram','cartridge_ram','initial_exram','exram','ppu_records','initial_ciram','ciram')}
            if control!=expected:raise RuntimeError('PPU observation changed plain-core execution')
            control_count+=1
        h=native_capture(snes,folder/'host-free',plan,'free');hr=check_host(plan,a,h,'free')
        hr.update(check_ram(a,h));hr.update(check_exram(a,h));hr.update(check_ppu(plan,a,h))
        if h['protected_memory']!=n['protected_memory']:raise RuntimeError('Host NMI changed protected scratch')
        hosts.append(hr);atomic_json(out/'progress.json',dict(complete=False,plans_completed=len(rows)))
    for name in ('pv-buffer-write-retains','pv-fill-ff-03','pv-guest-nmi'):
        plan=next(p for p in plans if p['name']==name)
        for mode in ('cost','time','capture','nested'):
            h=native_capture(snes,out/'stress'/name/mode,plan,mode);row=check_host(plan,refs[name],h,mode)
            row.update(check_ram(refs[name],h));row.update(check_exram(refs[name],h));row.update(check_ppu(plan,refs[name],h))
            if h['protected_memory']!=natives[name]['protected_memory']:raise RuntimeError('Targeted host NMI changed scratch')
            hosts.append(row)
    changes=(('unbuffered','pv-buffer-write-retains','    lda PV+8\n    sta MR_VALUE','    lda PV+13\n    sta MR_VALUE'),
             ('wrong-mirror','pv-transfer-23ff-1-44-0','    ora #4\n    sta PV+15','    ora #0\n    sta PV+15'),
             ('fill-write','pv-fill-ff-03','    lda MR_MODE\n    cmp #3','    lda MR_MODE\n    cmp #2'))
    mutants=[]
    for name,case,old,new in changes:
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name)
        create_native(folder,plan,expected_initial(plan));path=folder/'mmc5_ppu_blank.inc';text=path.read_text()
        if text.count(old)!=1:raise RuntimeError('Nonunique mutant anchor')
        path.write_text(text.replace(old,new))
        n=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048,cartridge_bytes=32768,exram=True,ppu_blank=True)
        if n.get('marker')!=0x5A:raise RuntimeError('Mutant did not finish; not a wrong-result control')
        try:compare(plan,refs[case],n);check_ppu(plan,refs[case],n)
        except (ValueError,RuntimeError):mutants.append(dict(name=name,rejected=True,completed=True))
        else:raise RuntimeError('Mutant accepted')
    guards=[]
    for plan in fault_cases():
        folder=out/plan['name'];n=native_capture(snes,folder/'native',plan)
        before=copy.deepcopy(plan);before['steps']=n['completed_steps'];a=nes_capture(probe,folder/'prior',before,probe=True)
        guards.append(guard(plan,n,a))
    all_rows=rows+hosts
    report=dict(passed=True,profile=PROFILE,plans=len(plans),scenarios=len(all_rows),
        boundaries=sum(r['steps'] for r in all_rows),internal_state_bytes=sum(r['record_bytes'] for r in all_rows),
        ppu_register_bytes=sum(r['ppu_register_bytes'] for r in all_rows),final_ciram_bytes=sum(r['final_ciram_bytes'] for r in all_rows),
        final_exram_bytes=sum(r['exram_bytes_checked'] for r in all_rows),final_cartridge_bytes=sum(r['cartridge_bytes_checked'] for r in all_rows),
        no_request_controls=control_count,host_scenarios=len(hosts),host_interrupts=sum(r['host']['count'] for r in hosts),
        negative_controls=mutants,fault_guards=guards,
        cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('nes_plain',plain),('ppu_probe',probe),('snes',snes)]},
        production_runtime_changed=False,new_game_replay=False,
        scope='Blanked PPU CPU-port state and CIRAM/fill nametables on sampled guest timeline. No CHR, palettes, OAM, ExRAM nametables, rendering, physical event deadlines, DMA/DMC, CV3 speed or boss-clear claim.',
        reference_disagreement=reference_disagreement(plain,probe,out/'reference-disagreement'),
        results=rows,host_results=hosts)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();r=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in r.items() if k not in ('results','host_results')},indent=2))
