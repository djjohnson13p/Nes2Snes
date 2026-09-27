#!/usr/bin/env python3
"""Execute authored CHR-ROM transfers against actual original mapping/PPU state."""
from pathlib import Path
import argparse
import copy
import hashlib
from chr_blank_fixture import cases,fault_cases
from mmc5_chr_blank import PROFILE,create_native,chr_image
from timeline_fixture import expected_initial
from verify_ram_timeline import nes_capture
from verify_host_nmi import execute,check_host
from verify_timeline import compare
from verify_wram_timeline import check_ram
from verify_cpu_io_timeline import check_exram
from verify_ppu_blank import check_ppu,exact_hex,guard as ppu_guard
from mmc5_timeline import reassemble
from route_evidence import atomic_json


def packed_registers(record):
    r=exact_hex(record,48,'CHR record')
    if any(r[34:]):raise ValueError('Nonzero CHR padding')
    low=bytes(r[2+2*i] for i in range(8))
    highs=[]
    for group in range(2):
        values=[r[3+2*(group*4+i)] for i in range(4)]
        if any(v>3 for v in values):raise ValueError('Out-of-range CHR bank register')
        highs.append(sum(v<<(i*2) for i,v in enumerate(values)))
    return low+bytes(highs)+bytes((r[1],))


def check_chr(plan,reference,native):
    a,b=reference.get('chr_records'),native.get('chr_records')
    if not isinstance(a,list) or len(a)!=plan['steps']+1 or not isinstance(b,list) or len(b)!=plan['steps']:
        raise ValueError('Incomplete CHR instruction records')
    initial=exact_hex(a[0],48,'initial CHR')
    if initial[0]!=plan['chr_mode'] or packed_registers(a[0])!=bytes(11):
        raise ValueError('Original CHR boot differs from declared state')
    for i,(x,y) in enumerate(zip(a[1:],b),1):
        first=exact_hex(x,48,'reference CHR');second=exact_hex(y,48,'native CHR')
        if first!=second:raise RuntimeError(f'{plan["name"]}: CHR mapping step {i}: {first.hex()} != {second.hex()}')
        if first[0]!=plan['chr_mode'] or first[1]>3:raise ValueError('Unsupported live CHR mode/latch')
        packed_registers(x)
        if any(int.from_bytes(first[j:j+2],'little')>=plan['chr_banks'] for j in range(18,34,2)):
            raise ValueError('Mapped CHR bank outside cartridge')
    if exact_hex(native.get('chr_registers'),11,'final CHR registers')!=packed_registers(a[-1]):
        raise RuntimeError('Final CHR bank state differs from endpoint')
    return {'chr_state_bytes':plan['steps']*48}


def native_capture(core,folder,plan,mode=None):
    rom=create_native(folder,plan,expected_initial(plan),host_mode=mode)
    original=(folder/'original/fixture.nes').read_bytes()
    count=plan['prg_banks']*8192;data=chr_image(plan['chr_banks'])
    if original[16+count:]!=data or rom.read_bytes()[32768+count:32768+count+len(data)]!=data:
        raise RuntimeError('Original CHR image differs between execution inputs')
    return execute(core,rom,folder/'capture.json',plan['steps'],host_expected=mode is not None,
                   ram_bytes=2048,cartridge_bytes=32768,exram=True,ppu_blank=True,chr_blank=True)


def check_all(plan,reference,native,mode=None):
    row=compare(plan,reference,native) if mode is None else check_host(plan,reference,native,mode)
    row.update(check_ram(reference,native));row.update(check_exram(reference,native))
    row.update(check_ppu(plan,reference,native));row.update(check_chr(plan,reference,native))
    return row


def guard(plan,native,previous):
    row=ppu_guard(plan,native,previous)
    if exact_hex(native.get('chr_registers'),11,'guard CHR')!=packed_registers(previous['chr_records'][-1]):
        raise ValueError('Guard changed CHR bank state')
    return dict(row,chr_register_bytes_unchanged=11)


