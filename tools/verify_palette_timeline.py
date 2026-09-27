#!/usr/bin/env python3
"""Palette timeline versus unmodified Nestopia, using stable authored endpoints.

The primary oracle is not the earlier FCEUmm per-instruction observer: that
core has known palette-latch errors. CPU RAM, CPU registers, PPU transfer state,
CIRAM and palette RAM are independently compared at each program's final state.
Native per-instruction records only measure host-interrupt noninterference.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from libretro_runner import Runner
from palette_timeline import create_native,create_nes,underlying,PALETTE_ADDRESS
from palette_timeline_fixture import cases
from timeline_fixture import expected_initial
from palette_state import decode
from route_evidence import atomic_json
from verify_ppu_blank import exact_hex
from timeline_host import PROTECTED


def nes_sample(core,rom,out,stop_pc=None):
    if stop_pc is not None and (type(stop_pc) is not int or not 0x8000<=stop_pc<=65535):
        raise ValueError('Invalid authored prefix endpoint')
    r=Runner(core,rom)
    try:
        for _ in range(120):
            r.run(1)
            if stop_pc is None:
                if r.memory()[0x7E]==0x5A:break
            elif int.from_bytes(bytes.fromhex(decode(r.state())['cpu_registers'])[:2],'little')==stop_pc:
                break
        else:raise RuntimeError('Original program did not complete')
        raw=r.state();out.with_suffix('.nst').write_bytes(raw);state=decode(raw)
        if bytes.fromhex(state['cpu_ram'])!=r.memory()[:2048]:raise RuntimeError('Serialized CPU RAM differs')
        state.update(core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),frames=r.frames)
        atomic_json(out,state)
    finally:r.close()


def native_sample(core,rom,out,steps,host):
    # Use one core/session only; the existing capture helper returns after
    # completion. Palette RAM is sampled via a dedicated small wrapper below.
    if type(steps) is not int or not 1<=steps<=31 or type(host) is not bool:
        raise ValueError('Invalid native capture shape or host gate')
    r=Runner(core,rom)
    try:
        for _ in range(2048):
            r.run(1);ram=r.memory()
            if ram[0x1FFF] in (0x5A,0xEE) or (host and ram[0x1D06]):break
        else:raise RuntimeError('Native program did not complete')
        context=ram[0x18C0:0x18E0];pstate=ram[0x1C20:0x1C2A]
        result=dict(complete=ram[0x1FFF]==0x5A,marker=ram[0x1FFF],status=context[14],
             completed_steps=int.from_bytes(context[16:18],'little'),cpu_ram=ram[:2048].hex(),
             cpu_registers=(context[4:9]+bytes((context[9]|0x30,))+context[10:11]).hex(),
             ppu_state=pstate.hex(),palette=ram[PALETTE_ADDRESS:PALETTE_ADDRESS+32].hex(),
             ciram=ram[0x4800:0x5000].hex(),records=[ram[0x10000+2080*i:0x10000+2080*(i+1)].hex() for i in range(steps)],
             ppu_records=[ram[0x5000+16*i:0x5010+16*i].hex() for i in range(steps)],
             chr_records=[ram[0x5200+48*i:0x5230+48*i].hex() for i in range(steps)],
             protected_memory=b''.join(ram[a:a+n] for a,n in PROTECTED).hex(),
             ppu_chr_context=ram[0x1C20:0x1C3C].hex(),
             cartridge_ram=ram[0x8000:0x10000].hex(),exram=ram[0x4000:0x4400].hex(),host_enabled=host,
             host=dict(count=int.from_bytes(ram[0x1D00:0x1D04],'little'),depth=ram[0x1D04],peak=ram[0x1D05],
                  fault=ram[0x1D06],wait_hits=int.from_bytes(ram[0x1D08:0x1D0A],'little'),
                  nested_wait_hits=int.from_bytes(ram[0x1D0A:0x1D0C],'little'),work=int.from_bytes(ram[0x1D0C:0x1D10],'little'),
                  min_sp=int.from_bytes(ram[0x1D1E:0x1D20],'little'),low_canary=ram[0x1E80],high_canary=ram[0x1FF1]),
             core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest())
        atomic_json(out,result)
    finally:r.close()


def capture(kind,core,rom,out,steps=31,host=False,stop_pc=None):
    out.parent.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,__file__,'--sample',kind,'--core',str(core),'--rom',str(rom),'--out',str(out),'--steps',str(steps)]
    if host:cmd+=['--host']
    if stop_pc is not None:cmd+=['--stop-pc',str(stop_pc)]
    subprocess.run(cmd,check=True,timeout=90,stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


ENDPOINT_SIZES={'cpu_ram':2048,'cpu_registers':7,'ppu_state':10,'palette':32,'ciram':2048}


def compare_endpoint(plan,reference,native):
    for key,size in ENDPOINT_SIZES.items():
        a=exact_hex(reference.get(key),size,'reference '+key);b=exact_hex(native.get(key),size,'native '+key)
        if a!=b:
            differences=[(i,x,y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
            raise RuntimeError(f'{plan["name"]}: {key} mismatch {differences[:12]}')


def compare(plan,reference,native):
    if (native.get('complete') is not True or any(type(native.get(k)) is not int for k in ('status','marker','completed_steps'))
            or native.get('status')!=0 or native.get('marker')!=0x5A or native.get('completed_steps')!=plan['steps']):
        raise RuntimeError('Native failure or incomplete instruction budget')
    for key,size in (('records',2080),('ppu_records',16),('chr_records',48)):
        rows=native.get(key)
        if not isinstance(rows,list) or len(rows)!=plan['steps']:raise ValueError('Incomplete native '+key)
        for row in rows:exact_hex(row,size,key)
    for i,text in enumerate(native['records']):
        row=bytes.fromhex(text)
        if int.from_bytes(row[18:20],'little')!=i+1:raise ValueError('Native checkpoint order/count differs')
    last=bytes.fromhex(native['records'][-1]);regs=last[4:9]+bytes((last[9]|0x30,))+last[10:11]
    if last[32:]!=exact_hex(native.get('cpu_ram'),2048,'CPU RAM') or regs!=exact_hex(native.get('cpu_registers'),7,'CPU registers'):
        raise ValueError('Final native capture is not the retired endpoint')
    if bytes.fromhex(native['ppu_records'][-1])[:10]!=exact_hex(native.get('ppu_state'),10,'PPU state'):
        raise ValueError('Final PPU capture is not the retired endpoint')
    compare_endpoint(plan,reference,native)
    if bytes.fromhex(native['cpu_ram'])[0x7E]!=0x5A:raise RuntimeError('Guest completion marker missing')
    return dict(passed=True,name=plan['name'],independent_endpoint_bytes=sum(ENDPOINT_SIZES.values()),
                cpu_ram_bytes=2048,cpu_register_bytes=7,ppu_state_bytes=10,palette_bytes=32,ciram_bytes=2048)


def check_host(baseline,native,mode):
    h=native.get('host',{})
    required={'count','depth','peak','fault','work','min_sp','low_canary','high_canary','wait_hits','nested_wait_hits'}
    if not isinstance(h,dict) or set(h)!=required or any(type(v) is not int or v<0 or v>0xFFFFFFFF for v in h.values()):
        raise ValueError('Invalid host metadata')
    if mode not in ('free','cost','time','capture','nested'):raise ValueError('Unsupported targeted host mode')
    expected=0 if mode=='free' else native['completed_steps']
    if h['wait_hits']!=expected or (mode=='nested' and (h['nested_wait_hits']<expected or h['nested_wait_hits']*2!=h['count'])) or (mode!='nested' and h['nested_wait_hits']):
        raise RuntimeError('Selected host interruption site not fully exercised')
    if native.get('host_enabled') is not True or not h.get('count') or h.get('count')!=h.get('work') or h.get('fault') or h.get('depth'):
        raise RuntimeError('Incomplete host interrupt service')
    if h.get('low_canary')!=0xA5 or h.get('high_canary')!=0x5A or not 0x1E90<=h.get('min_sp',0)<0x1FF0:
        raise RuntimeError('Host stack envelope violated')
    if h.get('peak')!=(2 if mode=='nested' else 1):raise RuntimeError('Unexpected host nesting')
    for key,size in (('cartridge_ram',32768),('exram',1024),('protected_memory',132),('ppu_chr_context',28)):
        exact_hex(baseline.get(key),size,'baseline '+key)
        exact_hex(native.get(key),size,'host '+key)
    for key in ('records','ppu_records','chr_records','cartridge_ram','exram','protected_memory','ppu_chr_context'):
        if native.get(key)!=baseline.get(key):raise RuntimeError('Host changed '+key)
    return h['count']


def run_case(nes,snes,out,p):
    # Every emulator runs in its own process; case paths are disjoint.
    d=out/p['name'];nr=create_nes(d/'nes',p);ref=capture('nes',nes,nr,d/'nes/capture.json')
    initial=expected_initial(underlying(p))
    sr=create_native(d/'native',p,initial);base=capture('native',snes,sr,d/'native/capture.json')
    first=compare(p,ref,base)
    sr=create_native(d/'host',p,initial,host_mode='free')
    host=capture('native',snes,sr,d/'host/capture.json',host=True)
    second=compare(p,ref,host)
    return [first,second],check_host(base,host,'free')


def run(nes,snes,out,limit=None,jobs=2):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Require 1..4 isolated case workers')
    plans=cases()
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(plans):raise ValueError('Invalid smoke-test limit')
        plans=plans[:limit]
    out.mkdir(parents=True,exist_ok=True)
    (out/'palette-timeline-verification.json').unlink(missing_ok=True)
    atomic_json(out/'plans.json',plans);finished={}
    executor=ThreadPoolExecutor(max_workers=jobs)
    futures={executor.submit(run_case,nes,snes,out,p):i for i,p in enumerate(plans)}
    try:
        for future in as_completed(futures):
            i=futures[future];finished[i]=future.result()
            print(f"Palette {len(finished)}/{len(plans)} {plans[i]['name']}",flush=True)
            atomic_json(out/'progress.json',dict(complete=False,programs=len(finished)))
    finally:
        executor.shutdown(wait=True,cancel_futures=True)
    rows=[];nmis=0
    for i in range(len(plans)):
        pair,count=finished[i];rows.extend(pair);nmis+=count
    report=dict(passed=True,complete_matrix=limit is None,programs=len(plans),scenarios=len(rows),
                independent_endpoint_bytes=sum(r['independent_endpoint_bytes'] for r in rows),host_interrupts=nmis,
                source_profile='mmc5-palette-blank',per_instruction_nes_equivalence_claimed=False,new_game_replay=False,
                cores={'nestopia':hashlib.sha256(nes.read_bytes()).hexdigest(),'snes':hashlib.sha256(snes.read_bytes()).hexdigest()},
                scope='Independent final endpoints of stable authored programs with rendering and PPU NMI disabled. Native instruction records establish host noninterference only; not per-instruction NES cycle, event, bus, video or audio equivalence.',
                results=rows)
    atomic_json(out/'palette-timeline-verification.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=('nes','native'));p.add_argument('--steps',type=int,default=31);p.add_argument('--host',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--stop-pc',type=int);p.add_argument('--jobs',type=int,default=2)
    for key in ('core','rom','out','nes-core','snes-core'):p.add_argument('--'+key,type=Path)
    a=p.parse_args()
    if a.sample=='nes':nes_sample(a.core,a.rom,a.out,a.stop_pc)
    elif a.sample=='native':native_sample(a.core,a.rom,a.out,a.steps,a.host)
    else:print(run(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.limit,a.jobs))
