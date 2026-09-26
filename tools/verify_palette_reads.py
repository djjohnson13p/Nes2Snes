#!/usr/bin/env python3
"""Independent, unmasked palette-read checks with a failing baseline control.

Nestopia is the acceptance oracle. A second, unmodified FCEUmm capture is
retained verbatim as a diagnostic, not folded into successful test totals.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_native import build
from palette_read_fixture import create

ROOT = Path(__file__).resolve().parents[1]


def compare(records: list, expected: bytes, actual: bytes) -> dict:
    if len(expected) != 0x800 or len(actual) != 0x800:
        raise ValueError('Require complete 2-KiB CPU RAM captures')
    if not isinstance(records, list) or not records:
        raise ValueError('Require a nonempty ordered record list')
    names = set()
    mismatches = []
    for i, row in enumerate(records):
        if not isinstance(row, dict): raise ValueError('Invalid record')
        name, address = row.get('name'), row.get('address')
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('Record names must be nonempty and unique')
        if type(address) is not int or address != 0x300 + 4*i or address + 4 > 0x780:
            raise ValueError('Records must cover contiguous four-byte observations')
        names.add(name)
        n, s = expected[address:address+4], actual[address:address+4]
        if n != s: mismatches.append(dict(test=name, expected=n.hex(), actual=s.hex()))
    return dict(records_checked=len(records), bytes_checked=4*len(records),
                mismatch_count=len(mismatches), mismatches=mismatches,
                comparison='Full A/X/Y and selected C/Z/V/N flags; no palette-result masking')


def capture(core: Path, rom: Path, output: Path) -> bytes:
    subprocess.run([sys.executable, str(ROOT/'tools/verify_native_cpu.py'),
                    '--capture', '--core', str(core), '--rom', str(rom),
                    '--output', str(output), '--limit', '600'], check=True)
    return output.read_bytes()


def run(nes: Path, snes: Path, out: Path, previous_root: Path,
        fceumm: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    configs = [(f'ciram-{bank}-seed-{seed}', seed, bank, {})
               for bank in (0, 1, 3) for seed in range(4)]
    configs += [
        ('counter-free', 3, 1, dict(runtime_counters=False)),
        ('generic', 2, 0, dict(direct=False, quick_io=False, quick_ppu=False,
                             quick_indexed=False, quick_indirect=False,
                             quick_zp=False, safe_addresses=False)),
        ('full-write-context', 1, 3, dict(simple_direct=False)),
        ('nested-host-interrupts', 0, 1, dict(stress_nmi_restore=True)),
    ]
    rows = []
    reference_diagnostic = None
    negative_control = None
    for name, seed, bank, options in configs:
        folder = out/name
        meta = create(folder, seed, bank)
        build(folder/'fixture.nes', folder, folder/'snes', **options)
        n = capture(nes, folder/'fixture.nes', folder/'nes.ram')
        s = capture(snes, folder/'snes/native-prototype.sfc', folder/'snes.ram')
        result = compare(meta['records'], n, s)
        result.update(name=name, seed=seed, bank=bank, options=options,
                      fixture_sha256=meta['rom_sha256'])
        counters = json.loads((folder/'snes.diagnostics.json').read_text())
        if options.get('runtime_counters', True):
            if not any(counters.values()): raise AssertionError('Interception paths not exercised')
        elif any(counters.values()):
            raise AssertionError('Disabled access counters unexpectedly changed')
        (folder/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        if result['mismatch_count']: raise AssertionError(f'{name}: independent NES mismatch')
        rows.append(result)
        (out/'progress.json').write_text(json.dumps(dict(status='running',
            completed_configurations=len(rows), planned_configurations=len(configs)))+'\n')
        if negative_control is None:
            baseline = folder/'baseline'
            subprocess.run([sys.executable, str(previous_root/'tools/build_native.py'),
                            '--rom', str(folder/'fixture.nes'), '--trace', str(folder),
                            '--out', str(baseline)], check=True, stdout=subprocess.DEVNULL)
            old = capture(snes, baseline/'native-prototype.sfc', folder/'baseline.ram')
            negative_control = compare(meta['records'], n, old)
            (out/'negative-control.json').write_text(json.dumps(negative_control, indent=2)+'\n')
            if not negative_control['mismatch_count']:
                raise AssertionError('Baseline must fail the same independent fixture')
            if fceumm:
                f = capture(fceumm, folder/'fixture.nes', folder/'fceumm.ram')
                reference_diagnostic = compare(meta['records'], n, f)
                reference_diagnostic.update(acceptance_oracle=False,
                    included_in_pass_totals=False,
                    explanation='Pinned FCEUmm does not match Nestopia palette I/O-latch semantics. '
                    'Full mismatches retained; no output masks or tolerances were added.')
                (out/'reference-disagreement.json').write_text(
                    json.dumps(reference_diagnostic, indent=2)+'\n')
        print(f'PALETTE_OK {name}: {result["records_checked"]} records', flush=True)
    report = dict(status='passed', configurations=len(rows),
                  records_checked=sum(r['records_checked'] for r in rows),
                  bytes_checked=sum(r['bytes_checked'] for r in rows),
                  mismatch_count=0, results=rows, negative_control=negative_control,
                  reference_diagnostic=reference_diagnostic,
                  core_sha256={name: hashlib.sha256(core.read_bytes()).hexdigest()
                      for name, core in [('nestopia', nes), ('snes9x', snes)] +
                      ([('fceumm', fceumm)] if fceumm else [])},
                  scope='Forced-blank PPUDATA palette values, aliases, grayscale, upper bus bits, '
                  'I/O latch, shadow-buffer refill, address increments/wrap, CIRAM and MMC5 fill. '
                  'Not rendering-time fetch behavior, latch decay, DMC interference, or full-game accuracy.')
    (out/'palette-read-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    (out/'progress.json').write_text(json.dumps(dict(status='passed',
        completed_configurations=len(rows), planned_configurations=len(configs)))+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('nes-core', 'snes-core', 'out', 'previous-root'):
        parser.add_argument('--'+arg, type=Path, required=True)
    parser.add_argument('--fceumm-core', type=Path)
    args = parser.parse_args()
    report = run(args.nes_core, args.snes_core, args.out, args.previous_root, args.fceumm_core)
    print(json.dumps({k: report[k] for k in ('status', 'configurations', 'records_checked', 'bytes_checked')}, indent=2))
