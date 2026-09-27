#!/usr/bin/env python3
"""Independent final states for extended MMC5 nametable behavior.

NES execution is unmodified Nestopia; it receives ordinary program inputs only.
Full ExRAM and selected actual mapper registers are now checked alongside the
palette endpoint. Per-instruction native records still test host noninterference,
not independent NES timing. No rendering, PPU-status or event scheduling claim.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from palette_timeline import create_nes,create_native,underlying
from nametable_palette_fixture import cases,guard_cases,color_case,map_case
from timeline_fixture import expected_initial
from verify_palette_timeline import capture,compare,check_host
from verify_palette_controls import prefix_rom,compare_guard
from verify_ppu_blank import exact_hex
from mmc5_timeline import reassemble
from route_evidence import atomic_json

EXTRA={'nametable_registers':4,'exram':1024}


def compare_extra(reference,native):
    for key,size in EXTRA.items():
        a=exact_hex(reference.get(key),size,'reference '+key)
        b=exact_hex(native.get(key),size,'native '+key)
        if a!=b:raise RuntimeError('Independent '+key+' differs')
    # Bind final logical map/tile/color to the last captured native state too.
    count=native.get('completed_steps')
    if type(count) is not int or not 1<=count<=31:raise ValueError('Invalid retired count')
    cpu=exact_hex(native['records'][count-1],2080,'retired CPU record')
    ppu=exact_hex(native['ppu_records'][count-1],16,'retired PPU record')
    actual=exact_hex(native['nametable_registers'],4,'native mapper state')
    if actual!=bytes((cpu[28],))+ppu[10:13]:
        raise ValueError('Final mapper state differs from retired native capture')


def run_case(nes,snes,out,plan):
    d=out/plan['name']
    ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
    initial=expected_initial(underlying(plan));rows=[];baseline=None;nmis=0
    for mode in (None,'free'):
        where=d/('native' if mode is None else 'host')
        rom=create_native(where,plan,initial,**({'host_mode':mode} if mode else {}))
        actual=capture('native',snes,rom,where/'capture.json',host=mode is not None)
        row=compare(plan,ref,actual);compare_extra(ref,actual)
        row['independent_endpoint_bytes']+=sum(EXTRA.values())
        rows.append(row)
        if mode is None:baseline=actual
        else:nmis+=check_host(baseline,actual,mode)
    return rows,nmis


def run(nes,snes,out,*,limit=None,jobs=2):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Require 1..4 isolated workers')
    plans=cases()
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(plans):raise ValueError('Invalid smoke limit')
        plans=plans[:limit]
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'nametable-palette-verification.json';summary.unlink(missing_ok=True)
    atomic_json(out/'plans.json',plans);done={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        future={pool.submit(run_case,nes,snes,out,p):i for i,p in enumerate(plans)}
        for f in as_completed(future):
            i=future[f];done[i]=f.result()
            print('Nametable',len(done),'/',len(plans),plans[i]['name'],flush=True)
            atomic_json(out/'progress.json',dict(complete=False,programs=len(done)))
    results=[];nmis=0
    for i in range(len(plans)):
        rows,count=done[i];results.extend(rows);nmis+=count
    report=dict(passed=True,complete_matrix=limit is None,programs=len(plans),scenarios=len(results),
                independent_endpoint_bytes=sum(x['independent_endpoint_bytes'] for x in results),
                host_interrupts=nmis,endpoint_bytes=5173,results=results,
                cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nestopia',nes),('snes',snes)]},
                scope='Blanked final CPU/PPU/palette/CIRAM/ExRAM and selected mapper state. Not per-instruction NES timing, rendering, events, OAM, DMA or gameplay.')
    atomic_json(summary,report);return report


def controls(nes,snes,out,fce):
    out.mkdir(parents=True,exist_ok=True)
    summary=out/'nametable-palette-controls.json';summary.unlink(missing_ok=True)
    hosts=[];mutants=[];guards=[]
    for plan in (color_case(0xFD),map_case(0xAA,3,2)):
        d=out/plan['name'];ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
        initial=expected_initial(underlying(plan))
        base=capture('native',snes,create_native(d/'native',plan,initial),d/'native/capture.json')
        compare(plan,ref,base);compare_extra(ref,base)
        for mode in ('cost','time','capture','nested'):
            where=d/mode;rom=create_native(where,plan,initial,host_mode=mode)
            actual=capture('native',snes,rom,where/'capture.json',host=True)
            compare(plan,ref,actual);compare_extra(ref,actual)
            hosts.append(dict(name=plan['name'],mode=mode,host_interrupts=check_host(base,actual,mode)))
    for name,plan,old,new in (
        ('upper-color',color_case(0xFD),'    and #3\n    sta PV+12','    nop\n    nop\n    sta PV+12'),
        ('nonzero-source',map_case(0xAA,3,2),'zero_source:\n    ; Source 2 is disconnected from CPU ExRAM in the admitted modes 2/3.\n    lda #0',
         'zero_source:\n    lda #$A5'),
        ('wrong-quadrant',map_case(0xE4,2,3),'    sta PV+10\n    rts','    eor #$30\n    sta PV+10\n    rts')):
        d=out/('mutant-'+name);ref=capture('nes',nes,create_nes(d/'nes',plan),d/'nes/capture.json')
        create_native(d/'native',plan,expected_initial(underlying(plan)))
        p=d/'native/mmc5_ppu_blank.inc';text=p.read_text()
        if text.count(old)!=1:raise RuntimeError('Nonunique mutation anchor')
        p.write_text(text.replace(old,new))
        actual=capture('native',snes,reassemble(d/'native'),d/'native/capture.json')
        if actual['complete'] is not True or actual['status'] or actual['completed_steps']!=plan['steps']:
            raise RuntimeError('Mutant crashed instead of testing wrong results')
        try:compare(plan,ref,actual);compare_extra(ref,actual)
        except (RuntimeError,ValueError) as exc:mutants.append(dict(name=name,rejected=True,completed=True,reason=str(exc)))
        else:raise RuntimeError('Incorrect native mapping passed')
    for plan,stop,retired in guard_cases():
        d=out/plan['name'];ref=capture('nes',nes,prefix_rom(d/'nes-prefix',plan,stop),d/'nes-prefix/capture.json',stop_pc=stop)
        actual=capture('native',snes,create_native(d/'native',plan,expected_initial(underlying(plan))),d/'native/capture.json')
        row=compare_guard(plan,ref,actual,stop,retired);compare_extra(ref,actual)
        row['independent_prefix_bytes']+=sum(EXTRA.values());guards.append(row)
    # The two unmodified references disagree on the write path. Preserve both
    # results; native source-2 writes remain a refusal, not a guessed mapping.
    from native_fixture import Program
    from ppu_blank_fixture import put,address
    from palette_timeline_fixture import seal
    p=Program(0xE100);put(p,0x5105,0xAA);address(p,0x2000);put(p,0x2007,0x77)
    put(p,0x5105,0);address(p,0x2000)
    p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    plan=seal(p,'nt-zero-write-disagreement');d=out/plan['name']
    rom=create_nes(d,plan);reference=capture('nes',nes,rom,d/'nestopia.json')
    subprocess.run([sys.executable,str(Path(__file__).with_name('verify_palette_controls.py')),
                    '--fce-sample','--nes-core',str(fce),'--rom',str(rom),'--out',str(d/'fceumm.json')],
                   check=True,timeout=90,stdout=subprocess.DEVNULL)
    other=json.loads((d/'fceumm.json').read_text())
    a=exact_hex(reference['cpu_ram'],2048,'Nestopia RAM')
    b=exact_hex(other['cpu_ram'],2048,'FCEUmm RAM')
    differences=[dict(address=i,nestopia=x,fceumm=y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    if not differences:raise RuntimeError('Saved unsupported-write disagreement did not reproduce')
    report=dict(passed=True,host_results=hosts,negative_controls=mutants,guards=guards,
                source2_write_diagnostic=dict(accuracy_resolved=False,excluded_from_acceptance=True,
                    differences=differences,cores={'nestopia':reference['core_sha256'],'fceumm':other['core_sha256']}),
                host_interrupts=sum(r['host_interrupts'] for r in hosts),
                zero_source_writes_supported=False,rendering_exram_modes_supported=False)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('nes-core','snes-core','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--fce-core',type=Path)
    p.add_argument('--controls',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args();nes=a.nes_core.resolve();snes=a.snes_core.resolve();out=a.out.resolve()
    if a.controls and a.fce_core is None:p.error('--controls requires --fce-core')
    result=controls(nes,snes,out,a.fce_core.resolve()) if a.controls else run(nes,snes,out,limit=a.limit,jobs=a.jobs)
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
