#!/usr/bin/env python3
"""Compare render-aligned replay samples without publishing game-derived images.

Both captures must use the same input script and emulator core. Timing is counted
in emulated SNES frames between matching logical game frames, not wall time.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def compare(baseline: Path, candidate: Path, out: Path) -> dict:
    old = json.loads((baseline / 'replay.json').read_text())
    new = json.loads((candidate / 'replay.json').read_text())
    if old.get('alignment', 'legacy-previous-poll') != new.get('alignment', 'legacy-previous-poll'):
        raise ValueError('Replay alignment methods must match; recapture both builds')
    for field in ('input_sha256', 'core_sha256'):
        if old[field] != new[field]:
            raise ValueError(f'Replays must have identical {field}')
    if [(s['name'], s['render_frame']) for s in old['samples']] != [
        (s['name'], s['render_frame']) for s in new['samples']
    ]:
        raise ValueError('Sample names and logical render frames must match')
    samples, intervals = [], []
    total_pixels = total_mismatches = 0
    previous = None
    for a, b in zip(old['samples'], new['samples']):
        name = a['name']
        if not name or Path(name).name != name or name in ('.', '..'):
            raise ValueError('Invalid sample name')
        with Image.open(baseline / (name + '.png')) as image:
            left = np.asarray(image.convert('RGB'))
        with Image.open(candidate / (name + '.png')) as image:
            right = np.asarray(image.convert('RGB'))
        if left.shape != right.shape:
            raise ValueError(f'Image dimensions differ for {name}')
        mismatches = int(np.any(left != right, axis=2).sum())
        pixels = int(left.shape[0] * left.shape[1])
        total_pixels += pixels
        total_mismatches += mismatches
        samples.append(dict(name=name, render_frame=a['render_frame'],
                            pixels_checked=pixels, pixel_mismatches=mismatches))
        if previous is not None:
            pa, pb = previous
            logical = a['render_frame'] - pa['render_frame']
            before = a['snes_frame'] - pa['snes_frame']
            after = b['snes_frame'] - pb['snes_frame']
            if min(logical, before, after) <= 0:
                raise ValueError('Replay frame numbers must increase strictly')
            intervals.append(dict(ending_sample=name, logical_frames=logical,
                                  baseline_snes_frames=before, candidate_snes_frames=after,
                                  speed_ratio=before / after,
                                  candidate_snes_frames_per_logical_frame=after / logical))
        previous = a, b
    result = dict(alignment=new.get('alignment', 'legacy-previous-poll'),baseline_rom_sha256=old['rom_sha256'],
                  candidate_rom_sha256=new['rom_sha256'],
                  core_sha256=new['core_sha256'], input_sha256=new['input_sha256'],
                  pixels_checked=total_pixels, pixel_mismatches=total_mismatches,
                  samples=samples, intervals=intervals,
                  scope='Selected fixed-input, render-aligned captures only; not frame-by-frame or full-game equivalence.')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.baseline, args.candidate, args.out)
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report['pixel_mismatches'] else 0)
