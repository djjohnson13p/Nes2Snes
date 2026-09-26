#!/usr/bin/env python3
"""Differentially check the native bridge against an independent NES emulator.

Run each libretro core in its own subprocess: libretro implementations maintain
process-global state. The fixture is original procedural input, not game data.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
from libretro_runner import Runner

def capture(core:Path,rom:Path,out:Path,limit:int):
    r=Runner(core,rom)
    try:
        for _ in range(limit):
            r.run(1);m=r.memory()
            if len(m)>=0x800 and m[0x7E]==0x5A:
                out.write_bytes(m[:0x800])
                diagnostics={}
                if len(m)>=0x3900:
                    out.with_suffix('.oam.bin').write_bytes(m[0x3800:0x3900])
                if len(m)>=0x974:
                    diagnostics={name:int.from_bytes(m[a:a+4],'little') for name,a in
                                 (('cop_calls',0x960),('quick_zp_calls',0x964),
                                  ('quick_indirect_calls',0x968),('quick_io_calls',0x96c),('quick_ppu_calls',0x970),('direct_write_calls',0x980),('simple_direct_write_calls',0x984),('direct_bank_calls',0x988),('quick_indexed_memory_calls',0x990),('quick_indexed_apu_calls',0x994),('indexed_dummy_io_reads',0x998))}
                out.with_suffix('.diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
                return
        raise RuntimeError(f'CPU fixture did not complete in {limit} frames; diagnostic RAM={m[0x90c:0x910].hex() if len(m)>0x910 else "NES"}')
    finally:r.close()

def verify(nes_core:Path,snes_core:Path,fixture:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    source=json.loads((fixture/'trace-summary.json').read_text())
    if not source.get('procedural_fixture'):raise ValueError('Expected the original procedural CPU fixture.')
    build_meta=json.loads((fixture/'snes/native-build.json').read_text())
    limit=3000 if build_meta.get('test_bank_switch_stress') else 300
    for name,core,rom in [('nes',nes_core,fixture/'fixture.nes'),('snes',snes_core,fixture/'snes/native-prototype.sfc')]:
        subprocess.run([sys.executable,__file__,'--capture','--core',str(core),'--rom',str(rom),
                        '--output',str(out/(name+'.ram')), '--limit',str(limit)],check=True)
    nes=(out/'nes.ram').read_bytes();snes=(out/'snes.ram').read_bytes()
    mismatches=[]
    for item in source['records']:
        a=item['address'];n=nes[a:a+4];s=snes[a:a+4]
        if n!=s:mismatches.append({'test':item['name'],'nes':n.hex(),'snes':s.hex()})
    diagnostics=json.loads((out/'snes.diagnostics.json').read_text())
    build_meta=json.loads((fixture/'snes/native-build.json').read_text())
    if 'fastpath_stress_seed' in source:
        for flag,counter in [('quick_zero_page','quick_zp_calls'),
                             ('quick_indirect_reads','quick_indirect_calls'),
                             ('quick_io','quick_io_calls')]:
            exercised=diagnostics.get(counter,0)
            if flag=='quick_io' and build_meta.get('direct_bank_switches'):
                exercised += diagnostics.get('direct_bank_calls',0)
            if build_meta.get(flag) and not exercised:
                raise RuntimeError(f'Enabled path {flag} was not exercised')
    if source.get('direct_fixture') and build_meta.get('direct_calls'):
        counter = 'simple_direct_write_calls' if build_meta.get('simple_direct_writes') else 'direct_write_calls'
        if diagnostics.get(counter) != 95 or not diagnostics.get('quick_ppu_calls'):
            raise RuntimeError('Must exercise 95 direct writes (including two initialization writes) and the C0 COP fallback')
    if 'ppu_fixture_seed' in source:
        counter = 'direct_write_calls' if build_meta.get('direct_calls') else 'quick_ppu_calls'
        if (build_meta.get('direct_calls') or build_meta.get('quick_ppu_writes')) and not diagnostics.get(counter):
            raise RuntimeError(f'Enabled PPU write path was not exercised: {counter}')
    if source.get('safe_address_fixture') and build_meta.get('safe_addresses'):
        if not build_meta.get('safe_native_sites') or diagnostics.get('cop_calls') != 0:
            raise RuntimeError('Safe-address fixture must use native replacements without COP')
    if source.get('bank_switch_fixture') and build_meta.get('direct_bank_switches'):
        if diagnostics.get('direct_bank_calls', 0) < 90 or diagnostics.get('cop_calls', 0) == 0:
            raise RuntimeError('Must exercise the direct mapper returns and C0 COP fallback')
    oam_check=None
    if 'expected_oam_source_page' in source:
        address=source['expected_oam_source_page']*256
        expected=nes[address:address+256]
        actual=(out/'snes.oam.bin').read_bytes()
        oam_check={'bytes_checked':256,'mismatch_count':sum(a!=b for a,b in zip(expected,actual))}
        if len(actual)!=256 or actual!=expected:raise RuntimeError('Native OAM page copy mismatch')
    result={'records_checked':len(source['records']),'bytes_checked':len(source['records'])*4,
            'mismatch_count':len(mismatches),'mismatches':mismatches,
            'native_execution_counters':diagnostics,'oam_copy':oam_check,
            'scope':('NMOS indexed PPU dummy reads, page crossings and RMW bus side effects; not cycle accuracy.' if source.get('indexed_bus_fixture') else 'Indexed RAM/ROM boundaries, flags, hardware fallback and APU write events; not full-game coverage.' if source.get('indexed_memory_fixture') else 'Explicit five-step APU length/status event oracle, including reload/disable and store flags; no periodic cycle-timing claim.' if source.get('apu_counter_fixture') else 'Original indexed zero-base and internal RAM-mirror boundary cases; not mapper or full-game coverage.' if source.get('safe_address_fixture') else 'Original STA/STX/STY stores and flags in all 32 mapped execution combinations, including C0 fallback.' if source.get('direct_fixture') else 'Original buffered PPU, register aliases, palette mirrors, status latch and store flags; rendering disabled, not cycle accuracy.' if 'ppu_fixture_seed' in source else 'Seeded indexed-zero-page/indirect reads, switchable-code bank changes and serial joypad fallback. Not complete game validation.' if 'fastpath_stress_seed' in source else 'Original synthetic documented-6502 instructions and all 32 supported mapper combinations. Not complete game validation.')}
    (out/'cpu-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if mismatches:raise RuntimeError('Independent CPU comparison failed.')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',action='store_true')
    for arg in ('core','rom','output','nes-core','snes-core','fixture','out'):p.add_argument('--'+arg,type=Path)
    p.add_argument('--limit',type=int,default=300)
    a=p.parse_args()
    if a.capture:
        if not all((a.core,a.rom,a.output)):p.error('--capture requires --core, --rom, --output')
        capture(a.core,a.rom,a.output,a.limit)
    else:
        if not all((a.nes_core,a.snes_core,a.fixture,a.out)):p.error('Require --nes-core, --snes-core, --fixture, --out')
        verify(a.nes_core,a.snes_core,a.fixture,a.out)
