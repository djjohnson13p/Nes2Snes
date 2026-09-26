#!/usr/bin/env python3
"""Compare steady changed-fill screens with an unmodified independent NES core.

All pixels are compared as black/white classes. Analog color, mid-frame fill
changes, extended attributes and physical-console behavior are outside scope.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image
from build_native import ROOT, build
from fill_mode_fixture import create
from libretro_runner import Runner

CASES = [(3,0,117,c) for c in range(4)] + [(3,0,t,0) for t in (0,1,15,64,127,255)] + [
    (3,0,3,1),(3,1,3,2),(3,2,3,3),(3,3,3,0),
    (3,0,3,0),(3,2,3,254)]

def capture(core: Path, rom: Path, out: Path, platform: str) -> None:
    out.mkdir(parents=True,exist_ok=True)
    runner=Runner(core,rom,options={'nestopia_blargg_ntsc_filter':'disabled'})
    try:
        runner.run(100 if platform=='nes' else 160)
        mem=runner.memory()
        if not 33 <= mem[0x70] <= 200:
            raise RuntimeError(f'Fill-change frame not reached: {mem[0x70]}')
        if platform=='snes' and mem[0x90F]:
            raise RuntimeError('Guest execution fault '+mem[0x90c:0x910].hex())
        runner.save_png(out/'screen.png')
        if platform=='snes':
            (out/'vram.bin').write_bytes(runner.memory(3))
        (out/'capture.json').write_text(json.dumps(dict(nmi_count=mem[0x70],platform=platform,
            frames=runner.frames,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest()))+'\n')
    finally:runner.close()

def verify(nes_core: Path,snes_core: Path,out: Path,previous_root: Path|None=None,fceumm_core: Path|None=None) -> dict:
    out.mkdir(parents=True,exist_ok=True);rows=[];negative=None;disagreement=None
    for case,values in enumerate(CASES):
        start_tile,start_color,tile,color=values
        directory=out/f'case-{case:02d}'
        create(directory,tile,color,start_tile,start_color)
        def shot(core,rom,tag,platform):
            dest=directory/tag
            subprocess.run([sys.executable,str(ROOT/'tools/verify_fill_mode.py'), '--capture',
                '--core',str(core),'--rom',str(rom),'--out',str(dest),'--platform',platform],
                check=True,stdout=subprocess.DEVNULL,timeout=90)
            pixels=np.array(Image.open(dest/'screen.png').convert('RGB')).max(2)>128
            if pixels.shape!=(224,256):raise ValueError('Unexpected frame size')
            return pixels
        reference=shot(nes_core,directory/'fixture.nes','nes','nes')
        if case==15 and fceumm_core:
            second=shot(fceumm_core,directory/'fixture.nes','fceumm-diagnostic','nes')
            disagreement=dict(status='reference-disagreement-not-a-pass',
                primary_vs_fceumm_pixel_mismatches=int(np.count_nonzero(second!=reference)),
                pixels_compared=int(reference.size),
                fceumm_core_sha256=hashlib.sha256(fceumm_core.read_bytes()).hexdigest(),
                register="$5107",value=color,documented_low_bits=color&3,
                explanation='Pinned FCEUmm expands unmasked upper bits; Nestopia and the low-two-bit renderer agree. Physical hardware has not been tested.')
            (directory/'reference-disagreement.json').write_text(json.dumps(disagreement,indent=2)+'\n')
        for coalesced in (False,True):
            tag='coalesced' if coalesced else 'legacy-dma'
            built=build(directory/'fixture.nes',directory,directory/tag,coalesced_nt_dma=coalesced,fill_cache_fix=True)
            observed=shot(snes_core,directory/tag/'native-prototype.sfc',tag,'snes')
            mismatch=int(np.count_nonzero(observed!=reference))
            raw=(directory/tag/'vram.bin').read_bytes()
            if len(raw)!=65536:raise ValueError('Full VRAM not available')
            tileword=(0x2000|((color&3)<<10)|tile).to_bytes(2,'little')
            badwords=0
            for base in (0x4000,0x4800,0x5000,0x5800,0x6000):
                badwords+=sum(raw[pos:pos+2]!=tileword for pos in range(base,base+1920,2))
            row=dict(case=case,start_tile=start_tile,start_color=start_color,tile=tile,color=color,
                     coalesced=coalesced,pixels_checked=int(reference.size),pixel_mismatches=mismatch,
                     tile_words_checked=4800,tile_word_mismatches=badwords,rom_sha256=built['sha256'])
            rows.append(row)
            (directory/tag/'verification.json').write_text(json.dumps(row,indent=2)+'\n')
            if mismatch or badwords:raise RuntimeError(f'Fill mismatch: {row}')
        if case==0:
            # Use the actual earlier source when supplied. Otherwise only
            # the explicit no-fix control is claimed, never a historical build.
            previous=directory/'previous'
            if previous_root:
                subprocess.run([sys.executable,str(previous_root/'tools/build_native.py'),
                    '--rom',str(directory/'fixture.nes'),'--trace',str(directory),'--out',str(previous)],
                    check=True,stdout=subprocess.DEVNULL,timeout=90)
            else:
                build(directory/'fixture.nes',directory,previous,fill_cache_fix=False)
            pixels=shot(snes_core,previous/'native-prototype.sfc','negative','snes')
            differences=int(np.count_nonzero(pixels!=reference))
            if differences==0:raise RuntimeError('Stale-background negative control unexpectedly passed')
            negative=dict(kind='actual-previous-source' if previous_root else 'explicit-no-fix-option',
                          pixel_mismatches=differences,pixels_compared=int(reference.size),
                          expected_failure_observed=True)
        print(f'{case+1}/{len(CASES)} fill changes verified against NES',flush=True)
    result=dict(passed=True,cases=len(CASES),configurations=len(rows),
                pixels_checked=sum(r['pixels_checked'] for r in rows),pixel_mismatches=0,
                tile_words_checked=sum(r['tile_words_checked'] for r in rows),tile_word_mismatches=0,
                negative_control=negative,reference_disagreement=disagreement,
                nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
                snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
                scope=__doc__,results=rows)
    (out/'fill-mode-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true')
    for name in ('core','nes-core','snes-core','rom','previous-root','fceumm-core'):
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--platform',choices=('nes','snes'))
    args=parser.parse_args()
    if args.capture:
        if not all((args.core,args.rom,args.platform)):parser.error('Capture needs core, ROM, platform')
        capture(args.core,args.rom,args.out,args.platform)
    else:
        if not args.nes_core or not args.snes_core:parser.error('Require both independent cores')
        result=verify(args.nes_core,args.snes_core,args.out.resolve(),args.previous_root,args.fceumm_core)
        print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
