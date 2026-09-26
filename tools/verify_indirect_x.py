#!/usr/bin/env python3
"""Independent, procedural indirect-X matrix; deliberately no gameplay claims."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_native import build
from indirect_x_fixture import create
from native_fixture import create as native_fixture
from verify_native_cpu import verify

ROOT = Path(__file__).resolve().parents[1]

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)

def run(nes_core: Path, snes_core: Path, out: Path, previous_root: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows, coverage = [], []
    configs = []
    for indexes in (False, True):
        for block in range(16):
            configs.append((f'{"indexes" if indexes else "pointers"}-{block:02d}',
                            dict(block=block, seed=7, sweep_indexes=indexes),
                            dict(quick_indirect_x=True)))
    configs += [
        ('counter-free', dict(block=15, seed=255), dict(quick_indirect_x=True, runtime_counters=False)),
        ('default-fallback', dict(block=15, seed=255), {}),
        ('master-disabled', dict(block=15, seed=255), dict(quick_indirect_x=True, quick_indirect=False)),
        ('no-direct', dict(block=15, seed=1), dict(quick_indirect_x=True, direct=False)),
        ('only-indirect-fast', dict(block=0, seed=1), dict(quick_indirect_x=True, direct=False,
             quick_zp=False, quick_indexed=False, quick_io=False, safe_addresses=False)),
        ('slow-rom', dict(block=15, seed=0), dict(quick_indirect_x=True, fastrom=False)),
        ('guest-nmi', dict(block=15, seed=7, in_nmi=True), dict(quick_indirect_x=True)),
        ('nested-nmi', dict(block=15, seed=7, in_nmi=True), dict(quick_indirect_x=True,
             stress_nmi_restore=True, runtime_counters=False)),
    ]
    for name, fixture_options, build_options in configs:
        print(f'Checking {name}', flush=True)
        directory = out/name
        meta = create(directory, **fixture_options)
        built = build(directory/'fixture.nes', directory, directory/'snes', **build_options)
        result = verify(nes_core, snes_core, directory, directory/'verification')
        enabled = bool(build_options.get('quick_indirect_x', False) and
                       build_options.get('quick_indirect', True))
        counted = build_options.get('runtime_counters', True)
        expected = meta['expected_fast_reads'] if enabled and counted else 0
        measured = result['native_execution_counters']['quick_indirect_calls']
        if measured != expected:
            raise RuntimeError(f'{name}: expected {expected} native reads, measured {measured}')
        if built['quick_indirect_x'] != enabled:
            raise RuntimeError(f'{name}: wrong build gate')
        result['scope'] = 'Authored indexed-indirect reads, flags, wrapping, raw mappings and I/O fallback; not CPU cycle accuracy or gameplay validation.'
        row = dict(name=name, option_enabled=enabled, fixture_options=fixture_options,
                   build_options=build_options, expected_fast_reads=expected,
                   rom_sha256=built['rom_sha256'], output_sha256=digest(directory/'snes/native-prototype.sfc'),
                   **result)
        write_json(directory/'verification/indirect-x-case.json', row)
        rows.append(row)
        coverage.extend(meta['coverage'])
        write_json(out/'progress.json', dict(complete=False, configurations_completed=len(rows),
                                           results=rows))
    pointers = {r['pointer'] for r in coverage}
    indexes = {r['index'] for r in coverage}
    banks = {(r['primary_bank'], r['c_bank']) for r in coverage}
    if pointers != set(range(256)) or indexes != set(range(256)):
        raise RuntimeError('Incomplete independent pointer/index coverage')
    if banks != {(p,c) for p in range(16) for c in (7,30)}:
        raise RuntimeError('Incomplete supported bank coverage')
    # An unchanged default must really produce the previous ROM, not merely
    # appear to behave similarly. Both builders receive the same input bytes.
    identity = []
    for name, creator in [('general', native_fixture), ('indirect-x', create)]:
        directory = out/('identity-'+name)
        creator(directory)
        build(directory/'fixture.nes', directory, directory/'current')
        with (directory/'previous-build.log').open('w') as log:
            subprocess.run([sys.executable, str(previous_root/'tools/build_native.py'),
                            '--rom', str(directory/'fixture.nes'), '--trace', str(directory),
                            '--out', str(directory/'previous')], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=120)
        new = digest(directory/'current/native-prototype.sfc')
        old = digest(directory/'previous/native-prototype.sfc')
        if new != old:
            raise RuntimeError(f'{name}: default ROM changed')
        identity.append(dict(fixture=name, sha256=new, matches_baseline=True))
    report = dict(passed=True, complete=True,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        configurations=len(rows), records_checked=sum(r['records_checked'] for r in rows),
        register_flag_bytes=sum(r['bytes_checked'] for r in rows), mismatches=0,
        pointer_offsets_checked=len(pointers), x_values_checked=len(indexes),
        supported_bank_pairs_checked=len(banks),
        coverage_qualification='Every pointer offset and every X value occurs; this is not every Cartesian combination of all operands, flags, banks and addresses.',
        nes_core_sha256=digest(nes_core), snes_core_sha256=digest(snes_core),
        default_binary_identity=identity, option_enabled_by_default=False,
        full_game_validation=False, gameplay_performance_measured=False,
        scope='New optional (zero-page,X) read handlers compared with the pinned unmodified FCEUmm core. No commercial ROM, whole-game, hardware-console or cycle-exact claim.',
        results=rows)
    write_json(out/'indirect-x-verification.json', report)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nes-core', type=Path, required=True)
    parser.add_argument('--snes-core', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--previous-root', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.nes_core.resolve(), args.snes_core.resolve(), args.out.resolve(), args.previous_root.resolve())
    print(json.dumps({k:v for k,v in report.items() if k != 'results'}, indent=2))
