#!/usr/bin/env python3
"""Independent whole-routine dispatch comparison. No commercial input required."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from build_native import build
from dispatch_fixture import create, boundary_fixture
from verify_native_cpu import verify
from libretro_runner import Runner

def save(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(path)

def fault_capture(core, rom, out):
    r=Runner(core,rom)
    try:
        for _ in range(600):
            r.run(1);m=r.memory()
            if m[0x90F]:
                save(out,dict(fault=m[0x90F],pc=int.from_bytes(m[0x90C:0x90E],'little'),
                              bank=m[0x90E],success_marker=m[0x7E]))
                return
            if m[0x7E]==0x5A:raise RuntimeError('Unchecked target executed')
        raise RuntimeError('No expected unknown-code stop')
    finally:r.close()

def run(nes_core,snes_core,out,previous_root=None):
    out.mkdir(parents=True,exist_ok=True);rows=[]
    configurations=[]
    for block in range(32):
        configurations.append((f'selectors-{block:02d}',dict(selectors=list(range(block*8,block*8+8)),
            primary=block%16,cbank=7 if block>=16 else 30),{}))
    for name, fixture, options in [
        ('counter-free',{},dict(runtime_counters=False)),
        ('disabled',{},dict(native_inline_dispatch=False)),
        ('no-direct',{},dict(direct=False)),
        ('outside-nmi',dict(outside_nmi=True),{}),
        ('c0',dict(c0=True),{}),
        ('slowrom',{},dict(fastrom=False)),
        ('stack-depth-32',dict(stack_depth=32),{}),
        ('stack-depth-96',dict(stack_depth=96),{}),
        ('nmi-stress',{},dict(stress_nmi_restore=True)),
    ]:configurations.append((name,fixture,options))
    for name, fixture, options in configurations:
        print('Checking '+name,flush=True)
        directory=out/name;meta=create(directory,**fixture)
        flags=dict(native_inline_dispatch=True);flags.update(options)
        info=build(directory/'fixture.nes',directory,directory/'snes',**flags)
        result=verify(nes_core,snes_core,directory,directory/'verification')
        expected=meta['expected_native_calls'] if info['native_inline_dispatch'] and info['runtime_counters'] else 0
        actual=result['native_execution_counters']['native_dispatch_calls']
        if expected!=actual:raise RuntimeError(f'{name}: expected {expected} calls, got {actual}')
        # The independent CPU records also require the measured stack delta=0.
        ram=(directory/'verification/snes.ram').read_bytes()
        for record in meta['records']:
            if record['name'].endswith('_stack_delta') and ram[record['address']]!=0:
                raise RuntimeError('Stack delta is nonzero')
        row=dict(name=name,records=result['records_checked'],bytes=result['bytes_checked'],
                 mismatches=result['mismatch_count'],native_calls=actual,expected_native_calls=expected,
                 fixture_options=fixture,build_options=flags)
        rows.append(row);save(out/'progress.json',dict(complete=False,completed=len(rows),results=rows))
    boundaries=[]
    for ret in (0xFEFF,0xFF00,0xFF01,0xFFF7):
        directory=out/f'boundary-{ret:04x}';meta=boundary_fixture(directory,ret)
        build(directory/'fixture.nes',directory,directory/'snes',native_inline_dispatch=True)
        r=verify(nes_core,snes_core,directory,directory/'verification')
        actual=r['native_execution_counters']['native_dispatch_calls']
        if actual!=meta['expected_native_calls']:raise RuntimeError('Incorrect boundary guard')
        boundaries.append(dict(return_address=ret,records=r['records_checked'],bytes=r['bytes_checked'],mismatches=r['mismatch_count'],native_calls=actual))
    guards=[]
    for enabled in (False,True):
        directory=out/f'unknown-target-{enabled}';meta=create(directory,selectors=[0])
        counts=bytearray((directory/'counts.u32').read_bytes())
        target=meta['cases'][0]['table_target'];physical=0x3E000+target-0xE000
        struct.pack_into('<I',counts,4*physical,0);(directory/'counts.u32').write_bytes(counts)
        build(directory/'fixture.nes',directory,directory/'snes',native_inline_dispatch=enabled)
        subprocess.run([sys.executable,__file__,'--capture-fault','--snes-core',str(snes_core),
                        '--rom',str(directory/'snes/native-prototype.sfc'),'--out',str(directory/'fault.json')],check=True,timeout=30)
        d=json.loads((directory/'fault.json').read_text())
        if d['fault']!=1 or d['pc']!=target or d['bank']!=0xA1 or d['success_marker']==0x5A:
            raise RuntimeError('Unknown-target guard mismatch '+str(d))
        guards.append(dict(enabled=enabled,**d))
    identities=[]
    if previous_root:
        for name,creator in [('dispatch',create)]:
            directory=out/('identity-'+name);creator(directory)
            build(directory/'fixture.nes',directory,directory/'current')
            subprocess.run([sys.executable,str(previous_root/'tools/build_native.py'),
                 '--rom',str(directory/'fixture.nes'),'--trace',str(directory),
                 '--out',str(directory/'previous')],check=True,stdout=subprocess.DEVNULL,timeout=60)
            new=(directory/'current/native-prototype.sfc').read_bytes()
            old=(directory/'previous/native-prototype.sfc').read_bytes()
            if new!=old:raise RuntimeError('Default output changed')
            identities.append(dict(fixture=name,byte_identical=True,sha256=hashlib.sha256(new).hexdigest()))
    report=dict(passed=True,complete=True,configurations=len(rows)+len(boundaries),records_checked=sum(r['records'] for r in rows+boundaries),
        bytes_checked=sum(r['bytes'] for r in rows+boundaries),mismatches=0,selector_values_checked=256,
        coverage='All selector byte values occur; not a Cartesian product of all CPU state, table addresses, and bank mappings.',
        reference_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
        snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
        fault_guards=guards,boundary_results=boundaries,default_identity=identities,results=rows,
        scope='Classified inline table dispatch: outputs, scratch bytes, relative stack balance, raw-table reads and guarded fallback. No cycle or all-game accuracy claim.')
    save(out/'native-dispatch-verification.json',report);save(out/'progress.json',dict(complete=True,completed=len(rows)))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('nes-core','snes-core','out','previous-root','rom'):p.add_argument('--'+name,type=Path)
    p.add_argument('--capture-fault',action='store_true');a=p.parse_args()
    if a.capture_fault:fault_capture(a.snes_core.resolve(),a.rom.resolve(),a.out.resolve())
    else:
        if not all((a.nes_core,a.snes_core,a.out)):p.error('Require --nes-core, --snes-core and --out')
        d=run(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve(),a.previous_root.resolve() if a.previous_root else None)
        print(json.dumps({k:v for k,v in d.items() if k!='results'},indent=2))
