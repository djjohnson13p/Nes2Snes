#!/usr/bin/env python3
"""Independently check zero-page stores, indirect reads and zero-offset OAM DMA.

NES OAM is extracted from the pinned unmodified core's tagged save state,
not from a model of this port. Each emulator capture runs in a fresh process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from build_native import build
from libretro_runner import Runner
from verify_native_cpu import verify
from zero_page_store_fixture import create as sty_fixture
from indirect_load_fixture import create as indirect_fixture
from oam_copy_fixture import create as oam_fixture, RAM_PAGES, ROM_PAGES


def fcs_oam(data: bytes) -> tuple[bytes, int]:
    if len(data) < 16 or data[:3] != b'FCS':
        raise ValueError('Expected an uncompressed tagged FCEUmm save state')
    fields = {}
    pos = 16
    while pos < len(data):
        if len(data) - pos < 5:
            raise ValueError('Truncated FCS section header')
        kind, size = data[pos], int.from_bytes(data[pos+1:pos+5], 'little')
        pos += 5
        end = pos + size
        if end > len(data):
            raise ValueError('Truncated FCS section')
        if kind == 3:
            while pos < end:
                if end - pos < 8:
                    raise ValueError('Truncated PPU state field')
                tag = data[pos:pos+4]
                count = int.from_bytes(data[pos+4:pos+8], 'little') & 0x7fffffff
                pos += 8
                if count > end - pos:
                    raise ValueError('Truncated PPU state payload')
                if tag in (b'SPRA', b'PGEN'):
                    if tag in fields:
                        raise ValueError('Duplicate PPU field')
                    fields[tag] = data[pos:pos+count]
                pos += count
        pos = end
    if len(fields.get(b'SPRA', b'')) != 256 or len(fields.get(b'PGEN', b'')) != 1:
        raise ValueError('Independent NES core did not expose expected OAM/latch state')
    return fields[b'SPRA'], fields[b'PGEN'][0]


def capture_oam(core: Path, rom: Path, out: Path) -> None:
    r = Runner(core, rom)
    try:
        for _ in range(300):
            r.run(1)
            if r.memory()[0x7e] == 0x5a:
                oam, latch = fcs_oam(r.state())
                out.write_bytes(oam)
                out.with_suffix('.json').write_text(json.dumps({'ppu_io_latch': latch}) + '\n')
                return
        raise RuntimeError('OAM oracle did not reach the completion marker')
    finally:
        r.close()


def run(nes_core: Path, snes_core: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, seed, c0, enabled in [
            *[(f'sty-seed-{n}', n, False, True) for n in range(4)],
            ('sty-c0', 7, True, True), ('sty-generic', 7, True, False)]:
        d = out / name
        meta = sty_fixture(d, seed, c0)
        build(d/'fixture.nes', d, d/'snes', quick_zp=enabled, safe_addresses=False)
        result = verify(nes_core, snes_core, d, d/'verification')
        expected = meta['store_cases'] if enabled else 0
        if result['native_execution_counters']['quick_zp_calls'] != expected:
            raise RuntimeError(f'{name}: wrong number of accelerated STY operations')
        rows.append(dict(name=name, **result))
    for name, seed, specialized in [
            ('indirect-0', 0, True), ('indirect-7', 7, True),
            ('indirect-shared', 7, False), ('indirect-generic', 7, False)]:
        d = out / name
        indirect_fixture(d, seed)
        build(d/'fixture.nes', d, d/'snes', specialized_indirect=specialized,
              quick_indirect=name != 'indirect-generic')
        result = verify(nes_core, snes_core, d, d/'verification')
        count = result['native_execution_counters']['quick_indirect_calls']
        if bool(count) != (name != 'indirect-generic'):
            raise RuntimeError(f'{name}: indirect path not exercised as expected')
        rows.append(dict(name=name, **result))
    configs = [(f'oam-{page:02x}', page, False, 'STA', True, True, True)
               for page in RAM_PAGES + ROM_PAGES]
    configs += [('oam-c0-ram', 2, True, 'STA', True, True, True),
                ('oam-c0-rom', 0xff, True, 'STA', True, True, True),
                ('oam-stx', 2, False, 'STX', True, True, True),
                ('oam-sty', 2, False, 'STY', True, True, True),
                ('oam-blockmove', 2, False, 'STA', False, True, True),
                ('oam-no-direct', 0x1a, False, 'STA', True, False, True),
                ('oam-generic', 2, False, 'STA', True, False, False)]
    for name, page, c0, writer, words, direct, quick_io in configs:
        d = out / name
        oam_fixture(d, page, 7, c0, writer)
        build(d/'fixture.nes', d, d/'snes', word_oam=words, direct=direct, quick_io=quick_io)
        result = verify(nes_core, snes_core, d, d/'verification')
        oracle = d/'verification/nes-ppu-oam.bin'
        subprocess.run([sys.executable, __file__, '--capture-oam', '--nes-core', str(nes_core),
                        '--rom', str(d/'fixture.nes'), '--out', str(oracle)], check=True)
        expected = oracle.read_bytes()
        actual = (d/'verification/snes.oam.bin').read_bytes()
        if len(actual) != 256 or actual != expected:
            raise RuntimeError(f'{name}: independent OAM content mismatch')
        result['oam_oracle'] = dict(bytes_checked=256, mismatch_count=0,
                                   sha256=hashlib.sha256(expected).hexdigest())
        (d/'verification/oam-verification.json').write_text(json.dumps(result, indent=2) + '\n')
        rows.append(dict(name=name, **result))
    report = dict(passed=True, configurations=len(rows),
                  records_checked=sum(r['records_checked'] for r in rows),
                  register_flag_bytes=sum(r['bytes_checked'] for r in rows),
                  oam_bytes_checked=256 * len(configs),
                  mismatches=0,
                  nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
                  snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(),
                  results=rows,
                  scope='Explicit indexed-zero-page, indirect-read and zero-offset OAM/latch cases. '
                        'No active-rendering, OAMADDR rotation, stack-page DMA, cycle accuracy or full-game claim.')
    (out/'memory-completion.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nes-core', type=Path, required=True)
    p.add_argument('--snes-core', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--rom', type=Path)
    p.add_argument('--capture-oam', action='store_true')
    a = p.parse_args()
    if a.capture_oam:
        if a.rom is None: p.error('--capture-oam requires --rom')
        capture_oam(a.nes_core.resolve(), a.rom.resolve(), a.out.resolve())
    else:
        if a.snes_core is None: p.error('--snes-core is required')
        report = run(a.nes_core.resolve(), a.snes_core.resolve(), a.out.resolve())
        print(json.dumps({k: v for k, v in report.items() if k != 'results'}, indent=2))
