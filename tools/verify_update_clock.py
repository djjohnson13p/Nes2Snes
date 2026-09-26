#!/usr/bin/env python3
"""Authored reentrancy-guard clock test against an unmodified NES core.

No commercial ROM is required. A deliberately alternating guard makes the
NMI-entry count different from the completed update count. The instrumentation
must preserve the reference RAM and count the correct instruction entries.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from libretro_runner import Runner
from native_fixture import Program, write_program
from rom import Rom
from route_evidence import guarded_update_pc, atomic_json


def create(folder: Path, initial_guard: int) -> dict:
    if type(initial_guard) is not int or initial_guard not in (0,1): raise ValueError('Require a binary initial guard')
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0)
    for a in (0x2000,0x2001,0x600,0x601,0x602,0x603):p.op('STA','abs',a)
    p.op('LDA','imm',initial_guard);p.op('STA','zp',0x50)
    p.op('LDX','imm',2);p.label('wait');p.op('BIT','abs',0x2002)
    p.op('BPL','rel','wait');p.op('DEX');p.op('BNE','rel','wait')
    p.op('LDA','imm',0x80);p.op('STA','abs',0x2000)
    p.label('idle');p.op('JMP','abs','idle')
    p.label('nmi');p.op('PHA');p.op('TXA');p.op('PHA');p.op('TYA');p.op('PHA')
    p.op('LDY','zp',0x50);p.op('BNE','rel','skip');p.label('full_update');p.op('INC','zp',0x50)
    p.op('INC','abs',0x600);p.op('BNE','rel','after_update');p.op('INC','abs',0x601)
    p.label('after_update');p.op('JMP','abs','finish')
    p.label('skip');p.op('DEC','zp',0x50)
    p.label('finish');p.op('INC','abs',0x602);p.op('BNE','rel','restore');p.op('INC','abs',0x603)
    p.label('restore');p.op('PLA');p.op('TAY');p.op('PLA');p.op('TAX');p.op('PLA');p.op('RTI')
    result=write_program(folder,p)
    result['full_update_pc']=p.labels['full_update']
    return result


def sample(core: Path, rom_path: Path, out: Path, probe: bool):
    rom=Rom.read(rom_path);nmi=int.from_bytes(rom.prg[-6:-4],'little')
    marker=guarded_update_pc(rom.prg,nmi);r=Runner(core,rom_path);rows=[]
    try:
        if probe:
            r.lib.retro_n2s_data.argtypes=[C.c_uint];r.lib.retro_n2s_data.restype=C.c_void_p
            r.lib.retro_n2s_size.argtypes=[C.c_uint];r.lib.retro_n2s_size.restype=C.c_size_t
        for target in (90,180,240,360):
            r.run(target-r.frames);m=r.memory()
            if len(m)!=2048:raise AssertionError('Expected exactly 2 KiB NES internal RAM')
            data=dict(frame=target,updates=int.from_bytes(m[0x600:0x602],'little'),
                      nmis=int.from_bytes(m[0x602:0x604],'little'),ram_sha256=hashlib.sha256(m).hexdigest())
            if probe:
                counts=C.cast(r.lib.retro_n2s_data(0),C.POINTER(C.c_uint32))
                if not counts or r.lib.retro_n2s_size(0)!=len(rom.prg)*4:
                    raise RuntimeError('Missing or incorrectly sized probe array')
                base=len(rom.prg)-0x2000
                data['observed_nmis']=int(counts[base+nmi-0xE000])
                data['observed_updates']=int(counts[base+marker-0xE000])
            rows.append(data)
        if r.errors: raise RuntimeError(r.errors)
    finally:r.close()
    atomic_json(out,dict(rows=rows,marker_pc=marker,rom_sha256=rom.metadata()['sha256'],
                         core_sha256=hashlib.sha256(core.read_bytes()).hexdigest()))


def verify(probe_core: Path, reference_core: Path, out: Path):
    out.mkdir(parents=True,exist_ok=True);rows=[]
    for guard in (0,1):
        folder=out/str(guard);meta=create(folder,guard)
        for role,core in [('reference',reference_core),('probe',probe_core)]:
            subprocess.run([sys.executable,__file__,'--sample',role,'--core',str(core),
                            '--rom',str(folder/'fixture.nes'),'--out',str(folder/(role+'.json'))],
                           check=True,timeout=60,stdout=subprocess.DEVNULL)
        a=json.loads((folder/'reference.json').read_text());b=json.loads((folder/'probe.json').read_text())
        if a['marker_pc']!=b['marker_pc'] or b['marker_pc']!=meta['full_update_pc']:
            raise AssertionError('Wrong guarded entry')
        if a['rom_sha256']!=b['rom_sha256']:
            raise AssertionError('The two cores received different fixture bytes')
        if len(a['rows'])!=4 or len(b['rows'])!=4:
            raise AssertionError('Missing independent snapshots')
        for x,y in zip(a['rows'],b['rows']):
            if any(x[key]!=y[key] for key in x):raise AssertionError('Probe changed reference execution')
            if y['observed_updates']!=x['updates'] or y['observed_nmis']!=x['nmis']:
                raise AssertionError('Probe marker disagrees with independent program counters')
            if not 0<x['updates']<x['nmis']:raise AssertionError('Fixture failed to exercise skipped updates')
        rows.append(dict(initial_guard=guard,reference=a,probe=b))
        atomic_json(out/'progress.json',dict(complete=False,cases_completed=len(rows)))
    result=dict(passed=True,cases=2,snapshots=8,reference_ram_bytes_checked=8*2048,
                skipped_updates_observed=True,legacy_entry_count_overcounts_updates=True,
                scope='Authored alternating-guard program; independent NES RAM and probe counts. Not arbitrary-game timing accuracy.',results=rows)
    atomic_json(out/'update-clock-verification.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',choices=['probe','reference'])
    for name in ('core','rom','probe-core','reference-core','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    required=('core','rom','out') if a.sample else ('probe_core','reference_core','out')
    for key in required:
        if getattr(a,key) is None:p.error('--'+key.replace('_','-')+' is required')
    if a.sample: sample(a.core.resolve(),a.rom.resolve(),a.out.resolve(),a.sample=='probe')
    else:
        result=verify(a.probe_core.resolve(),a.reference_core.resolve(),a.out.resolve())
        print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
