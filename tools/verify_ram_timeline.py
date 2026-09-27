#!/usr/bin/env python3
"""Exercise full-RAM addressing on one evolving native timeline.

Only authored boot inputs/programs and declared requests enter native execution.
The original NES supplies comparison evidence, not intermediate execution state.
Physical guest pin sampling, mapper snooping and DMA remain outside this profile.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from ram_timeline_fixture import cases, fault_cases, edge_cases
from timeline_fixture import expected_initial
from timeline_program import create_native
from verify_timeline import compare
from verify_host_nmi import execute, check_host
from host_nmi_fixture import reassemble
from route_evidence import atomic_json

ROOT=Path(__file__).resolve().parents[1]


def nes_capture(core: Path,folder: Path,plan: dict,*,probe: bool) -> dict:
    folder.mkdir(parents=True,exist_ok=True)
    atomic_json(folder/'plan.json',plan)
    subprocess.run([sys.executable,str(ROOT/'tools/verify_timeline.py'),
                    '--sample','probe' if probe else 'plain','--core',str(core),
                    '--plan',str(folder/'plan.json'),'--out',str(folder)],
                   check=True,timeout=30,stdout=subprocess.DEVNULL)
    return json.loads((folder/'capture.json').read_text())


def native_capture(core: Path,folder: Path,plan: dict,*,mode: str|None=None) -> dict:
    rom=create_native(folder,plan,expected_initial(plan),host_mode=mode)
    return execute(core,rom,folder/'capture.json',plan['steps'],host_expected=mode is not None,ram_bytes=2048)


def unchanged_on_fault(plan: dict,report: dict) -> dict:
    """Memory access guard must fault before a guest side effect or retirement."""
    done=report.get('completed_steps')
    if report.get('marker')!=0xEE or report.get('status')!=5 or type(done) is not int or not 0<done<plan['steps']:
        raise ValueError('RAM guard did not stop at an access boundary')
    previous=bytes.fromhex(report['records'][done-1])
    final=bytes.fromhex(report['final_guest_ram'])
    context=bytearray.fromhex(report['final_guest_context'])
    if len(previous)!=2080 or len(final)!=2048 or len(context)!=32:
        raise ValueError('Incomplete failure context')
    if previous[32:]!=final or previous[:14]!=context[:14]:
        raise ValueError('RAM guard changed guest memory, registers, requests or clock')
    return dict(name=plan['name'],rejected=True,completed_steps=done,status=5,
                unchanged_guest_bytes=2048,unchanged_header_bytes=14)


def verify(plain: Path,probe: Path,snes: Path,out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'ram-timeline-verification.json';summary.unlink(missing_ok=True)
    plans=cases()+edge_cases();atomic_json(out/'plans.json',plans)
    results=[];references={};baselines={};inert=0;host_results=[]
    for plan in plans:
        print('RAM timeline',plan['name'],flush=True)
        folder=out/plan['name']
        reference=nes_capture(probe,folder/'nes',plan,probe=True)
        references[plan['name']]=reference
        if not plan['events']:
            control=nes_capture(plain,folder/'plain',plan,probe=False)
            if control!={k:v for k,v in reference.items() if k!='records'}:
                raise RuntimeError('Full-RAM harness changed original no-request execution')
            inert+=1
        baseline=native_capture(snes,folder/'native',plan)
        result=compare(plan,reference,baseline)
        if plan['name'].startswith('ram-jmp-'):
            required='6c'
        else:
            required=plan['name'].split('-')[1]
        if not plan['events'] and required not in result['executed_opcodes']:
            raise RuntimeError('Selected RAM opcode was never exercised')
        baselines[plan['name']]=baseline
        results.append(result)
        host=native_capture(snes,folder/'host-free',plan,mode='free')
        checked=check_host(plan,reference,host,'free')
        if host['protected_memory']!=baseline['protected_memory']:
            raise RuntimeError('Host NMI changed final address-resolution scratch')
        host_results.append(checked)
        atomic_json(out/'progress.json',dict(complete=False,scenarios_completed=len(results)))
    # Explicit host waits after address resolution / before saving ALU state,
    # plus nested display NMIs. These consume no emulated original-game cycles.
    for name in ('ram-b1-1','ram-91-1','ram-fe-1','ram-be-1','ram-a1-1','ram-b1-1-events'):
        plan=next(p for p in plans if p['name']==name)
        for mode in ('loaded','alu','time','nested'):
            folder=out/'stress'/name/mode
            actual=native_capture(snes,folder,plan,mode=mode)
            checked=check_host(plan,references[name],actual,mode)
            if actual['protected_memory']!=baselines[name]['protected_memory']:
                raise RuntimeError('Interrupted operand/pointer scratch was not restored')
            host_results.append(checked)
    # Real wrong binaries, not just changed JSON. Each must complete or fault
    # in a way that the ordinary strict comparison detects.
    controls=[]
    for name,case,old,new in (
        ('unwrapped-pointer','ram-b1-1','    inc a\n    and #$00FF\n    tax','    inc a\n    nop\n    nop\n    tax'),
        ('wrong-mirror','ram-b1-1','    and #$07FF','    and #$03FF'),
        ('stale-pointer-cost','ram-b1-1','    sta GC_INPUT+8','    stz GC_INPUT+8')):
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name)
        create_native(folder,plan,expected_initial(plan))
        path=folder/'timeline_ram.inc';text=path.read_text()
        if text.count(old)!=1:raise RuntimeError('Mutation anchor is not unique')
        path.write_text(text.replace(old,new,1));rom=reassemble(folder)
        actual=execute(snes,rom,folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048)
        try:compare(plan,references[case],actual)
        except (RuntimeError,ValueError):controls.append(dict(name=name,rejected=True,marker=actual['marker'],status=actual['status']))
        else:raise RuntimeError('Deliberately broken RAM implementation passed')
    faults=[]
    for plan in fault_cases():
        actual=native_capture(snes,out/plan['name'],plan)
        faults.append(unchanged_on_fault(plan,actual))
    # Capture ABI is deliberately incompatible, not guessed or truncated.
    all_rows=results+host_results
    report=dict(passed=True,memory_model='internal-2k',scenarios=len(results),
        no_request_plain_comparisons=inert,host_scenarios=len(host_results),
        dependent_boundaries=sum(r['steps'] for r in all_rows),
        guest_ram_bytes=sum(r['steps']*2048 for r in all_rows),
        header_bytes=sum(r['steps']*32 for r in all_rows),
        matched_bytes=sum(r['record_bytes'] for r in all_rows),
        host_interrupts=sum(r['host']['count'] for r in host_results),
        nested_interruptions=sum(r['host']['nested_wait_hits'] for r in host_results),
        deliberate_interruptions=sum(r['host']['wait_hits'] for r in host_results),
        irq_entries=sum(r['entries']['irq'] for r in results),
        nmi_entries=sum(r['entries']['nmi'] for r in results),
        exercised_opcodes=sorted({k for r in results for k in r['executed_opcodes']}),
        memory_opcode_variants=100,negative_controls=controls,fault_guards=faults,
        cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nes_plain',plain),('nes_ram_stimulus',probe),('snes',snes)]},
        production_runtime_changed=False,guest_event_policy_changed=False,
        results=results,host_results=host_results,
        scope='Dependent internal-RAM addressing, 2-KiB aliases, original instruction costs and sampled guest interrupts under real host NMIs. Not bus-cycle accuracy, mapper observation, DMA/DMC, physical NES polling, live CV3 scheduling or performance.')
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();report=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','host_results')},indent=2))
