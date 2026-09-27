#!/usr/bin/env python3
"""Independent original-cartridge reads on the guarded native timeline.

Source ROM bytes are authored inputs; reference endpoints are comparison-only.
This models state and original instruction costs, not mapper/bus event timing.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from build_viewer import ROOT,tool,finalize_rom,validate_sfc
from rom_timeline_fixture import cases,fault_cases
from timeline_program import create_native
from timeline_fixture import expected_initial
from verify_ram_timeline import nes_capture,native_capture,unchanged_on_fault
from verify_timeline import compare
from verify_host_nmi import execute,check_host
from route_evidence import atomic_json


def reassemble(folder: Path) -> Path:
    subprocess.run([tool('ca65'),'-g','-I',str(folder),'--bin-include-dir',str(folder),
                    '-o',str(folder/'fixture.o'),str(folder/'fixture.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),
                    '-o',str(folder/'fixture.bin'),str(folder/'fixture.o')],check=True)
    data=finalize_rom((folder/'fixture.bin').read_bytes(),(folder/'original-prg.bin').read_bytes())
    validate_sfc(data);path=folder/'fixture.sfc';path.write_bytes(data);return path


def verify(plain: Path,probe: Path,snes: Path,out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'rom-timeline-verification.json';summary.unlink(missing_ok=True)
    plans=cases();atomic_json(out/'plans.json',plans)
    results=[];hosts=[];references={};baselines={};plain_count=0
    for plan in plans:
        print('ROM timeline',plan['name'],flush=True)
        folder=out/plan['name']
        reference=nes_capture(probe,folder/'nes',plan,probe=True)
        references[plan['name']]=reference
        if not plan['events']:
            inert=nes_capture(plain,folder/'plain',plan,probe=False)
            if inert!={k:v for k,v in reference.items() if k!='records'}:
                raise RuntimeError('ROM harness changed no-request original execution')
            plain_count+=1
        native=native_capture(snes,folder/'native',plan)
        result=compare(plan,reference,native)
        op='6c' if 'jmp' in plan['name'] else plan['name'].split('-')[1]
        if not plan['events'] and op not in result['executed_opcodes']:
            raise RuntimeError('Declared ROM instruction was not exercised')
        original=(folder/'nes/fixture.nes').read_bytes()[16:32784]
        candidate=(folder/'native/fixture.sfc').read_bytes()
        if candidate[32768:65536]!=original:
            raise RuntimeError('Separate raw-cartridge bank differs from original input')
        baselines[plan['name']]=native;results.append(result)
        host=native_capture(snes,folder/'host-free',plan,mode='free')
        checked=check_host(plan,reference,host,'free')
        if host['protected_memory']!=native['protected_memory']:
            raise RuntimeError('Host NMI changed ROM-resolution scratch')
        hosts.append(checked)
        atomic_json(out/'progress.json',dict(complete=False,plans_completed=len(results)))
    for plan in (plans[1],next(p for p in plans if p['name']=='rom-b1-1-90ff-03-events'),plans[-1]):
        for mode in ('loaded','alu','cost','nested'):
            actual=native_capture(snes,out/'stress'/plan['name']/mode,plan,mode=mode)
            checked=check_host(plan,references[plan['name']],actual,mode)
            if actual['protected_memory']!=baselines[plan['name']]['protected_memory']:
                raise RuntimeError('Interrupted ROM scratch did not restore')
            hosts.append(checked)
    controls=[]
    # Real executable mutations: read translated code, mirror the wrong ROM half.
    for name,case,old,new in (
        ('translated-not-original','rom-bd-1-80c0-00','lda f:$018000,x','lda f:$008000,x'),
        ('wrong-upper-bank','rom-bd-1-dfff-03','and #$7FFF','and #$3FFF')):
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name)
        create_native(folder,plan,expected_initial(plan))
        path=folder/'timeline_rom.inc';text=path.read_text()
        if old not in text:raise RuntimeError('Absent mutation anchor')
        path.write_text(text.replace(old,new))
        actual=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048)
        try:compare(plan,references[case],actual)
        except (RuntimeError,ValueError):controls.append(dict(name=name,rejected=True))
        else:raise RuntimeError('Bad ROM reader passed independent comparison')
    faults=[]
    for plan in fault_cases():
        actual=native_capture(snes,out/plan['name'],plan)
        faults.append(unchanged_on_fault(plan,actual))
    plan=fault_cases()[0];folder=out/'mutant-write-guard'
    create_native(folder,plan,expected_initial(plan))
    path=folder/'timeline_rom.inc';text=path.read_text()
    if text.count('    lda MR_WRITE')!=1:raise RuntimeError('Nonunique write-guard anchor')
    path.write_text(text.replace('    lda MR_WRITE','    lda #0'))
    actual=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048)
    try:unchanged_on_fault(plan,actual)
    except ValueError:controls.append(dict(name='missing-write-guard',rejected=True))
    else:raise RuntimeError('Disabled ROM-write guard passed')
    rows=results+hosts
    report=dict(passed=True,memory_model='nrom-32k',plans=len(plans),scenarios=len(rows),
                dependent_boundaries=sum(r['steps'] for r in rows),
                compared_bytes=sum(r['record_bytes'] for r in rows),
                no_request_plain_comparisons=plain_count,host_scenarios=len(hosts),
                host_interrupts=sum(r['host']['count'] for r in hosts),
                read_opcode_variants=len({p['name'].split('-')[1] for p in plans if 'jmp' not in p['name']}),
                negative_controls=controls,fault_guards=faults,
                cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in
                       [('nes_plain',plain),('nes_stimulus',probe),('snes',snes)]},
                production_runtime_changed=False,mmc5_mapping_implemented=False,
                scope='Authored immutable NROM-256 data reads and RAM, instruction costs and sampled guest requests under real emulated host NMIs. Not MMC5, bus transactions, physical pin timing, DMA/DMC, CV3 scheduling or speed.',
                results=results,host_results=hosts)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();result=verify(args.nes_plain.resolve(),args.nes_probe.resolve(),args.snes_core.resolve(),args.out.resolve())
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','host_results')},indent=2))
