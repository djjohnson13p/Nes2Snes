#!/usr/bin/env python3
"""Independent SRAM state, bank aliases and protected writes on native timeline.

Every endpoint compares all internal CPU RAM and registers/mapping state. Full
32-KiB cartridge RAM is compared at the final recorded boundary only, not falsely
counted at every step. Original NES writes and mapper logic are the oracle.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
from mmc5_wram import PROFILE,initial_ram,create_native
from mmc5_wram_fixture import cases,fault_cases
from mmc5_timeline import reassemble
from timeline_fixture import expected_initial
from verify_ram_timeline import nes_capture
from verify_host_nmi import execute,check_host
from verify_timeline import compare
from route_evidence import atomic_json


def check_header(plan: dict,row: bytes) -> None:
    slots=row[20:24];bank=row[24];page=row[25];lock=row[26];reg=row[27]
    pc=int.from_bytes(row[4:6],'little')
    if any(v>=plan['prg_banks'] and not 128<=v<=131 for v in slots) or not 0x8000<=pc<=65535 or bank>=plan['prg_banks'] or bank!=slots[(pc-0x8000)//8192]:
        raise ValueError('Invalid typed mapper or executable bank')
    if not 0<=reg<4 or page!=128+reg or lock>15:
        raise ValueError('Invalid RAM-page/protection capture')


def check_ram(reference: dict,native: dict) -> dict:
    a=reference.get('cartridge_ram');b=native.get('cartridge_ram')
    if not isinstance(a,str) or not isinstance(b,str) or len(a)!=65536 or len(b)!=65536:
        raise ValueError('Missing complete endpoint cartridge memory')
    initial=reference.get('initial_cartridge_ram')
    if not isinstance(initial,str) or len(initial)!=65536 or bytes.fromhex(initial)!=initial_ram():
        raise ValueError('Original cartridge boot did not establish declared initial memory')
    if bytes.fromhex(a)!=bytes.fromhex(b):
        offsets=[i for i,(x,y) in enumerate(zip(bytes.fromhex(a),bytes.fromhex(b))) if x!=y]
        raise RuntimeError(f'Cartridge memory mismatch: {len(offsets)} bytes; first {offsets[:10]}')
    return dict(cartridge_bytes_checked=32768,cartridge_sha256=hashlib.sha256(bytes.fromhex(a)).hexdigest())


def native_capture(core: Path,folder: Path,plan: dict,mode=None) -> dict:
    rom=create_native(folder,plan,expected_initial(plan),host_mode=mode)
    return execute(core,rom,folder/'capture.json',plan['steps'],host_expected=mode is not None,ram_bytes=2048,cartridge_bytes=32768)


def guard(plan:dict,native:dict,previous:dict) -> dict:
    done=native.get('completed_steps')
    if native.get('complete') is not False or native.get('marker')!=0xEE or native.get('status')!=5 or type(done) is not int or not 0<done<plan['steps']:
        raise ValueError('Cartridge guard did not fail closed')
    row=bytes.fromhex(native['records'][done-1]);ram=bytes.fromhex(native['final_guest_ram']);context=bytes.fromhex(native['final_guest_context'])
    protected=bytes.fromhex(native['protected_memory'])
    if len(row)!=2080 or len(ram)!=2048 or len(context)!=32 or len(protected)!=132:
        raise ValueError('Incomplete guard evidence')
    if row[32:]!=ram or row[:14]!=context[:14] or row[20:24]!=protected[0x38:0x3C] or row[26]!=protected[0x36] or row[27]!=protected[0x37]:
        raise ValueError('Refused operation mutated guest or mapper state')
    check_ram(previous,native)
    return dict(name=plan['name'],rejected=True,completed_steps=done,status=5,
                internal_bytes_unchanged=2048,cartridge_bytes_unchanged=32768)


def verify(plain:Path,probe:Path,snes:Path,out:Path) -> dict:
    out.mkdir(parents=True,exist_ok=True);summary=out/'wram-timeline-verification.json';summary.unlink(missing_ok=True)
    plans=cases();atomic_json(out/'plans.json',plans);rows=[];hosts=[];refs={};natives={};inert=0;forms=set()
    for number,plan in enumerate(plans):
        print(f'Cartridge RAM {number+1}/{len(plans)} {plan["name"]}',flush=True)
        folder=out/plan['name'];a=nes_capture(probe,folder/'nes',plan,probe=True)
        b=native_capture(snes,folder/'native',plan)
        raw=(folder/'nes/fixture.nes').read_bytes()[16:16+plan['prg_banks']*8192]
        if (folder/'native/fixture.sfc').read_bytes()[32768:32768+len(raw)]!=raw:
            raise RuntimeError('Native original-cartridge data differs from NES input')
        result=compare(plan,a,b);result.update(check_ram(a,b));refs[plan['name']]=a;natives[plan['name']]=b
        if plan['name'].startswith('cw-access-'):
            op=plan['name'].split('-')[2]
            if op not in result['executed_opcodes']:raise RuntimeError('Declared SRAM opcode not exercised')
            forms.add(op)
        if not plan['events']:
            control=nes_capture(plain,folder/'plain',plan,probe=False)
            expected={k:v for k,v in a.items() if k not in ('records','initial_cartridge_ram','cartridge_ram')}
            if control!=expected:raise RuntimeError('Cartridge observer changed no-request execution')
            inert+=1
        h=native_capture(snes,folder/'host-free',plan,'free');hr=check_host(plan,a,h,'free');hr.update(check_ram(a,h))
        if h['protected_memory']!=b['protected_memory']:raise RuntimeError('Host NMI corrupted RAM state or scratch')
        rows.append(result);hosts.append(hr);atomic_json(out/'progress.json',dict(complete=False,plans_completed=len(rows)))
    for name in ('cw-persistence-nmi','cw-cross-fe','cw-jump-wrap'):
        plan=next(p for p in plans if p['name']==name)
        for mode in ('cost','time','capture','nested'):
            n=native_capture(snes,out/'stress'/name/mode,plan,mode);r=check_host(plan,refs[name],n,mode);r.update(check_ram(refs[name],n))
            if n['protected_memory']!=natives[name]['protected_memory']:raise RuntimeError('Targeted interruption corrupted RAM state')
            hosts.append(r)
    controls=[]
    mutations=(('locked-write','cw-lock-00-00','    cmp #6\n    bne locked','    cmp #6\n    nop\n    nop'),
               ('wrong-page','cw-persistence','    lda MB_BANK\n    and #3\n    xba','    lda MB_BANK\n    and #0\n    xba'),
               ('unmasked-protection','cw-lock-fe-fd','    and #3\n    sta MR_VALUE','    and #$FF\n    sta MR_VALUE'))
    for name,case,old,new in mutations:
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name);create_native(folder,plan,expected_initial(plan))
        path=folder/('program.inc' if name=='unmasked-protection' else 'mmc5_prg.inc');text=path.read_text()
        if old not in text:raise RuntimeError('Absent mutation anchor '+name)
        path.write_text(text.replace(old,new));n=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048,cartridge_bytes=32768)
        try:compare(plan,refs[case],n);check_ram(refs[case],n)
        except (ValueError,RuntimeError):controls.append(dict(name=name,rejected=True))
        else:raise RuntimeError('Broken SRAM implementation accepted')
    faults=[]
    for plan in fault_cases():
        folder=out/plan['name'];n=native_capture(snes,folder/'native',plan)
        prior=copy.deepcopy(plan);prior['steps']=n['completed_steps']
        a=nes_capture(probe,folder/'prior',prior,probe=True)
        faults.append(guard(plan,n,a))
    totals=rows+hosts
    report=dict(passed=True,profile=PROFILE,plans=len(plans),scenarios=len(totals),
        boundaries=sum(r['steps'] for r in totals),internal_state_bytes=sum(r['record_bytes'] for r in totals),
        final_cartridge_bytes=sum(r['cartridge_bytes_checked'] for r in totals),
        access_opcode_forms=len(forms),no_request_controls=inert,host_scenarios=len(hosts),
        host_interrupts=sum(r['host']['count'] for r in hosts),negative_controls=controls,fault_guards=faults,
        cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('nes_plain',plain),('nes_wram_probe',probe),('snes',snes)]},
        production_runtime_changed=False,new_game_replay=False,
        scope='Explicit 32-KiB single-chip PRG-RAM wiring, state and instruction cost only. Full cartridge snapshot at final boundary; not each intermediate boundary. No RAM code execution, open bus, cycle-level I/O, physical NES interrupts or live CV3 scheduling.',
        results=rows,host_results=hosts)
    atomic_json(summary,report);return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();r=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in r.items() if k not in ('results','host_results')},indent=2))
