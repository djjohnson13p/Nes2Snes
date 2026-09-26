#!/usr/bin/env python3
"""Verify opt-in defaults within one source revision, not across runtime fixes.

Historical byte-identity claims remain in their original reports. This check
compares omitted options with explicit False on the same current source. It does
not replace independent execution tests or known-failing historical controls.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

from build_native import build
from dispatch_fixture import create as dispatch_fixture
from fill_mode_fixture import create as fill_fixture
from native_fixture import create as cpu_fixture
from indirect_x_fixture import create as indirect_x_fixture

FIXTURES = {'cpu': cpu_fixture, 'fill': fill_fixture, 'dispatch': dispatch_fixture,
            'indirect-x': indirect_x_fixture}
OPTIONS = {'native_inline_dispatch': 'native_inline_dispatch',
           'coalesced_nt_dma': 'coalesced_nametable_dma',
           'fill_cache_fix': 'fill_cache_fix',
           'quick_indirect_x': 'quick_indirect_x'}


def run(out: Path, fixtures: tuple[str, ...] = ('cpu', 'fill', 'dispatch', 'indirect-x')) -> dict:
    if not fixtures or len(set(fixtures)) != len(fixtures) or any(
            name not in FIXTURES for name in fixtures):
        raise ValueError('Require nonempty, unique, known fixture names')
    parameters = inspect.signature(build).parameters
    if any(parameters[name].default is not False for name in OPTIONS):
        raise RuntimeError('An opt-in option is no longer disabled by default')
    rows = []
    for name in fixtures:
        directory = out / name
        FIXTURES[name](directory)
        default = build(directory/'fixture.nes', directory, directory/'default')
        disabled = build(directory/'fixture.nes', directory, directory/'disabled',
                         **{option: False for option in OPTIONS})
        if any(info[key] is not False for info in (default, disabled)
               for key in OPTIONS.values()):
            raise RuntimeError(f'{name}: an opt-in path was enabled')
        first = (directory/'default/native-prototype.sfc').read_bytes()
        second = (directory/'disabled/native-prototype.sfc').read_bytes()
        if not first or first != second:
            raise RuntimeError(f'{name}: omitted and disabled options differ')
        rows.append({'fixture': name, 'byte_identical': True, 'bytes': len(first),
                     'sha256': hashlib.sha256(first).hexdigest()})
    report = {'passed': True, 'comparison': 'same-source omitted versus explicit False',
              'historical_binary_identity_claimed': False,
              'disabled_options': list(OPTIONS), 'results': rows}
    out.mkdir(parents=True, exist_ok=True)
    temporary = out/'identity.json.tmp'
    temporary.write_text(json.dumps(report, indent=2)+'\n')
    temporary.replace(out/'identity.json')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixtures', nargs='+', choices=tuple(FIXTURES),
                        default=list(FIXTURES))
    args = parser.parse_args()
    print(json.dumps(run(args.out.resolve(), tuple(args.fixtures)), indent=2))
