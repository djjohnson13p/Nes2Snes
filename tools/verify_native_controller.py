#!/usr/bin/env python3
"""Independent controller/CPU checks for the guarded whole-routine replacement.

No commercial ROM is needed. The NES core executes the procedural polling body;
the SNES core executes either the optimized body or its original fallback.
These checks establish polled values/state/flags, not cycle-accurate input timing.
"""
from __future__ import annotations
import argparse,ctypes as C,hashlib,json,subprocess,sys
from pathlib import Path
from controller_fixture import create
from build_native import build
from libretro_runner import Runner


def capture(core:Path,rom:Path,out:Path,buttons:list[str])->None:
    r=Runner(core,rom)
    try:
        for _ in range(600):
            r.run(1,tuple(buttons));m=r.memory()
            if len(m)>0x90f and m[0x90f]:raise RuntimeError('Bridge fault '+m[0x90c:0x910].hex())
            if m[0x7e]==0x5a:
                out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(m[:0x800])
                out.with_suffix('.json').write_text(json.dumps(dict(
                    native_poll_calls=int.from_bytes(m[0x9a0:0x9a4],'little') if len(m)>=0x9a4 else None,
                    host_frames=r.frames))+'\n')
                return
        raise RuntimeError('Controller fixture did not finish')
    finally:r.close()


def verify(nes_core:Path,snes_core:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    # Never request opposite directions: frontend sanitization differs by core.
    inputs=[[],['a'],['b'],['start'],['select'],['up'],['down'],['left'],['right'],
            ['a','b'],['a','right'],['b','left'],['a','up'],['b','down'],
            ['start','select'],['a','b','right'],['a','b','up'],['a','b','left','up']]
    configurations=[(f'input-{i:02}',b,{}) for i,b in enumerate(inputs)]
    for name,options in [('counterfree',dict(runtime_counters=False)),
                         ('disabled',dict(native_poll=False)),
                         ('no-direct',dict(direct=False)),
                         ('c0',dict(c0=True)),('outside-nmi',dict(outside_nmi=True)),
                         ('slowrom',dict(fastrom=False)),
                         ('nested-nmi',dict(stress_nmi_restore=True))]:
        configurations.append((name,['a','b','right'],options))
    results=[]
    for name,buttons,options in configurations:
        path=out/name;opts=dict(options)
        meta=create(path,c0=opts.pop('c0',False),outside_nmi=opts.pop('outside_nmi',False))
        flags=dict(native_poll=True);flags.update(opts)
        info=build(path/'fixture.nes',path,path/'snes',**flags)
        for platform,core,rom in [('nes',nes_core,path/'fixture.nes'),('snes',snes_core,path/'snes/native-prototype.sfc')]:
            subprocess.run([sys.executable,__file__,'--capture','--core',str(core),'--rom',str(rom),
                            '--out',str(path/(platform+'.ram')),'--buttons',','.join(buttons)],check=True,
                           stdout=subprocess.DEVNULL)
        a=(path/'nes.ram').read_bytes();b=(path/'snes.ram').read_bytes()
        differences=[]
        for item in meta['records']:
            j=item['address'];x=a[j:j+4];y=b[j:j+4]
            if x!=y:differences.append(dict(test=item['name'],nes=x.hex(),snes=y.hex()))
        stats=json.loads((path/'snes.json').read_text())
        expected=meta['expected_native_calls'] if info['native_controller_poll'] and info['runtime_counters'] else 0
        result=dict(name=name,buttons=buttons,records_checked=len(meta['records']),mismatches=differences,
                    native_calls=stats['native_poll_calls'],expected_native_calls=expected,
                    fallback_indices=[x for x in meta['indices'] if x>=3],options=options)
        results.append(result)
        (out/'progress.json').write_text(json.dumps(dict(completed=len(results),total=len(configurations)),indent=2)+'\n')
        (path/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
        if differences or stats['native_poll_calls']!=expected:
            raise RuntimeError('Controller differential failure: '+json.dumps(result))
        print(name,'passed',flush=True)
    result=dict(configurations=len(results),records_checked=sum(r['records_checked'] for r in results),
                register_bytes_checked=sum(r['records_checked'] for r in results)*4,mismatches=0,
                results=results,nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
                snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
                scope=__doc__)
    (out/'controller-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',action='store_true')
    for name in ('core','rom','nes-core','snes-core','out'):p.add_argument('--'+name,type=Path)
    p.add_argument('--buttons',default='');a=p.parse_args()
    if a.capture:
        if not all((a.core,a.rom,a.out)):p.error('Capture requires core, rom, out')
        capture(a.core,a.rom,a.out,[b for b in a.buttons.split(',') if b])
    else:
        if not all((a.nes_core,a.snes_core,a.out)):p.error('Require nes-core, snes-core, out')
        verify(a.nes_core,a.snes_core,a.out)
