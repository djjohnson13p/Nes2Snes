#!/usr/bin/env python3
"""Independent banked program/data execution with explicit mapper-profile limits.

No intermediate mapper decision, expected register or capture is supplied to the
native machine. Test code writes real MMC5 registers on the original NES core.
"""
from pathlib import Path
import argparse
import hashlib
import json
from mmc5_timeline_fixture import cases, fault_cases, read_case, part
from mmc5_timeline import create_native, reassemble
from timeline_fixture import expected_initial
from verify_ram_timeline import nes_capture, native_capture
from verify_host_nmi import execute, check_host
from verify_timeline import compare
from route_evidence import atomic_json


def guard(plan: dict, report: dict, status: int=5) -> dict:
    done=report.get('completed_steps')
    if (report.get('complete') is not False or report.get('marker')!=0xEE or report.get('status')!=status
            or type(done) is not int or not 0<done<plan['steps']):
        raise ValueError('Banked guard did not refuse execution')
    previous=bytes.fromhex(report['records'][done-1]);ram=bytes.fromhex(report['final_guest_ram'])
    context=bytes.fromhex(report['final_guest_context']);protected=bytes.fromhex(report['protected_memory'])
    if len(previous)!=2080 or len(context)!=32 or len(ram)!=2048 or len(protected)!=132:
        raise ValueError('Incomplete refusal evidence')
    if previous[32:]!=ram or previous[:14]!=context[:14] or previous[20:24]!=protected[0x38:0x3C]:
        raise ValueError('Refused instruction changed guest state or effective mapping')
    return dict(name=plan['name'],rejected=True,completed_steps=done,status=status,
                unchanged_ram_bytes=2048,unchanged_context_bytes=14,unchanged_mapping_bytes=4)


def mode_zero_control(plain: Path, probe: Path, out: Path) -> dict:
    # The pinned reference uses $5115 in mode 0 whereas the documented mapper
    # selects $5117. Preserve that disagreement; do not adopt the reference bug.
    # A duplicate authored tail keeps the original core executing valid code
    # after its discrepant mode-0 switch, without altering the mapper itself.
    plan=read_case(0xBD,0)
    plan['bank_code']=[dict(bank=7,origin=plan['origin'],code=plan['code'],starts=plan['starts'])]
    a=nes_capture(probe,out/'nes',plan,probe=True);b=nes_capture(plain,out/'plain',plan,probe=False)
    if b!={k:v for k,v in a.items() if k!='records'}:raise RuntimeError('Mode-zero observer changed execution')
    row=bytes.fromhex(a['records'][8])
    observed=list(row[20:24]);documented=[28,29,30,31]
    if observed!=[4,5,6,7] or observed==documented:
        raise RuntimeError('Pinned mode-zero diagnostic behavior changed; review the oracle boundary')
    return dict(reference_noninterference=True,observed_slots=observed,documented_slots=documented,
                disagreement_preserved=True,accepted_as_correct_mapping=False,
                scope='Pinned FCEUmm mode-0 register selection disagreement; native profile rejects mode 0.')


