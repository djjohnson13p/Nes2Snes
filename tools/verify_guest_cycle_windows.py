#!/usr/bin/env python3
"""Close a full authored NES instruction window with separate interrupt costs.

Original hardware deadlines are observed here, never fed back into either core.
An OAM-DMA case is deliberately rejected by instruction-only accounting.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from guest_cycles import account_window
from native_fixture import Program,write_program
from libretro_runner import Runner
from verify_guest_cycles import CycleObserver,sample_nes,check_nes,instruction,native_run,check_native
from route_evidence import atomic_json


def create(out: Path) -> dict:
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0)
    for address in (0x2000,0x2001,0x4010,0x4015):p.op('STA','abs',address)
    for address in (0x80,0x81,0x82):p.op('STA','zp',address)
    p.op('LDA','imm',0x40);p.op('STA','abs',0x4017)
    p.op('LDX','imm',2);p.label('wait');p.op('BIT','abs',0x2002);p.op('BPL','rel','wait')
    p.op('DEX');p.op('BNE','rel','wait');p.op('LDA','imm',0x80);p.op('STA','abs',0x2000)
    p.label('loop');p.op('LDA','zp',0x80);p.op('CLC');p.op('ADC','imm',7);p.op('STA','zp',0x80)
    p.op('INC','zp',0x81);p.op('JMP','abs','loop')
    p.label('nmi');p.op('PHA');p.op('INC','zp',0x82);p.op('PLA');p.op('RTI')
    meta=write_program(out,p);meta.update(nmi_pc=p.labels['nmi'],frames=8)
    atomic_json(out/'window.json',meta);return meta


def sample(core: Path,rom: Path,out: Path,observed: bool) -> None:
    r=Runner(core,rom)
    try:
        observer=CycleObserver(r.lib,list(range(0x8000,0xFFFE)),262144) if observed else None
        images=hashlib.sha256()
        for _ in range(8):r.run(1);images.update(r.rgb().tobytes())
        ram=r.memory();data=dict(ram_sha256=hashlib.sha256(ram).hexdigest(),images_sha256=images.hexdigest(),
                                 video_callbacks=r.frames,audio_frames=r.audio_frames,nmi_counter=ram[0x82])
        if observer:data['records']=observer.finish()
        atomic_json(out,data)
    finally:r.close()


def verify(plain: Path,observed: Path,snes: Path,out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True);meta=create(out/'fixture');rom=out/'fixture/fixture.nes'
    for role,core in [('plain',plain),('observed',observed)]:
        subprocess.run([sys.executable,__file__,'--sample',role,'--core',str(core),'--rom',str(rom),'--out',str(out/(role+'.json'))],check=True,timeout=30,stdout=subprocess.DEVNULL)
    a=json.loads((out/'plain.json').read_text());b=json.loads((out/'observed.json').read_text())
    if a!={k:v for k,v in b.items() if k!='records'}:raise RuntimeError('Cycle observer altered full-window execution')
    ledger=account_window(b['records'],{meta['nmi_pc']:'nmi'})
    if not a['nmi_counter'] or len(ledger['interrupts'])!=a['nmi_counter']:
        raise RuntimeError('Interrupt entries differ from the independently executed handler counter')
    # Validate a sequence of actual pre-instruction states in the native accountant.
    picked=b['records'][:64];inputs=[instruction(row).record() for row in picked]
    check_native(inputs,[row['end']-row['start'] for row in picked],native_run(snes,out/'native-window',inputs))
    # Explicitly demonstrate that elapsed DMA time is NOT opcode execution cost.
    plan=[dict(name='external-dma',opcode=0x8D,pc=0x8100,operand=0x4014,p=0x34,x=3,y=3,pointer=0x200)]
    atomic_json(out/'dma-plan.json',plan)
    for role,core in [('plain',plain),('observed',observed)]:
        subprocess.run([sys.executable,str(Path(__file__).with_name('verify_guest_cycles.py')),'--sample',role,'--core',str(core),'--plan',str(out/'dma-plan.json'),'--out',str(out/('dma-'+role))],check=True,timeout=30,stdout=subprocess.DEVNULL)
    da=json.loads((out/'dma-plain/capture.json').read_text());db=json.loads((out/'dma-observed/capture.json').read_text())
    if da['results'][0]!={k:v for k,v in db['results'][0].items() if k!='observed'}:raise RuntimeError('DMA observer changed emulated output')
    record=db['results'][0]['observed'][0];elapsed=record['end']-record['start'];cost=instruction(record).cost()
    if elapsed<=cost:raise RuntimeError('DMA negative control did not exercise an additional delay')
    try:check_nes(da,db,plan)
    except RuntimeError:pass
    else:raise RuntimeError('Instruction-only accounting silently accepted DMA')
    result=dict(passed=True,window=ledger,same_platform_noninterference=a,
                native_window_inputs=64,dma_negative_control=dict(rejected=True,instruction_cycles=cost,
                    measured_elapsed_cycles=elapsed,unmodeled_cycles=elapsed-cost),
                scope='Eight-frame authored NES program only. Accounted instruction durations and observed NMI entries, not prediction of hardware polling/deadlines or production runtime integration.')
    atomic_json(out/'guest-cycle-window-verification.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=['plain','observed'])
    for k in ('core','rom','nes-plain','nes-observed','snes-core','out'):p.add_argument('--'+k,type=Path)
    a=p.parse_args()
    if a.sample:sample(a.core,a.rom,a.out,a.sample=='observed')
    else:print(json.dumps(verify(a.nes_plain.resolve(),a.nes_observed.resolve(),a.snes_core.resolve(),a.out.resolve()),indent=2))
