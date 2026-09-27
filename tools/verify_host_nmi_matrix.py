#!/usr/bin/env python3
"""Independent guest streams under real hardware-emulated SNES host NMIs."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import subprocess
import sys
from route_evidence import atomic_json
from verify_timeline import verify as verify_timeline, compare, compare_rebased
from verify_host_nmi import execute, check_host, check_registers
from timeline_program import create_native, generate
from timeline_fixture import cases, expected_initial
from timeline_host import MODES, PROTECTED, replace_once
from host_nmi_fixture import create as create_registers, reassemble


def execute_registers(core: Path,rom: Path,out: Path) -> dict:
    subprocess.run([sys.executable,str(Path(__file__).with_name('verify_host_nmi.py')),
                    '--sample','registers','--core',str(core),'--rom',str(rom),'--out',str(out)],
                   check=True,timeout=90,stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def verify(plain: Path,probe: Path,snes: Path,out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'host-nmi-verification.json';summary.unlink(missing_ok=True)
    retained=verify_timeline(plain,probe,snes,out/'retained-timeline')
    plan=cases();references={};baselines={};results=[]
    for case in plan:
        folder=out/'retained-timeline'/case['name']
        references[case['name']]=json.loads((folder/'nes/capture.json').read_text())
        baselines[case['name']]=execute(snes,folder/'snes/fixture.sfc',folder/'baseline-context.json',case['steps'],host_expected=False)
        compare(case,references[case['name']],baselines[case['name']])
    tasks=[(case,'free') for case in plan]
    tasks.extend((case,mode) for case in plan[6:12] for mode in MODES[1:]
                 if mode!='stack' or case['events'])
    for case,mode in tasks:
        print('Checking host NMI',case['name'],mode,flush=True)
        folder=out/'host'/case['name']/mode
        rom=create_native(folder,case,expected_initial(case),host_mode=mode)
        native=execute(snes,rom,folder/'capture.json',case['steps'])
        result=check_host(case,references[case['name']],native,mode)
        if native['protected_memory']!=baselines[case['name']]['protected_memory']:
            raise RuntimeError('Host NMI changed the final protected scratch context')
        result['protected_bytes_checked']=sum(n for _,n in PROTECTED)
        results.append(result)
        atomic_json(out/'progress.json',dict(complete=False,results=results))
    register_results=[]
    for nested in (False,True):
        for mirror in (False,True):
            folder=out/'registers'/f'n{int(nested)}-b{int(mirror)}'
            print('Checking full native context',nested,mirror,flush=True)
            rom=create_registers(folder,nested=nested,mirror=mirror)
            report=execute_registers(snes,rom,folder/'capture.json')
            register_results.append(check_registers(report,nested=nested,mirror=mirror))
    # Interrupt between the low-word ADC store and its carry propagation.
    epoch_results=[];case=plan[0];reference=references[case['name']]
    code=generate(bytes.fromhex(case['code']),case['origin'],case['starts'])
    for epoch in (0xFFF0,0x12FFF0):
        body=replace_once(code,f'ins_{case["origin"]:04x}:',f'ins_{case["origin"]:04x}:\n    lda #${epoch>>16:04X}\n    sta GT+2\n    lda #${epoch&65535:04X}\n    sta GT')
        folder=out/f'epoch-{epoch:08x}'
        rom=create_native(folder,case,expected_initial(case),program_text=body,host_mode='time')
        native=execute(snes,rom,folder/'capture.json',case['steps'])
        compare_rebased(case,reference,native,epoch)
        normalized=copy.deepcopy(native)
        for i,text in enumerate(normalized['records']):
            row=bytearray.fromhex(text);now=int.from_bytes(row[:4],'little')
            row[:4]=(now-epoch).to_bytes(4,'little');normalized['records'][i]=row.hex()
        epoch_results.append(dict(epoch=epoch,**check_host(case,reference,normalized,'time')))
    controls=[]
    # These tests execute wrong binaries; parser mutation alone is insufficient.
    folder=out/'mutant-lost-scratch';case=plan[9]
    create_native(folder,case,expected_initial(case),host_mode='capture')
    source=folder/'timeline_host_nmi.inc'
    source.write_text(replace_once(source.read_text(),'    sta f:$7E18C0,x','    nop ; deliberately fail to restore the saved GT word'))
    actual=execute(snes,reassemble(folder),folder/'capture.json',case['steps'])
    try:check_host(case,references[case['name']],actual,'capture')
    except (ValueError,RuntimeError):controls.append(dict(name='lost-scratch',rejected=True,marker=actual['marker'],status=actual['status']))
    else:raise RuntimeError('Missing scratch restoration passed')
    folder=out/'mutant-accumulator-high'
    create_registers(folder,nested=True,mirror=True);source=folder/'timeline_host_nmi.inc'
    source.write_text(replace_once(source.read_text(),'    pla\n    rti','    pla\n    and #$00FF ; deliberately discard the hidden accumulator byte\n    rti'))
    actual=execute_registers(snes,reassemble(folder),folder/'capture.json')
    try:check_registers(actual,nested=True,mirror=True)
    except (ValueError,RuntimeError):controls.append(dict(name='accumulator-high',rejected=True))
    else:raise RuntimeError('Accumulator corruption passed')
    folder=out/'mutant-no-host';case=plan[0]
    create_native(folder,case,expected_initial(case),host_mode='free');source=folder/'fixture.s'
    source.write_text(replace_once(source.read_text(),'    lda #$80\n    sta $4200','    lda #$00\n    sta $4200'))
    actual=execute(snes,reassemble(folder),folder/'capture.json',case['steps'])
    compare(case,references[case['name']],actual) # guest equality is deliberately insufficient
    try:check_host(case,references[case['name']],actual,'free')
    except ValueError:controls.append(dict(name='no-host-interrupts',rejected=True))
    else:raise RuntimeError('Vacuous host-interrupt test passed')
    # A third real host NMI must fail explicitly before taking another snapshot.
    folder=out/'guard-nesting';case=plan[9]
    create_native(folder,case,expected_initial(case),host_mode='nested');source=folder/'fixture.s'
    source.write_text(replace_once(source.read_text(),'    cmp #1\n    bne no_nested','    cmp #3\n    bcs no_nested'))
    actual=execute(snes,reassemble(folder),folder/'capture.json',case['steps'])
    if actual['host']['fault']!=1 or actual['host']['peak']!=2 or actual['host']['low_canary']!=0xA5 or actual['host']['high_canary']!=0x5A:
        raise RuntimeError('Excessive nesting guard failed to report and bound the fault')
    try:check_host(case,references[case['name']],actual,'nested')
    except (ValueError,RuntimeError):pass
    else:raise RuntimeError('Fault-bearing nested execution passed')
    result=dict(passed=True,scenarios=len(results),dependent_boundaries=sum(r['steps'] for r in results),
                compared_guest_state_bytes=sum(r['record_bytes'] for r in results),
                final_protected_bytes=sum(r['protected_bytes_checked'] for r in results),
                host_interrupts=sum(r['host']['count'] for r in results),
                deliberate_interruptions=sum(r['host']['wait_hits'] for r in results),
                nested_interruptions=sum(r['host']['nested_wait_hits'] for r in results),
                register_checks=register_results,register_cases=sum(r['cases'] for r in register_results),
                register_bytes=sum(r['register_bytes'] for r in register_results),
                register_scratch_bytes=sum(r['scratch_bytes'] for r in register_results),
                epoch_checks=epoch_results,epoch_boundaries=sum(r['steps'] for r in epoch_results),
                negative_controls=controls,nesting_guard=dict(rejected=True,host=actual['host']),
                retained_timeline={k:v for k,v in retained.items() if k!='results'},
                results=results,production_runtime_changed=False,guest_event_policy_changed=False,
                cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nes_plain',plain),('nes_stimulus',probe),('snes',snes)]},
                scope='Hardware-emulated SNES vblank context preservation, with explicit native WAI stress and nested host NMI. Guest request policy remains authored after-instruction stimulation. Not a CV3 scheduler, physical-console validation, DMA/DMC model or speedup.')
    atomic_json(summary,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();report=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
