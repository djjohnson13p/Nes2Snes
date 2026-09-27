#!/usr/bin/env python3
"""Actual palette corruption controls, independent refused-prefix checks and host stress.

A guarded original prefix ends in an authored self-jump replacing the unsupported
instruction. No runtime RAM/register patches or expected intermediate states are
fed to either emulator. Only the CPU PPU-transfer endpoint is compared; this is
not a physical-event or per-instruction NES-timing oracle.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from native_fixture import Program
from ppu_blank_fixture import put,address
from palette_timeline_fixture import cases,seal,read_case,shadow_case
from palette_timeline import create_native,create_nes,underlying
from timeline_fixture import expected_initial
from mmc5_timeline import reassemble
from verify_palette_timeline import capture,compare,compare_endpoint,check_host,ENDPOINT_SIZES
from route_evidence import atomic_json
from libretro_runner import Runner


def guard_cases():
    rows=[]
    for name,op,operand,value in (('rendering','STA',0x2001,0x18),('nmi','STA',0x2000,0x80),
                                 ('status','LDA',0x2002,0),('oam','LDA',0x2004,0),
                                 ('rendering-exram','STA',0x5104,0),('chr-mode','STA',0x5101,0)):
        p=Program(0xE100);address(p,0x3F14);put(p,0x2007,0xED)
        if op=='STA':p.op('LDA','imm',value)
        stop=p.pc;retired=len(p.starts);p.op(op,'abs',operand)
        plan=seal(p,'pal-guard-'+name);rows.append((plan,stop,retired))
    return rows


def prefix_rom(out,plan,stop):
    path=create_nes(out,plan);data=bytearray(path.read_bytes())
    pos=16+(plan['prg_banks']-1)*8192+(stop&8191)
    original=data[pos:pos+3]
    if len(original)!=3:raise ValueError('Invalid prefix stop')
    data[pos:pos+3]=bytes((0x4C,stop&255,stop>>8));path.write_bytes(data)
    return path


def compare_guard(plan,reference,native,stop,retired):
    if (native.get('complete') is not False or type(native.get('status')) is not int or native['status']!=5
            or type(native.get('marker')) is not int or native.get('marker')!=0xEE or type(native.get('completed_steps')) is not int
            or native['completed_steps']!=retired):raise RuntimeError('Guard did not stop before the refused instruction')
    if int.from_bytes(bytes.fromhex(native['cpu_registers'])[:2],'little')!=stop:raise RuntimeError('Guard PC differs')
    compare_endpoint(plan,reference,native)
    return dict(name=plan['name'],rejected=True,retired=retired,status=native['status'],independent_prefix_bytes=sum(ENDPOINT_SIZES.values()))


def fce_sample(core,rom,out):
    r=Runner(core,rom)
    try:
        for _ in range(120):
            r.run(1)
            if r.memory()[0x7E]==0x5A:break
        else:raise RuntimeError('Diagnostic reference did not finish')
        atomic_json(out,dict(cpu_ram=r.memory()[:2048].hex(),frames=r.frames,
                            core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                            rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest()))
    finally:r.close()


def verify(nes,snes,fce,out):
    out.mkdir(parents=True,exist_ok=True);(out/'palette-controls.json').unlink(missing_ok=True)
    controls=[];guards=[];hosts=[]
    selected=[cases()[3],shadow_case(0xFF,0xFF,32),cases()[-2]]
    references={};baselines={}
    for plan in selected:
        folder=out/plan['name'];rom=create_nes(folder/'nes',plan);reference=capture('nes',nes,rom,folder/'nes/capture.json')
        sr=create_native(folder/'native',plan,expected_initial(underlying(plan)))
        base=capture('native',snes,sr,folder/'native/capture.json');compare(plan,reference,base)
        references[plan['name']]=reference;baselines[plan['name']]=base
        for mode in ('cost','time','capture','nested'):
            sr=create_native(folder/mode,plan,expected_initial(underlying(plan)),host_mode=mode)
            observed=capture('native',snes,sr,folder/mode/'capture.json',host=True)
            result=compare(plan,reference,observed);count=check_host(base,observed,mode)
            hosts.append(dict(mode=mode,host_interrupts=count,min_sp=observed['host']['min_sp'],**result))
    mutations=[('upper-latch',read_case(3,0xFF,0,0xC0),'    and #$C0','    and #$00'),
               ('backdrop-alias',read_case(0x14,0x2F,0,0),'    and #$000F','    and #$001F'),
               ('shadow-buffer',shadow_case(0xFF,0xFF,32),'    sta PV+8','    nop\n    nop\n    nop')]
    for name,plan,old,new in mutations:
        folder=out/('mutant-'+name);nr=create_nes(folder/'nes',plan);reference=capture('nes',nes,nr,folder/'nes/capture.json')
        create_native(folder/'native',plan,expected_initial(underlying(plan)))
        path=folder/'native/palette_timeline.inc';text=path.read_text()
        if text.count(old)!=1:raise RuntimeError('Nonunique mutant anchor')
        path.write_text(text.replace(old,new));rom=reassemble(folder/'native')
        actual=capture('native',snes,rom,folder/'native/capture.json')
        if actual['complete'] is not True or actual['status'] or actual['completed_steps']!=plan['steps']:
            raise RuntimeError('Mutation crashed; not a wrong-result control')
        try:compare(plan,reference,actual)
        except RuntimeError as exc:controls.append(dict(name=name,rejected=True,completed=True,reason=str(exc)))
        else:raise RuntimeError('Broken palette implementation passed')
    for plan,stop,retired in guard_cases():
        folder=out/plan['name'];rom=prefix_rom(folder/'nes-prefix',plan,stop)
        reference=capture('nes',nes,rom,folder/'nes-prefix/capture.json',stop_pc=stop)
        sr=create_native(folder/'native',plan,expected_initial(underlying(plan)))
        actual=capture('native',snes,sr,folder/'native/capture.json')
        guards.append(compare_guard(plan,reference,actual,stop,retired))
    # Keep a conflicting emulator result visible; never change CPU output masks.
    plan=selected[0];folder=out/'fceumm-disagreement';folder.mkdir(exist_ok=True)
    rom=create_nes(folder,plan)
    subprocess.run([sys.executable,__file__,'--fce-sample','--nes-core',str(fce),'--rom',str(rom),'--out',str(folder/'capture.json')],check=True,timeout=60,stdout=subprocess.DEVNULL)
    alternate=json.loads((folder/'capture.json').read_text());reference=references[plan['name']]
    a=bytes.fromhex(reference['cpu_ram']);b=bytes.fromhex(alternate['cpu_ram'])
    differences=[dict(address=i,nestopia=x,fceumm=y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    if not differences:raise RuntimeError('Expected retained reference diagnostic did not reproduce')
    report=dict(passed=True,targeted_host_scenarios=len(hosts),host_interrupts=sum(h['host_interrupts'] for h in hosts),
                host_results=hosts,negative_controls=controls,guards=guards,
                reference_disagreement=dict(reference_accuracy_passed=False,excluded_from_passing_counts=True,
                                            differences=differences,cores={'nestopia':hashlib.sha256(nes.read_bytes()).hexdigest(),'fceumm':alternate['core_sha256']}),
                independent_endpoint_comparison=True,per_instruction_nes_equivalence_claimed=False)
    atomic_json(out/'palette-controls.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fce-sample',action='store_true')
    for name in ('nes-core','snes-core','fce-core','rom','out'):parser.add_argument('--'+name,type=Path)
    a=parser.parse_args()
    if a.fce_sample:fce_sample(a.nes_core,a.rom,a.out)
    else:print(json.dumps(verify(a.nes_core.resolve(),a.snes_core.resolve(),a.fce_core.resolve(),a.out.resolve()),indent=2))
