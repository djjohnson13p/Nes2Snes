#!/usr/bin/env python3
"""Independent DMA endpoints and original instruction elapsed-time ledger.

The NES observer only records timestamps and PCs. Boot synchronizes phase using
an actual DMA; no captured timestamp, seed or intermediate state drives SNES.
"""
from pathlib import Path
import argparse
import ctypes as C
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from libretro_runner import Runner
from chr_sets_state import decode_sets
from palette_state import decode
from verify_chr_mode_rewrite import compare as compare_state,check_host as previous_host
from verify_palette_timeline import native_sample
from verify_ppu_blank import exact_hex
from route_evidence import atomic_json
from oam_dma_timeline import create_nes,create_native,initial,STATE_ADDRESS,LOG_ADDRESS
from oam_dma_fixture import cases,make_case,guard_cases,seal


class TimingRow(C.Structure):
    _fields_=[('start',C.c_uint64),('end',C.c_uint64),('pc',C.c_uint16),
              ('next_pc',C.c_uint16),('clock',C.c_uint32),('opcode',C.c_uint8),('reserved',C.c_uint8*7)]


class Observer:
    def __init__(self,lib,entry,count):
        if type(entry) is not int or not 0x8000<=entry<=65535 or type(count) is not int or not 1<=count<=64:
            raise ValueError('Invalid bounded timing request')
        self.lib=lib;self.count=count
        lib.retro_n2s_dma_configure.argtypes=[C.c_uint16,C.c_uint32];lib.retro_n2s_dma_configure.restype=C.c_int
        lib.retro_n2s_dma_status.argtypes=[C.c_uint];lib.retro_n2s_dma_status.restype=C.c_uint32
        lib.retro_n2s_dma_data.argtypes=[];lib.retro_n2s_dma_data.restype=C.POINTER(TimingRow)
        if lib.retro_n2s_dma_status(2)!=32 or C.sizeof(TimingRow)!=32 or not lib.retro_n2s_dma_configure(entry,count):
            raise ValueError('Timing observer ABI/configuration mismatch')

    def finish(self):
        lib=self.lib
        if lib.retro_n2s_dma_status(0)!=self.count or lib.retro_n2s_dma_status(1) or lib.retro_n2s_dma_status(3):
            raise ValueError('Incomplete or invalid timing capture')
        rows=lib.retro_n2s_dma_data();result=[]
        for i in range(self.count):
            r=rows[i]
            if any(r.reserved) or not r.clock or r.end<=r.start or (r.end-r.start)%r.clock:
                raise ValueError('Malformed timing row')
            result.append({k:int(getattr(r,k)) for k,_ in TimingRow._fields_ if k!='reserved'})
        return result


def nes_sample(core,rom,out,steps,observed,stop=None):
    r=Runner(core,rom)
    try:
        observer=Observer(r.lib,0xE100,steps) if observed else None
        for _ in range(120):
            r.run(1)
            if stop is None:
                if r.memory()[0x7E]==0x5A:break
            elif int.from_bytes(bytes.fromhex(decode(r.state(),sprite_16=True)['cpu_registers'])[:2],'little')==stop:
                break
        else:raise RuntimeError('Original program did not reach endpoint')
        raw=r.state();out.parent.mkdir(parents=True,exist_ok=True);out.with_suffix('.nst').write_bytes(raw)
        result=decode_sets(raw)
        if bytes.fromhex(result['cpu_ram'])!=r.memory()[:2048]:raise ValueError('Serialized CPU RAM differs')
        result.update(core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                      state_sha256=hashlib.sha256(raw).hexdigest(),frames=r.frames,audio_frames=r.audio_frames,image_sha256=hashlib.sha256(r.rgb().tobytes()).hexdigest())
        if observer:result['timings']=observer.finish()
        atomic_json(out,result)
    finally:r.close()


