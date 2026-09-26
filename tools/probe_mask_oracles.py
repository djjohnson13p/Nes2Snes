#!/usr/bin/env python3
"""Record (do not conceal or bless) disagreement on MMC5 rendering-disable.

This is a diagnostic, NOT a passing SNES accuracy test. All three unmodified
cores run the same authored source or its native translation. It intentionally
retains entire images, per-frame hashes, pixel-class totals, and disagreement.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from build_native import build, ROOT
from mask_fixture import create


def record(core: Path, rom: Path, out: Path, frames: tuple[int,...], nestopia: bool=False) -> dict:
    from libretro_runner import Runner
    out.mkdir(parents=True,exist_ok=True)
    options={'nestopia_blargg_ntsc_filter':'disabled'} if nestopia else {}
    r=Runner(core,rom,options=options); snapshots=[]
    try:
        for f in frames:
            r.run(f-r.frames)
            a=r.rgb()
            if a.shape!=(224,256,3): raise RuntimeError(f'Unexpected image shape: {a.shape}')
            w=a.max(2)>128
            r.save_png(out/f'frame-{f}.png')
            snapshots.append(dict(frame=f, pixels=int(w.size), white_pixels=int(w.sum()),
                white_pixels_below_row_100=int(w[100:].sum()),
                pixel_class_sha256=hashlib.sha256(w.tobytes()).hexdigest(),
                guest_nmi_counter=r.memory()[0x70]))
        report=dict(core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
            rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
            options=options,frames=snapshots)
        (out/'samples.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:r.close()


def probe(fceumm: Path, nestopia: Path, snes: Path, out: Path) -> dict:
    create(out/'fixture',0x1e,split_mask=0)
    build(out/'fixture/fixture.nes',out/'fixture',out/'fixture/snes')
    reports={}
    for name,core,rom,frames in (
        ('fceumm',fceumm,out/'fixture/fixture.nes','99,100,101,102'),
        ('nestopia',nestopia,out/'fixture/fixture.nes','99,100,101,102'),
        ('snes9x',snes,out/'fixture/snes/native-prototype.sfc','159,160,161,162')):
        command=[sys.executable,str(Path(__file__).resolve()),'--worker','--core',str(core),
            '--rom',str(rom),'--out',str(out/name),'--frames',frames]
        if name=='nestopia':command.append('--nestopia-options')
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
        reports[name]=json.loads((out/name/'samples.json').read_text())
    result=dict(status='diagnostic_only_not_accuracy_pass',
        scope='Complete layer disable following MMC5 IRQ; independent reference disagreement remains unresolved; no hardware result',
        fixture_sha256=hashlib.sha256((out/'fixture/fixture.nes').read_bytes()).hexdigest(),
        emulators=reports,
        fceumm_observed_pixel_classes=len({f['pixel_class_sha256'] for f in reports['fceumm']['frames']}),
        nestopia_observed_pixel_classes=len({f['pixel_class_sha256'] for f in reports['nestopia']['frames']}))
    (out/'oracle-disagreement.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--worker',action='store_true')
    p.add_argument('--core',type=Path);p.add_argument('--rom',type=Path)
    p.add_argument('--frames');p.add_argument('--nestopia-options',action='store_true')
    for n in ('fceumm','nestopia','snes'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.worker:
        if not all((a.core,a.rom,a.frames)):p.error('Worker needs core, rom and frames')
        fs=tuple(map(int,a.frames.split(',')))
        if not fs or fs!=tuple(sorted(set(fs))) or not 1<=fs[0]<=fs[-1]<=4096:p.error('Invalid frame sequence')
        r=record(a.core,a.rom,a.out,fs,a.nestopia_options)
    else:
        if not all((a.fceumm,a.nestopia,a.snes)):p.error('Require all three independent cores')
        r=probe(a.fceumm,a.nestopia,a.snes,a.out)
    print(json.dumps(r,indent=2))
