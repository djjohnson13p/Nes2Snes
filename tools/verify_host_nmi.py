#!/usr/bin/env python3
"""Check host NMI context preservation without changing the guest event policy.

The host interrupts come from SNES vblank, not emulator stimulus APIs. WAI sites
are native test rendezvous only. Guest expected results never enter execution.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from libretro_runner import Runner
from route_evidence import atomic_json
from timeline_program import create_native, REGULAR, BRANCHES, memory_bytes
from timeline_fixture import cases, expected_initial
from timeline_host import PROTECTED, MODES
from opcodes6502 import OPS
from verify_timeline import compare


def sample(core: Path, rom: Path, out: Path, steps: int, *, host_expected: bool=True, ram_bytes: int=512, cartridge_bytes: int=0, exram: bool=False, ppu_blank: bool=False) -> dict:
    if type(ppu_blank) is not bool or (ppu_blank and (not exram or ram_bytes!=2048 or cartridge_bytes!=32768)):
        raise ValueError('Blank PPU snapshot requires full external-memory profile')
    if type(exram) is not bool:raise ValueError('ExRAM capture gate must be boolean')
    if type(cartridge_bytes) is not int or cartridge_bytes not in (0,32768):
        raise ValueError('Unsupported cartridge snapshot size')
    if type(host_expected) is not bool:
        raise ValueError('Host expectation must be boolean')
    if type(steps) is not int or not 1 <= steps <= 112:
        raise ValueError('Invalid dependent step count')
    if type(ram_bytes) is not int or ram_bytes not in (512,2048) or steps*(32+ram_bytes)>65536:
        raise ValueError('Capture shape exceeds native output bank')
    size=32+ram_bytes
    out.unlink(missing_ok=True)
    r = Runner(core, rom)
    try:
        ram = None
        for _ in range(2048):
            r.run(1)
            ram = r.memory()
            if ram[0x1FFF] in (0x5A, 0xEE) or (host_expected and ram[0x1D06]):
                break
        def u16(address): return int.from_bytes(ram[address:address+2], 'little')
        def u32(address): return int.from_bytes(ram[address:address+4], 'little')
        report = dict(complete=ram[0x1FFF] == 0x5A, marker=ram[0x1FFF], host_nmi_enabled=host_expected,
                      status=ram[0x18CE], completed_steps=u16(0x18D0),
                      records=[ram[0x10000+size*i:0x10000+size*(i+1)].hex() for i in range(steps)],
                      protected_memory=b''.join(ram[a:a+n] for a,n in PROTECTED).hex(),
                      host_frames=r.frames, host=dict(count=u32(0x1D00), depth=ram[0x1D04],
                          peak=ram[0x1D05], fault=ram[0x1D06], wait_hits=u16(0x1D08),
                          nested_wait_hits=u16(0x1D0A), work=u32(0x1D0C),
                          low_canary=ram[0x1E80], high_canary=ram[0x1FF1], min_sp=u16(0x1D1E)),
                      core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                      rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest())
        if ram_bytes==2048:
            report['final_guest_ram']=ram[:2048].hex()
            report['final_guest_context']=ram[0x18C0:0x18E0].hex()
        if cartridge_bytes:
            report['cartridge_ram']=ram[0x8000:0x8000+cartridge_bytes].hex()
        if exram:
            report['exram']=ram[0x4000:0x4400].hex()
        if ppu_blank:
            report['ciram']=ram[0x4800:0x5000].hex()
            report['ppu_state']=(ram[0x1C20:0x1C2D]+bytes(3)).hex()
            report['ppu_records']=[ram[0x5000+16*i:0x5010+16*i].hex() for i in range(steps)]
        atomic_json(out, report)
        return report
    finally:
        r.close()


def check_host(plan: dict, reference: dict, native: dict, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError('Unknown host mode')
    if native.get('host_nmi_enabled') is not True:
        raise ValueError('A no-host baseline is not host-interrupt evidence')
    result = compare(plan, reference, native)
    protected = native.get('protected_memory')
    if not isinstance(protected,str) or len(bytes.fromhex(protected))!=sum(n for _,n in PROTECTED):
        raise ValueError('Incomplete protected-memory observation')
    h = native.get('host')
    required={'count','depth','peak','fault','wait_hits','nested_wait_hits','work','low_canary','high_canary','min_sp'}
    if not isinstance(h,dict) or set(h) != required or any(type(v) is not int or v<0 for v in h.values()):
        raise ValueError('Invalid host observation metadata')
    if any(h[k]>maximum for k,maximum in [('count',0xFFFFFFFF),('work',0xFFFFFFFF),('wait_hits',65535),('nested_wait_hits',65535),('min_sp',65535),('fault',255),('depth',255),('peak',255)]):
        raise ValueError('Out-of-range host metadata')
    if not 0x1E90 <= h['min_sp'] < 0x1FF0:
        raise ValueError('Host stack watermark outside the reserved envelope')
    if h['fault'] or h['depth'] or not h['count'] or h['work'] != h['count']:
        raise ValueError('Host NMI fault, incomplete service or no exercised interrupt')
    if h['low_canary'] != 0xA5 or h['high_canary'] != 0x5A:
        raise ValueError('Host stack canary changed')
    expected=0
    if mode in ('loaded','alu','partial-save'):
        expected=sum(OPS[bytes.fromhex(r)[17]][0] in REGULAR | BRANCHES for r in reference['records'][1:])
    elif mode=='stack':
        expected=sum(bytes.fromhex(r)[16]!=0 for r in reference['records'][1:])
    elif mode!='free':
        expected=plan['steps']
    if h['wait_hits']!=expected or (mode!='free' and not expected):
        raise ValueError('The selected interruption site was not completely exercised')
    if mode=='nested':
        if h['peak']!=2 or h['nested_wait_hits']*2!=h['count'] or h['nested_wait_hits']<expected:
            raise ValueError('Nested real host interrupts were not completely exercised')
    elif h['peak']!=1 or h['nested_wait_hits']:
        raise ValueError('Unexpected nested interrupt')
    return dict(mode=mode,host=h,**result)


def execute(core: Path, rom: Path, out: Path, steps: int, *, host_expected: bool=True, ram_bytes: int=512, cartridge_bytes: int=0, exram: bool=False, ppu_blank: bool=False) -> dict:
    subprocess.run([sys.executable,__file__,'--sample','timeline','--core',str(core),'--rom',str(rom),
                    '--out',str(out),'--steps',str(steps),'--ram-bytes',str(ram_bytes),'--cartridge-bytes',str(cartridge_bytes)]+([] if host_expected else ['--baseline'])+(['--exram'] if exram else [])+(['--ppu-blank'] if ppu_blank else []),check=True,timeout=90,
                   stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def sample_registers(core: Path, rom: Path, out: Path) -> dict:
    out.unlink(missing_ok=True)
    r=Runner(core,rom)
    try:
        for _ in range(2048):
            r.run(1);ram=r.memory()
            if ram[0x1FFF] in (0x5A,0xEE) or ram[0x1D06]:break
        h=dict(count=int.from_bytes(ram[0x1D00:0x1D04],'little'),depth=ram[0x1D04],
               peak=ram[0x1D05],fault=ram[0x1D06],wait_hits=int.from_bytes(ram[0x1D08:0x1D0A],'little'),
               nested_wait_hits=int.from_bytes(ram[0x1D0A:0x1D0C],'little'),
               work=int.from_bytes(ram[0x1D0C:0x1D10],'little'),
               low_canary=ram[0x1E80],high_canary=ram[0x1FF1],
               min_sp=int.from_bytes(ram[0x1D1E:0x1D20],'little'))
        report=dict(complete=ram[0x1FFF]==0x5A,marker=ram[0x1FFF],
                    completed_cases=int.from_bytes(ram[0x1D10:0x1D12],'little'),host=h,
                    records=[ram[0x10000+145*i:0x10000+145*(i+1)].hex() for i in range(256)],
                    core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),host_frames=r.frames)
        atomic_json(out,report);return report
    finally:r.close()


def check_registers(report: dict, *, nested: bool, mirror: bool) -> dict:
    from host_nmi_fixture import inputs,scratch
    if type(nested) is not bool or type(mirror) is not bool:
        raise ValueError('Native context settings must be booleans')
    if (report.get('complete') is not True or type(report.get('marker')) is not int or report['marker']!=0x5A
            or type(report.get('completed_cases')) is not int or report['completed_cases']!=256
            or report.get('fault') is not None):
        raise ValueError('Incomplete or fault-bearing register run')
    rows=report.get('records')
    if not isinstance(rows,list) or len(rows)!=256:raise ValueError('Missing register cases')
    for i,(row,text) in enumerate(zip(inputs(),rows)):
        raw=bytes.fromhex(text)
        x=row['x']&255 if row['p']&16 else row['x'];y=row['y']&255 if row['p']&16 else row['y']
        wanted=(row['a'].to_bytes(2,'little')+x.to_bytes(2,'little')+y.to_bytes(2,'little')
                +row['d'].to_bytes(2,'little')+bytes((row['dbr'],row['p']))
                +(0x1FF0).to_bytes(2,'little')+bytes((0x80 if mirror else 0,))+scratch())
        if raw!=wanted:raise RuntimeError(f'Host return changed register or scratch case {i}')
    h=report.get('host')
    expected=dict(count=512 if nested else 256,depth=0,peak=2 if nested else 1,fault=0,
                  wait_hits=256,nested_wait_hits=256 if nested else 0,work=512 if nested else 256,
                  low_canary=0xA5,high_canary=0x5A)
    if not isinstance(h,dict) or set(h)!=set(expected)|{'min_sp'} or any(type(v) is not int for v in h.values()):
        raise ValueError('Invalid register-run host observations')
    if any(h[k]!=v for k,v in expected.items()) or not 0x1E90 <= h['min_sp'] < 0x1FF0:
        raise ValueError('Host service, nesting or stack preservation was not verified')
    return dict(passed=True,cases=256,register_bytes=256*13,scratch_bytes=256*132,
                mirror_bank=0x80 if mirror else 0,nested=nested,host=h)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample',choices=['timeline','registers']);p.add_argument('--steps',type=int,default=112);p.add_argument('--ram-bytes',type=int,choices=(512,2048),default=512)
    p.add_argument('--cartridge-bytes',type=int,choices=(0,32768),default=0);p.add_argument('--exram',action='store_true');p.add_argument('--ppu-blank',action='store_true')
    p.add_argument('--baseline',action='store_true',help='Only for a no-host baseline; host metadata is uninitialized and is not acceptance evidence')
    for key in ('core','rom','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    report=sample_registers(a.core,a.rom,a.out) if a.sample=='registers' else sample(a.core,a.rom,a.out,a.steps,host_expected=not a.baseline,ram_bytes=a.ram_bytes,cartridge_bytes=a.cartridge_bytes,exram=a.exram,ppu_blank=a.ppu_blank)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