def capture(kind,core,rom,out,steps=31,host=False,stop=None):
    out.parent.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,__file__,'--sample',kind,'--core',str(core),'--rom',str(rom),'--out',str(out),'--steps',str(steps)]
    if host:cmd+=['--host']
    if stop is not None:cmd+=['--stop',str(stop)]
    subprocess.run(cmd,check=True,timeout=90,stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def noninterference(plain,observed):
    def logical(x):return {k:v for k,v in x.items() if k not in ('core_sha256','timings')}
    if logical(plain)!=logical(observed):raise RuntimeError('Observer changed original execution')


def timing(plan,reference,actual,clock_origin=0):
    if type(clock_origin) is not int or not 0<=clock_origin<2**32 or clock_origin&1:
        raise ValueError('Clock origin must preserve the declared GET phase')
    rows=reference.get('timings')
    if not isinstance(rows,list) or len(rows)!=plan['steps']:raise ValueError('Incomplete original timing ledger')
    raw=exact_hex(actual.get('dma_records'),8*plan['steps'],'DMA records')
    meta=exact_hex(actual.get('dma_state'),8,'DMA metadata')
    if meta!=raw[-8:]:raise ValueError('Final DMA state differs from retired record')
    records=actual.get('records')
    if not isinstance(records,list) or len(records)!=plan['steps']:
        raise ValueError('Incomplete native instruction ledger')
    required={'start','end','pc','next_pc','clock','opcode'}
    if any(not isinstance(row,dict) or set(row)!=required or
           any(type(v) is not int for v in row.values()) for row in rows):
        raise ValueError('Invalid original instruction record')
    origin=rows[0]['start'];prior=origin;count=total=last=0;durations=[]
    for i,(row,text) in enumerate(zip(rows,records)):
        if not (0<=row['start']<row['end']<2**64 and 0<row['clock']<=65535 and
                0<=row['pc']<=65535 and 0<=row['next_pc']<=65535 and 0<=row['opcode']<=255):
            raise ValueError('Original record exceeds integer bounds')
        if i and row['pc']!=rows[i-1]['next_pc']:raise ValueError('Original PC discontinuity')
        native=exact_hex(text,2080,'Native instruction record')
        if row['start']!=prior or row['clock']!=rows[0]['clock'] or row['end']<=row['start']:
            raise ValueError('Discontinuous original time window')
        elapsed=(row['end']-origin)//row['clock']
        if (row['end']-origin)%row['clock'] or int.from_bytes(native[:4],'little')!=elapsed+clock_origin or int.from_bytes(native[4:6],'little')!=row['next_pc']:
            raise RuntimeError(f'{plan["name"]}: original/native clock or next-PC mismatch at {i}: ref {elapsed}, native {int.from_bytes(native[:4],"little")}')
        # Only absolute STA $4014 contributes DMA delay; source bytes are read
        # from the authored original program, never inferred from a matching PC.
        from mmc5_timeline import fragments
        inst=None
        for part in fragments(plan):
            offset=row['pc']-part['origin'];code=bytes.fromhex(part['code'])
            if 0<=offset<len(code):inst=code[offset:offset+3];break
        if not inst or inst[0]!=row['opcode'] or native[17]!=row['opcode']:
            raise ValueError('Original/native executed opcode differs')
        if (row['end']-row['start'])%row['clock']:raise ValueError('Fractional original instruction cycle')
        duration=(row['end']-row['start'])//row['clock']
        if inst==b'\x8d\x14\x40':
            last=duration-4
            if last not in (513,514):raise RuntimeError('Unexpected independently measured DMA delay')
            total+=last;count+=1;durations.append(last)
        entry=raw[i*8:(i+1)*8]
        if entry!=count.to_bytes(2,'little')+last.to_bytes(2,'little')+total.to_bytes(4,'little'):
            raise RuntimeError('Native DMA ledger differs from independent elapsed timing')
        prior=row['end']
    return dict(boundaries=len(rows),span_cycles=(prior-origin)//rows[0]['clock'],dma_transfers=count,dma_stall_cycles=total,delays=durations)


def compare(plan,reference,actual,clock_origin=0):
    result=compare_state(plan,reference,actual)
    result['timing']=timing(plan,reference,actual,clock_origin)
    return result


def check_host(base,actual,mode):
    count=previous_host(base,actual,mode)
    for key in ('dma_state','dma_records'):
        if base.get(key)!=actual.get(key):raise RuntimeError('Host changed '+key)
    return count


def run_case(nes,observed,snes,out,plan):
    d=out/plan['name'];rom=create_nes(d/'nes',plan)
    plain=capture('nes',nes,rom,d/'nes/plain.json',plan['steps'])
    ref=capture('observed',observed,rom,d/'nes/observed.json',plan['steps']);noninterference(plain,ref)
    rows=[];base=None;nmis=0
    for mode in (None,'free'):
        dest=d/('native' if mode is None else 'host')
        rom=create_native(dest,plan,initial(plan),**({'host_mode':mode} if mode else {}))
        actual=capture('native',snes,rom,dest/'capture.json',plan['steps'],bool(mode))
        rows.append(compare(plan,ref,actual))
        if mode:nmis=check_host(base,actual,mode)
        else:base=actual
    return rows,nmis


def run(nes,observed,snes,out,limit=None,jobs=2):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Require 1..4 workers')
    plans=cases()
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(plans):raise ValueError('Invalid smoke limit')
        plans=plans[:limit]
    out.mkdir(parents=True,exist_ok=True);summary=out/'dma-verification.json';summary.unlink(missing_ok=True)
    atomic_json(out/'plans.json',plans);done={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        pending={pool.submit(run_case,nes,observed,snes,out,p):i for i,p in enumerate(plans)}
        for f in as_completed(pending):
            i=pending[f];done[i]=f.result();print('DMA',len(done),'/',len(plans),plans[i]['name'],flush=True)
    rows=[];nmis=0
    for i in range(len(plans)):
        pair,n=done[i];rows.extend(pair);nmis+=n
    result=dict(passed=True,complete_matrix=limit is None,programs=len(plans),scenarios=len(rows),
        independent_endpoint_bytes=sum(r['independent_endpoint_bytes'] for r in rows),
        independent_timing_boundaries=sum(r['timing']['boundaries'] for r in rows),
        host_interrupts=nmis,results=rows,cores={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('nestopia',nes),('observer',observed),('snes',snes)]},
        scope='RAM-source OAM DMA with authored phase synchronization, no DMC/rendering/guest interrupts. Independent final endpoints and instruction elapsed clocks/PCs. Not bus-transaction, PPU event or physical-console equivalence.')
    atomic_json(summary,result);return result


def prefix_rom(out,plan,stop):
    rom=create_nes(out,plan);raw=bytearray(rom.read_bytes())
    index=16+(plan['prg_banks']-1)*8192+(stop&8191)
    raw[index:index+3]=b'\x4c'+stop.to_bytes(2,'little');rom.write_bytes(raw)
    return rom


def compare_guard(plan,reference,actual,stop,retired):
    from verify_chr_mode_rewrite import check_guard
    result=check_guard(plan,reference,actual,stop,retired)
    raw=exact_hex(actual.get('dma_records'),plan['steps']*8,'DMA guard records')
    final=exact_hex(actual.get('dma_state'),8,'DMA guard state')
    if final!=raw[8*(retired-1):8*retired]:raise RuntimeError('Refused DMA changed its ledger')
    result['dma_state_unchanged']=True
    return result


def controls(nes,observed,snes,out):
    from mmc5_timeline import reassemble
    from mmc5_cpu_io import replace_once
    from native_fixture import Program
    from ppu_blank_fixture import put
    out.mkdir(parents=True,exist_ok=True);summary=out/'dma-controls.json';summary.unlink(missing_ok=True)
    hosts=[];mutants=[];guards=[]
    selected=[make_case(2,0,0xE9),make_case(0x1E,254,0xD9,True,True)]
    for plan in selected:
        d=out/plan['name'];rom=create_nes(d/'nes',plan)
        ref=capture('observed',observed,rom,d/'nes/observed.json')
        plain=capture('nes',nes,rom,d/'nes/plain.json');noninterference(plain,ref)
        base=capture('native',snes,create_native(d/'native',plan,initial(plan)),d/'native/capture.json');compare(plan,ref,base)
        for mode in ('cost','time','capture','nested'):
            actual=capture('native',snes,create_native(d/mode,plan,initial(plan),host_mode=mode),d/mode/'capture.json',host=True)
            compare(plan,ref,actual);hosts.append(dict(name=plan['name'],mode=mode,count=check_host(base,actual,mode)))
        # Stop inside the transfer, after reading byte 128 but before its OAM write.
        folder=d/'dma-copy';create_native(folder,plan,initial(plan),host_mode='free')
        path=folder/'oam_dma_timeline.inc';text=path.read_text()
        text=replace_once(text,'    sta MR_VALUE\n    rep #$20',
            '    sta MR_VALUE\n    cpy #128\n    bne :+\n    wai\nDmaWaitResume:\n:\n    rep #$20')
        path.write_text(text);path=folder/'fixture.s'
        path.write_text(replace_once(path.read_text(),'HostExpectedResume = $0000','HostExpectedResume = OamDmaRun::DmaWaitResume'))
        actual=capture('native',snes,reassemble(folder),folder/'capture.json',host=True)
        compare(plan,ref,actual)
        h=actual['host'];expected=int.from_bytes(bytes.fromhex(actual['dma_state'])[:2],'little')
        if h['wait_hits']!=expected:raise RuntimeError('Mid-copy interruption was not witnessed for every DMA')
        # Strictly validate the different wait-count contract before reusing the
        # remaining free-NMI invariants. Raw capture is retained without edits.
        normalized=dict(actual,host=dict(h,wait_hits=0))
        count=check_host(base,normalized,'free')
        hosts.append(dict(name=plan['name'],mode='dma-copy',count=count,wait_hits=h['wait_hits']))
    clock_checks=[]
    plan=selected[0];d=out/'clock-carry';ref=capture('observed',observed,create_nes(d/'nes',plan),d/'nes/capture.json')
    for mode in (None,'free'):
        folder=d/('native' if mode is None else 'host');create_native(folder,plan,initial(plan),**({'host_mode':mode} if mode else {}))
        path=folder/'fixture.s';text=path.read_text()
        # An even caller epoch tests low-word carry without changing GET phase.
        text=replace_once(text,'    jsr OamDmaInit','    jsr OamDmaInit\n    lda #$FF00\n    sta GT')
        if mode:
            text=replace_once(text,'HostExpectedResume = $0000','HostExpectedResume = OamDmaRun::DmaClockResume')
            h=folder/'oam_dma_timeline.inc'
            h.write_text(replace_once(h.read_text(),'    adc GT\n    sta GT\n    bcc :+',
                '    adc GT\n    sta GT\n    wai\nDmaClockResume:\n    bcc :+'))
        path.write_text(text);actual=capture('native',snes,reassemble(folder),folder/'capture.json',host=bool(mode))
        compare(plan,ref,actual,clock_origin=0xFF00)
        if mode:
            if actual['host']['wait_hits']!=1:raise RuntimeError('Carry-site interrupt not observed')
            count=check_host(carry_base,dict(actual,host=dict(actual['host'],wait_hits=0)),'free')
        else:carry_base=actual;count=0
        clock_checks.append(dict(origin=0xFF00,host=bool(mode),passed=True,host_interrupts=count))
    # Refusal is checked before the transfer, with no external expected data.
    plan=selected[0];raw=bytes.fromhex(plan['code']);stop=plan['origin']+raw.index(b'\x8d\x14\x40');retired=plan['starts'].index(stop)
    folder=out/'clock-overflow';ref=capture('nes',nes,prefix_rom(folder/'nes',plan,stop),folder/'nes/capture.json',stop=stop)
    create_native(folder/'native',plan,initial(plan));path=folder/'native/fixture.s'
    path.write_text(replace_once(path.read_text(),'    jsr OamDmaInit','    jsr OamDmaInit\n    lda #$FE00\n    sta GT\n    lda #$FFFF\n    sta GT+2'))
    actual=capture('native',snes,reassemble(folder/'native'),folder/'native/capture.json')
    if actual['status']!=4:raise RuntimeError('Overflow did not use the explicit clock fault')
    compare_guard(plan,ref,dict(actual,status=5),stop,retired)
    clock_checks.append(dict(origin=0xFFFFFE00,overflow_rejected_before_transfer=True,retired=retired,status=actual['status']))
    specifications=[
        ('stall-parity',selected[0],'    eor #1\n','    and #0\n'),
        ('source-mirror',make_case(0x1E,254,0xD9,True),'    and #7\n','    and #3\n'),
        ('short-copy',selected[0],'    cpy #256\n','    cpy #255\n'),
        ('capture-width',selected[0],'    sta f:$7E6006,x\n    sep #$20\n.a8','    sta f:$7E6006,x\n    nop\n    nop\n.a8')]
    for name,plan,old,new in specifications:
        folder=out/('mutant-'+name);ref=capture('observed',observed,create_nes(folder/'nes',plan),folder/'nes/capture.json')
        create_native(folder/'native',plan,initial(plan));path=folder/'native/oam_dma_timeline.inc'
        path.write_text(replace_once(path.read_text(),old,new))
        actual=capture('native',snes,reassemble(folder/'native'),folder/'native/capture.json')
        if not actual['complete'] or actual['status'] or actual['completed_steps']!=plan['steps']:
            raise RuntimeError('Broken implementation crashed instead of exercising a wrong result')
        try:compare(plan,ref,actual)
        except (ValueError,RuntimeError) as exc:mutants.append(dict(name=name,rejected=True,completed=True,reason=str(exc)))
        else:raise RuntimeError('Broken DMA implementation passed')
    for plan,stop,retired in guard_cases():
        folder=out/('guard-'+plan['name'])
        ref=capture('nes',nes,prefix_rom(folder/'nes',plan,stop),folder/'nes/capture.json',stop=stop)
        actual=capture('native',snes,create_native(folder/'native',plan,initial(plan)),folder/'native/capture.json')
        guards.append(compare_guard(plan,ref,actual,stop,retired))
    # Two original NES programs expose the differing latch result. This is a
    # reference-path disagreement, not a physical hardware or native pass.
    plan=make_case(2,3,0xFF);folder=out/'attribute-latch-diagnostic'
    dma=capture('nes',nes,create_nes(folder/'dma',plan),folder/'dma/capture.json')
    p=Program(0xE100);put(p,0x2003,2);put(p,0x2004,0xA6)
    p.op('LDA','abs',0x2000);p.op('STA','abs',0x680)
    port_plan=seal(p,'dma-port-latch-control')
    port=capture('nes',nes,create_nes(folder/'port',port_plan),folder/'port/capture.json')
    a=bytes.fromhex(dma['cpu_ram'])[0x680];b=bytes.fromhex(port['cpu_ram'])[0x680]
    if (a,b)!=(0xA2,0xA6):raise RuntimeError('Stored latch diagnostic changed; reassess guard')
    diagnostic=dict(reference_accuracy_passed=False,excluded_from_acceptance=True,dma_readback=a,cpu_port_readback=b,
        scope='Two unmodified Nestopia program paths; not a physical hardware rule. Final-attribute transfers remain refused.')
    result=dict(passed=True,host_results=hosts,host_interrupts=sum(h['count'] for h in hosts),
        negative_controls=mutants,guards=guards,clock_checks=clock_checks,latch_diagnostic=diagnostic)
    atomic_json(summary,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample',choices=('nes','observed','native'));p.add_argument('--steps',type=int,default=31)
    p.add_argument('--controls',action='store_true');p.add_argument('--host',action='store_true');p.add_argument('--stop',type=int);p.add_argument('--limit',type=int);p.add_argument('--jobs',type=int,default=2)
    for k in ('core','rom','out','nes-core','observed-core','snes-core'):p.add_argument('--'+k,type=Path)
    a=p.parse_args()
    if a.sample=='native':native_sample(a.core,a.rom,a.out,a.steps,a.host,extra_ranges={
        'oam':(0x5900,256),'oam_address':(0x1C3B,1),'chr_set_b':(0x5A00,9),
        'chr_rewrite_policy':(0x5A09,3),'dma_state':(STATE_ADDRESS,8),'dma_records':(LOG_ADDRESS,8*a.steps)})
    elif a.sample:nes_sample(a.core,a.rom,a.out,a.steps,a.sample=='observed',a.stop)
    elif a.controls:print(controls(a.nes_core.resolve(),a.observed_core.resolve(),a.snes_core.resolve(),a.out.resolve()))
    else:print(run(a.nes_core.resolve(),a.observed_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.limit,a.jobs))
