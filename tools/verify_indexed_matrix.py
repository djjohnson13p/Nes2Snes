#!/usr/bin/env python3
"""Build and independently execute indexed-memory and dummy-bus fixtures.

Commercial ROMs and instrumented emulator cores are not required. Outputs stay
in the requested build directory; any comparison failure terminates the suite.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from build_native import build
from indexed_memory_fixture import create
from indexed_bus_fixture import create as bus_create
from verify_native_cpu import verify


def run(nes_core: Path, snes_core: Path, out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    configurations = [(f'seed-{i}', i, False, True, True) for i in range(4)]
    configurations += [('c0', 7, True, True, True), ('generic', 7, True, False, True),
                       ('no-direct', 13, False, True, False), ('no-native-ram', 19, False, True, True)]
    for name, seed, c0, indexed, direct in configurations:
        directory=out/name
        create(directory, seed, c0)
        build(directory/'fixture.nes',directory,directory/'snes',quick_indexed=indexed,
              direct=direct,experimental_audio=True,audio_counters=True,audio_sweep=True,
              safe_addresses=name!='no-native-ram')
        result=verify(nes_core,snes_core,directory,directory/'verification')
        counters=result['native_execution_counters']
        if bool(counters['quick_indexed_memory_calls']) != indexed:
            raise RuntimeError(f'{name}: selected memory path was not exercised as expected')
        if bool(counters['quick_indexed_apu_calls']) != indexed:
            raise RuntimeError(f'{name}: selected APU path was not exercised as expected')
        if not counters['indexed_dummy_io_reads']:
            raise RuntimeError(f'{name}: missing indexed hardware dummy reads')
        results.append(dict(name=name,**result))
    for name,indexed,direct in [('bus',True,True),('bus-generic',False,True),('bus-no-direct',True,False)]:
        directory=out/name;bus_create(directory)
        build(directory/'fixture.nes',directory,directory/'snes',quick_indexed=indexed,direct=direct)
        result=verify(nes_core,snes_core,directory,directory/'verification')
        if result['native_execution_counters']['indexed_dummy_io_reads'] != 36:
            raise RuntimeError(f'{name}: expected 36 side-effecting dummy reads')
        results.append(dict(name=name,**result))
    report=dict(configurations=len(results),records_checked=sum(r['records_checked'] for r in results),
                bytes_checked=sum(r['bytes_checked'] for r in results),mismatch_count=sum(r['mismatch_count'] for r in results),
                nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
                snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),results=results,
                scope='Procedural indexed addressing/ALU flags and PPU dummy-read side effects; not CPU-cycle timing, open-bus fidelity or whole-game validation.')
    (out/'indexed-matrix.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nes-core',type=Path,required=True);p.add_argument('--snes-core',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=run(a.nes_core.resolve(),a.snes_core.resolve(),a.out.resolve())
    print(json.dumps({k:v for k,v in r.items() if k!='results'},indent=2))
