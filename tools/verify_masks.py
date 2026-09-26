#!/usr/bin/env python3
"""Compare EVERY steady-scene pixel against an independent NES core.

No ignored rows or clipping of the comparison region. Binary black/white scene
geometry is compared, not analog colors. Runs each emulator in its own process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from build_native import ROOT, build
from mask_fixture import create


def verify(nes_core: Path, snes_core: Path, out: Path,
           masks: tuple[int, ...] = tuple(range(0, 32, 2)),
           sizes: tuple[bool, ...] = (False, True)) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for sprite16 in sizes:
        for mask in masks:
            fixture = out/f'm{mask:02x}-s{16 if sprite16 else 8}'
            create(fixture, mask, sprite16)
            built = build(fixture/'fixture.nes', fixture, fixture/'snes')
            for tag, core, rom, frames in (
                ('nes', nes_core, fixture/'fixture.nes', 100),
                ('snes', snes_core, fixture/'snes/native-prototype.sfc', 160)):
                subprocess.run([sys.executable, str(ROOT/'tools/libretro_runner.py'),
                    '--core', str(core), '--rom', str(rom), '--frames', str(frames),
                    '--out', str(fixture/(tag+'.png'))],
                    check=True, stdout=subprocess.DEVNULL)
            aa = np.asarray(Image.open(fixture/'nes.png').convert('RGB'))
            bb = np.asarray(Image.open(fixture/'snes.png').convert('RGB'))
            if aa.shape != (224, 256, 3) or bb.shape != aa.shape:
                raise ValueError('Unexpected frame dimensions')
            diff = (aa.max(axis=2) > 128) != (bb.max(axis=2) > 128)
            row = dict(mask=mask, sprite16=sprite16, snes_sha256=built['sha256'],
                pixels=int(diff.size), mismatches=int(diff.sum()),
                left_edge_mismatches=int(diff[:, :8].sum()),
                other_mismatches=int(diff[:, 8:].sum()), passed=not bool(diff.any()))
            records.append(row)
            (fixture/'verification.json').write_text(json.dumps(row, indent=2)+'\n')
            print(json.dumps(row), flush=True)
    report = dict(scope='All 224x256 pixel classes; steady original fixture; no excluded pixels',
        cases=records, pixels=sum(x['pixels'] for x in records),
        mismatches=sum(x['mismatches'] for x in records),
        passed=bool(records) and all(x['passed'] for x in records),
        nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
        snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
        commercial_game_content=False)
    (out/'mask-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    return report

# Full rendering-disable is NOT included in this passing scope: the pinned
# NES cores disagree. probe_mask_oracles.py retains that failing diagnostic.
SPLIT_CASES = ((0x0a, 0x1e), (0x1e, 0x0a), (0x1e, 0x10),
               (0x10, 0x1e), (0x18, 0x1e), (0x1e, 0x18))


def verify_splits(nes_core: Path, snes_core: Path, out: Path) -> dict:
    """Test both screen regions, explicitly retaining partial-row errors.

    An NES IRQ changes PPUMASK partway through line 96. The frame-scheduled
    port currently switches a whole line, so line 88 after crop is NOT exact.
    Mismatches there are recorded, not asserted away or counted as matching.
    """
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for top, bottom in SPLIT_CASES:
        fixture = out/f't{top:02x}-b{bottom:02x}'
        create(fixture, top, split_mask=bottom)
        built = build(fixture/'fixture.nes', fixture, fixture/'snes')
        for tag, core, rom, frames in (
            ('nes', nes_core, fixture/'fixture.nes', 100),
            ('snes', snes_core, fixture/'snes/native-prototype.sfc', 160)):
            subprocess.run([sys.executable, str(ROOT/'tools/libretro_runner.py'),
                '--core', str(core), '--rom', str(rom), '--frames', str(frames),
                '--out', str(fixture/(tag+'.png'))], check=True,
                stdout=subprocess.DEVNULL)
        aa = np.asarray(Image.open(fixture/'nes.png').convert('RGB'))
        bb = np.asarray(Image.open(fixture/'snes.png').convert('RGB'))
        if aa.shape != (224, 256, 3) or bb.shape != aa.shape:
            raise ValueError('Unexpected frame dimensions')
        diff = (aa.max(axis=2) > 128) != (bb.max(axis=2) > 128)
        transition = 88
        stable_mismatches = int(diff[:transition].sum() + diff[transition+1:].sum())
        row = dict(top_mask=top, bottom_mask=bottom, snes_sha256=built['sha256'],
            pixels=int(diff.size), mismatches=int(diff.sum()),
            stable_pixels=int(diff.size-256), stable_mismatches=stable_mismatches,
            transition_row=transition, transition_mismatches=int(diff[transition].sum()),
            full_frame_exact=not bool(diff.any()), passed=stable_mismatches == 0)
        records.append(row)
        (fixture/'verification.json').write_text(json.dumps(row, indent=2)+'\n')
        print(json.dumps(row), flush=True)
    report = dict(scope='Independent NES oracle; one partial IRQ row reported separately, not exact',
        cases=records, pixels=sum(x['pixels'] for x in records),
        stable_pixels=sum(x['stable_pixels'] for x in records),
        stable_mismatches=sum(x['stable_mismatches'] for x in records),
        mismatches=sum(x['mismatches'] for x in records),
        full_frame_exact=all(x['full_frame_exact'] for x in records),
        passed=all(x['passed'] for x in records), commercial_game_content=False,
        nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
        snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest())
    (out/'mask-split-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def verify_cycle(snes_core: Path, out: Path, references: Path, sprite16: bool = False) -> dict:
    """Verify settled presentations after all 16 mask changes and counter wrap.

    Three guest IDs around each change are recorded as transition samples, not
    claimed to have a precisely aligned screenshot. The independent static NES
    images remain the oracle for every settled comparison.
    """
    from libretro_runner import Runner
    out.mkdir(parents=True, exist_ok=True)
    create(out, sprite16=sprite16, cycle=True)
    built = build(out/'fixture.nes', out, out/'snes')
    expected = {mask: np.asarray(Image.open(references/f'm{mask:02x}-s{16 if sprite16 else 8}'/'nes.png').convert('RGB')).max(2)>128
                for mask in range(0,32,2)}
    for a in expected.values():
        if a.shape != (224,256): raise ValueError('Unexpected oracle dimensions')
    r = Runner(snes_core, out/'snes/native-prototype.sfc')
    seen=set(); masks=set(); checked=0; transition=0; mismatches=0; previous=0
    try:
        for _ in range(4096):
            r.run(1); mem=r.memory()
            if mem[0x90f]: raise RuntimeError('Bridge fault during mask changes')
            presented=int.from_bytes(mem[0x974:0x976], 'little')
            if previous and previous not in seen:
                seen.add(previous)
                if previous%16 in (0,1,15):
                    transition += 1
                else:
                    mask=(previous>>3)&0x1e
                    actual=r.rgb().max(2)>128
                    if actual.shape!=(224,256): raise ValueError('Unexpected frame dimensions')
                    mismatches += int(np.count_nonzero(actual!=expected[mask]))
                    checked += 1; masks.add(mask)
            previous=presented
            if len(seen)>=272: break
        else: raise RuntimeError('Mask-cycle fixture did not complete')
        report=dict(scope='Settled presentations only; change-boundary frames are not aligned or claimed exact',
                    sprite16=sprite16, frames_observed=len(seen), frames_checked=checked,
                    transition_samples_not_compared=transition, masks=sorted(masks),
                    pixels_checked=checked*224*256, mismatches=mismatches,
                    snes_sha256=built['sha256'], passed=(checked>=200 and len(masks)==16 and mismatches==0))
        (out/'cycle-verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
        return report
    finally: r.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('nes-core', 'snes-core', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--scope', choices=('all', 'steady8', 'steady16', 'splits'), default='all')
    args = parser.parse_args()
    reports = []
    for key, size in (('steady8', False), ('steady16', True)):
        if args.scope in ('all', key):
            reports.append(verify(args.nes_core, args.snes_core, args.out/key, sizes=(size,)))
    if args.scope == 'all':
        for key, size in (('steady8', False), ('steady16', True)):
            reports.append(verify_cycle(args.snes_core, args.out/('cycle16' if size else 'cycle8'), args.out/key, size))
    if args.scope in ('all', 'splits'):
        reports.append(verify_splits(args.nes_core, args.snes_core, args.out/'splits'))
    raise SystemExit(not all(r['passed'] for r in reports))