def verify(plain: Path, probe: Path, snes: Path, out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True);summary=out/'mmc5-timeline-verification.json';summary.unlink(missing_ok=True)
    plans=cases();atomic_json(out/'plans.json',plans);rows=[];hosts=[];references={};baselines={};inert=0
    banks_seen=set();switches=0;entry_banks=set();read_forms=set()
    for num,plan in enumerate(plans):
        print(f'MMC5 {num+1}/{len(plans)} {plan["name"]}',flush=True)
        folder=out/plan['name'];a=nes_capture(probe,folder/'nes',plan,probe=True)
        b=native_capture(snes,folder/'native',plan);result=compare(plan,a,b)
        if plan['name'].startswith('m5-read-'):
            op=plan['name'].split('-')[2]
            if not plan['events'] and op not in result['executed_opcodes']:raise RuntimeError('Declared read opcode not exercised')
            read_forms.add(op)
        if not plan['events']:
            control=nes_capture(plain,folder/'plain',plan,probe=False)
            if control!={k:v for k,v in a.items() if k!='records'}:raise RuntimeError('Observer/stimulus core changed no-request NES execution')
            inert+=1
        n=plan['prg_banks']*8192;original=(folder/'nes/fixture.nes').read_bytes()[16:16+n]
        if (folder/'native/fixture.sfc').read_bytes()[32768:32768+n]!=original:
            raise RuntimeError('Original PRG bank image differs')
        h=native_capture(snes,folder/'host-free',plan,mode='free');host=check_host(plan,a,h,'free')
        if h['protected_memory']!=b['protected_memory']:raise RuntimeError('Host NMI changed mapper or resolver state')
        references[plan['name']]=a;baselines[plan['name']]=b;rows.append(result);hosts.append(host)
        last=None
        for text in a['records']:
            record=bytes.fromhex(text);mapping=record[20:24]
            banks_seen.update(mapping);entry_banks.add(record[24])
            if last is not None and mapping!=last:switches+=1
            last=mapping
        atomic_json(out/'progress.json',dict(complete=False,plans_completed=len(rows)))
    stress=['m5-code-bank-identity-nmi','m5-self-remap-vector','m5-read-b1-m2-r85-b32-irq']
    for name in stress:
        plan=next(p for p in plans if p['name']==name)
        for mode in ('cost','time','capture','nested'):
            b=native_capture(snes,out/'stress'/name/mode,plan,mode=mode)
            h=check_host(plan,references[name],b,mode)
            if b['protected_memory']!=baselines[name]['protected_memory']:raise RuntimeError('Targeted host NMI changed mapper state')
            hosts.append(h)
    mutants=[]
    for name,case,file,old,new in (
        ('pc-without-bank','m5-code-bank-identity','fixture.s','    cmp f:Banks,x','    lda #0'),
        ('unaligned-pair','m5-read-bd-m2-r85-b32','mmc5_prg.inc','    and #$FE','    nop\n    nop'),
        ('stale-vector','m5-self-remap-vector','guest_timeline.inc','    lda #$FFFA\n    jsr MapperRead\n.a8\n    sta GI+14',
         "    lda #<TimelineNMI\n    sep #$20\n.a8\n    sta GI+14")):
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name)
        create_native(folder,plan,expected_initial(plan));p=folder/file;text=p.read_text()
        if text.count(old)!=1:raise RuntimeError('Mutation anchor changed')
        p.write_text(text.replace(old,new));r=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,ram_bytes=2048)
        try:compare(plan,references[case],r)
        except (RuntimeError,ValueError):mutants.append(dict(name=name,rejected=True,marker=r['marker'],status=r['status']))
        else:raise RuntimeError('Broken bank implementation passed')
    faults=[]
    for plan in fault_cases():
        r=native_capture(snes,out/plan['name'],plan)
        faults.append(guard(plan,r,0xE1 if plan['name'].endswith('unobserved-bank') else 5))
    mode_zero=mode_zero_control(plain,probe,out/'mode-zero-disagreement')
    all_rows=rows+hosts
    result=dict(passed=True,plans=len(plans),scenarios=len(all_rows),
                dependent_boundaries=sum(r['steps'] for r in all_rows),compared_bytes=sum(r['record_bytes'] for r in all_rows),
                no_request_plain_comparisons=inert,host_scenarios=len(hosts),host_interrupts=sum(r['host']['count'] for r in hosts),
                admitted_prg_modes=[1,2,3],read_opcode_forms=len(read_forms),physical_rom_banks_observed=sorted(banks_seen),
                physical_execution_banks_observed=sorted(entry_banks),observed_slot_changes=switches,
                negative_controls=mutants,fault_guards=faults,mode_zero_reference_disagreement=mode_zero,
                cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('nes_plain',plain),('nes_mmc5_stimulus',probe),('snes',snes)]},
                production_runtime_changed=False,new_cv3_replay_performed=False,
                scope='Authored MMC5 PRG-ROM modes 1/2/3, bank-qualified code, raw data and current vectors on the protected timeline. Not PRG RAM, CHR, mapper IRQ/audio, bus cycles, physical event scheduling, DMA/DMC, CV3 integration or speed.',
                results=rows,host_results=hosts)
    atomic_json(summary,result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();r=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in r.items() if k not in ('results','host_results')},indent=2))