def verify(plain,probe,snes,out):
    out.mkdir(parents=True,exist_ok=True);summary=out/'chr-blank-verification.json';summary.unlink(missing_ok=True)
    plans=cases();atomic_json(out/'plans.json',plans);rows=[];hosts=[];refs={};natives={};controls=0
    for i,plan in enumerate(plans):
        print(f'CHR {i+1}/{len(plans)} {plan["name"]}',flush=True)
        folder=out/plan['name'];a=nes_capture(probe,folder/'nes',plan,probe=True);n=native_capture(snes,folder/'native',plan)
        rows.append(check_all(plan,a,n));refs[plan['name']]=a;natives[plan['name']]=n
        if not plan['events']:
            c=nes_capture(plain,folder/'plain',plan,probe=False)
            omitted={'records','initial_cartridge_ram','cartridge_ram','initial_exram','exram','ppu_records','initial_ciram','ciram','chr_records'}
            if c!={k:v for k,v in a.items() if k not in omitted}:raise RuntimeError('CHR observer changed original execution')
            controls+=1
        h=native_capture(snes,folder/'host-free',plan,'free');hosts.append(check_all(plan,a,h,'free'))
        if h['protected_memory']!=n['protected_memory']:raise RuntimeError('Host changed protected scratch')
        atomic_json(out/'progress.json',dict(complete=False,programs_completed=len(rows)))
    for name in ('chr-latch-m3','chr-write-ignored','chr-guest-nmi'):
        plan=next(p for p in plans if p['name']==name)
        for mode in ('cost','time','capture','nested'):
            h=native_capture(snes,out/'stress'/name/mode,plan,mode);hosts.append(check_all(plan,refs[name],h,mode))
            if h['protected_memory']!=natives[name]['protected_memory']:raise RuntimeError('Targeted host changed scratch')
    changes=(('raw-bank','chr-latch-m3','mmc5_chr_blank.inc','    adc #ChrStartBank','    adc #1'),
             ('live-high-bits','chr-latch-m3','mmc5_chr_blank.inc','    lda CR+8,x','    lda CR+10'),
             ('unbuffered','chr-write-ignored','mmc5_ppu_blank.inc','    lda PV+8\n    sta MR_VALUE','    lda PV+13\n    sta MR_VALUE'))
    mutants=[]
    for name,case,file,old,new in changes:
        plan=next(p for p in plans if p['name']==case);folder=out/('mutant-'+name)
        create_native(folder,plan,expected_initial(plan));p=folder/file;t=p.read_text()
        if t.count(old)!=1:raise RuntimeError('Changed mutation anchor')
        p.write_text(t.replace(old,new))
        n=execute(snes,reassemble(folder),folder/'capture.json',plan['steps'],host_expected=False,
                  ram_bytes=2048,cartridge_bytes=32768,exram=True,ppu_blank=True,chr_blank=True)
        if n.get('marker')!=0x5A:raise RuntimeError('Mutant crashed; not a wrong-result control')
        try:check_all(plan,refs[case],n)
        except (RuntimeError,ValueError):mutants.append(dict(name=name,rejected=True,completed=True))
        else:raise RuntimeError('Mutant passed')
    guards=[]
    for plan in fault_cases():
        folder=out/plan['name'];n=native_capture(snes,folder/'native',plan)
        before=copy.deepcopy(plan);before['steps']=n['completed_steps']
        a=nes_capture(probe,folder/'prior',before,probe=True);guards.append(guard(plan,n,a))
    all_rows=rows+hosts
    report=dict(passed=True,profile=PROFILE,plans=len(plans),scenarios=len(all_rows),
        boundaries=sum(r['steps'] for r in all_rows),cpu_state_bytes=sum(r['record_bytes'] for r in all_rows),
        ppu_state_bytes=sum(r['ppu_register_bytes'] for r in all_rows),chr_state_bytes=sum(r['chr_state_bytes'] for r in all_rows),
        final_ciram_bytes=sum(r['final_ciram_bytes'] for r in all_rows),
        final_exram_bytes=sum(r['exram_bytes_checked'] for r in all_rows),final_cartridge_bytes=sum(r['cartridge_bytes_checked'] for r in all_rows),
        no_request_controls=controls,host_scenarios=len(hosts),host_interrupts=sum(r['host']['count'] for r in hosts),
        negative_controls=mutants,fault_guards=guards,
        cores={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('nes_plain',plain),('chr_probe',probe),('snes',snes)]},
        scope='Blanked set-A CHR-ROM transfers; fixed CHR size per run. No set B, live size changes, pixel rendering, event/stall timing, production CV3 change or new game replay.',
        results=rows,host_results=hosts)
    atomic_json(summary,report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('nes-plain','nes-probe','snes-core','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();r=verify(a.nes_plain.resolve(),a.nes_probe.resolve(),a.snes_core.resolve(),a.out.resolve())
    print({k:v for k,v in r.items() if k not in ('results','host_results')})
