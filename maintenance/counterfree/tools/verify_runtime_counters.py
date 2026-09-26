#!/usr/bin/env python3
"""Verify optional access-count instrumentation without weakening CPU checks.

Each procedural input runs on an unmodified NES core and both SNES build modes.
The known instruction tests, dummy I/O reads, mapper returns, APU reloads and
raw OAM comparisons still run when access-count instrumentation is disabled.
No commercial ROM or claim of whole-game correctness is involved.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from build_native import build
from verify_native_cpu import verify
from native_fixture import create as cpu, Program, write_program
from libretro_runner import Runner
from fastpath_fixture import create as fast
from indexed_memory_fixture import create as indexed
from indexed_bus_fixture import create as bus
from direct_fixture import create as direct
from bank_switch_fixture import create as banks
from ppu_fixture import create as ppu
from indirect_load_fixture import create as indirect
from zero_page_store_fixture import create as sty
from apu_counter_fixture import create as lengths
from oam_copy_fixture import create as oam

ROOT = Path(__file__).resolve().parents[1]
AUDIO = dict(experimental_audio=True, audio_counters=True, audio_sweep=True)


def configurations():
    return [
        ('cpu', cpu, {}, {}),
        ('fast', fast, {'seed': 31}, {}),
        ('indexed', indexed, {'seed': 19}, AUDIO),
        ('indexed-c0', indexed, {'seed': 7, 'c0': True}, AUDIO),
        ('indexed-fallback', indexed, {'seed': 7}, dict(AUDIO, direct=False, quick_indexed=False)),
        ('dummy-reads', bus, {}, {}),
        ('direct', direct, {}, {}),
        ('banks', banks, {'seed': 11}, {}),
        ('bank-interrupts', banks, {'seed': 11, 'enable_nmi': True}, {'stress_bank_switch': True}),
        ('ppu', ppu, {'seed': 7}, {}),
        ('indirect', indirect, {'seed': 31}, {}),
        ('zero-page', sty, {'seed': 7, 'c0': True}, {'safe_addresses': False}),
        ('audio-lengths', lengths, {}, AUDIO),
        ('audio-c0', lengths, {'force_c0': True}, AUDIO),
        ('oam-ram', oam, {'page': 0x1a, 'seed': 11, 'writer': 'STY'}, {}),
        ('oam-rom', oam, {'page': 0xff, 'seed': 7, 'c0': True}, {}),
    ]


def fault_fixture(out: Path) -> dict:
    """Jump indirectly to valid original code deliberately absent from the trace."""
    p = Program()
    p.op('SEI'); p.op('CLD'); p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7e)
    p.op('STA', 'zp', 0x40)
    p.op('LDA', 'imm', 0xf8); p.op('STA', 'zp', 0x41)
    p.op('JMP', 'ind', 0x40)
    p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    raw = bytearray((out/'fixture.nes').read_bytes())
    raw[16+0x3f800:16+0x3f807] = bytes.fromhex('a95a857e4c04f8')
    (out/'fixture.nes').write_bytes(raw)
    meta['rom_sha256'] = hashlib.sha256(raw).hexdigest()
    meta['unclassified_target'] = 0xf800
    (out/'trace-summary.json').write_text(json.dumps(meta, indent=2)+'\n')
    return meta


def capture_fault(core: Path, rom: Path, out: Path) -> dict:
    runner = Runner(core, rom)
    try:
        for _ in range(60):
            runner.run(1)
            memory = runner.memory()
            if memory[0x90f]:
                result = dict(code=memory[0x90f], bank=memory[0x90e],
                              pc=int.from_bytes(memory[0x90c:0x90e], 'little'))
                if result['code'] != 1 or result['pc'] != 0xf800 or memory[0x7e] != 0:
                    raise AssertionError(f'Incorrect unclassified-code guard: {result}')
                out.write_text(json.dumps(result, indent=2)+'\n')
                return result
        raise AssertionError('Unclassified code did not trigger the safety stop')
    finally:
        runner.close()


def run(nes_core: Path, snes_core: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    oam_bytes = 0
    for name, creator, params, options in configurations():
        for enabled in (True, False):
            mode = 'counted' if enabled else 'uncounted'
            d = out / f'{name}-{mode}'
            creator(d, **params)
            build(d/'fixture.nes', d, d/'snes', runtime_counters=enabled, **options)
            report = verify(nes_core, snes_core, d, d/'verification')
            counts = report['native_execution_counters']
            if enabled and not any(counts.values()):
                raise AssertionError(f'{name}: test must actually exercise instrumented operations')
            if not enabled and any(counts.values()):
                raise AssertionError(f'{name}: disabled counters must remain zero')
            if creator is oam:
                oracle = d/'verification/nes-oam.bin'
                subprocess.run([sys.executable, str(ROOT/'tools/verify_memory_completion.py'),
                    '--capture-oam', '--nes-core', str(nes_core), '--rom', str(d/'fixture.nes'),
                    '--out', str(oracle)], check=True)
                actual = (d/'verification/snes.oam.bin').read_bytes()
                if len(actual) != 256 or oracle.read_bytes() != actual:
                    raise AssertionError(f'{name}: independent OAM data disagreement')
                oam_bytes += 256
            rows.append(dict(name=name, mode=mode, **report))
            (out/'progress.json').write_text(json.dumps(dict(
                status='running', completed_configurations=len(rows),
                expected_configurations=2*len(configurations()),
                last_completed=f'{name}-{mode}'), indent=2)+'\n')
            print(f'Completed {len(rows)}/{2*len(configurations())}: {name}-{mode}', flush=True)
    guards = []
    for enabled in (True, False):
        d = out / ('guard-counted' if enabled else 'guard-uncounted')
        fault_fixture(d)
        build(d/'fixture.nes', d, d/'snes', runtime_counters=enabled)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--capture-fault',
            '--snes-core', str(snes_core), '--rom', str(d/'snes/native-prototype.sfc'),
            '--out', str(d/'fault.json')], check=True)
        guards.append(dict(runtime_counters=enabled, **json.loads((d/'fault.json').read_text())))
    audio_results = []
    subprocess.run([sys.executable, str(ROOT/'tools/apu_sweep_fixture.py'),
                    '--out', str(out/'audio-input')], check=True)
    for name, options in [('direct', {}), ('generic', dict(direct=False, quick_io=False)),
                          ('nested-nmi', dict(stress_nmi_restore=True))]:
        d = out / ('audio-'+name)
        build(out/'audio-input/fixture.nes', out/'audio-input', d,
              runtime_counters=False, **AUDIO, **options)
        subprocess.run([sys.executable, str(ROOT/'tools/verify_apu_sweep.py'),
            '--core', str(snes_core), '--rom', str(d/'native-prototype.sfc'),
            '--fixture', str(out/'audio-input'), '--out', str(d/'verification')], check=True)
        audio_results.append(dict(name=name, **json.loads((d/'verification/sweep-verification.json').read_text())))
    result = dict(passed=True, fault_guards=guards, audio_regressions=audio_results, configurations=len(rows),
        records_checked=sum(r['records_checked'] for r in rows),
        bytes_checked=sum(r['bytes_checked'] for r in rows), oam_bytes_checked=oam_bytes,
        mismatches=sum(r['mismatch_count'] for r in rows),
        nes_core_sha256=hashlib.sha256(nes_core.read_bytes()).hexdigest(),
        snes_core_sha256=hashlib.sha256(snes_core.read_bytes()).hexdigest(), results=rows,
        scope='Counted and counter-free variants: explicit CPU/PPU/APU events, mapper returns, '
              'interrupt stress and zero-offset OAM contents; not cycle accuracy or full-game coverage.')
    (out/'runtime-counter-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    (out/'progress.json').write_text(json.dumps(dict(status='passed', completed_configurations=len(rows)), indent=2)+'\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nes-core', type=Path)
    p.add_argument('--snes-core', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--capture-fault', action='store_true')
    p.add_argument('--rom', type=Path)
    a = p.parse_args()
    if a.capture_fault:
        if not a.rom: p.error('--capture-fault requires --rom')
        capture_fault(a.snes_core.resolve(), a.rom.resolve(), a.out.resolve())
    else:
        if not a.nes_core: p.error('--nes-core is required for the matrix')
        report = run(a.nes_core.resolve(), a.snes_core.resolve(), a.out.resolve())
        print(json.dumps({k: v for k, v in report.items() if k != 'results'}, indent=2))
