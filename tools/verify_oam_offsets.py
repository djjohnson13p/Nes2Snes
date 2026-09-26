#!/usr/bin/env python3
"""Check sprite-DMA destination wrapping against an unmodified NES emulator.

Every offset is tested with forced blanking and initialized ordinary RAM. Extra
cases check mirrored RAM/ROM, alternate interception paths, subsequent OAM
writes, and source mutations. Each emulator session runs in its own process.
This is not active-rendering, stack-page, I/O-source or cycle-accuracy validation.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_native import build
from oam_copy_fixture import create
from verify_native_cpu import verify
from libretro_runner import Runner
from oam_state import nestopia_oam, meaningful_oam


def compare_oam(expected: bytes, actual: bytes) -> dict:
    """Require full buffers: truncated comparisons must never silently pass."""
    if len(expected) != 256 or len(actual) != 256:
        raise ValueError('Both independent OAM buffers must contain 256 bytes')
    raw_changed = sum(a != b for a, b in zip(expected, actual))
    expected_bits, actual_bits = meaningful_oam(expected), meaningful_oam(actual)
    changed = [i for i, (a, b) in enumerate(zip(expected_bits, actual_bits)) if a != b]
    return dict(bytes_checked=256, meaningful_bits_checked=1856, mismatch_count=len(changed),
                raw_mismatch_count=raw_changed,
                ignored_bits="Only absent OAM attribute bits 2/3/4",
                first_mismatch=changed[0] if changed else None,
                nes_sha256=hashlib.sha256(expected).hexdigest(),
                snes_sha256=hashlib.sha256(actual).hexdigest())


def case(nes: Path, snes: Path, folder: Path, offset: int, *, page: int = 2,
         seed: int = 7, c0: bool = False, writer: str = 'STA',
         post_write: int | None = None, mutate_source: bool = False,
         options: dict | None = None, previous_root: Path | None = None) -> dict:
    create(folder, page, seed, c0, writer, offset, post_write, mutate_source, neutral_latch=True)
    if previous_root is None:
        build(folder/'fixture.nes', folder, folder/'snes', **(options or {}))
    else:
        if options:
            raise ValueError('Negative-control build requires baseline defaults')
        subprocess.run([sys.executable, str(previous_root/'tools/build_native.py'),
                        '--rom', str(folder/'fixture.nes'), '--trace', str(folder),
                        '--out', str(folder/'snes')], check=True)
    cpu = verify(nes, snes, folder, folder/'verification')
    # Read the actual NES PPU's serialized OAM, not a Python rotation model
    # and not a potentially incomplete emulator OAMDATA readback implementation.
    oracle = folder/'verification/nes-ppu-oam.bin'
    subprocess.run([sys.executable, str(Path(__file__)),
                    '--capture-nestopia', '--nes-core', str(nes), '--rom', str(folder/'fixture.nes'),
                    '--out', str(oracle)], check=True)
    ppu = json.loads(oracle.with_suffix('.json').read_text())
    expected_address = (offset + (post_write is not None)) & 255
    native_ppu = json.loads((folder/'verification/snes.ppu.json').read_text())
    if native_ppu['oam_address'] != expected_address:
        raise RuntimeError('Native OAMADDR did not preserve/wrap as expected')
    if ppu['oam_address'] != expected_address:
        raise RuntimeError('Independent oracle did not preserve/wrap OAMADDR as expected')
    comparison = compare_oam(oracle.read_bytes(),
                            (folder/'verification/snes.oam.bin').read_bytes())
    result = dict(offset=offset, page=page, seed=seed, c0=c0, writer=writer,
                  post_write=post_write, mutate_source=mutate_source,
                  options=options or {}, cpu=cpu, oam=comparison, oracle_ppu=ppu)
    (folder/'verification/oam-offset.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def capture_stream(core: Path, rom: Path, out: Path, kind: str) -> None:
    """Observe each of 256 independent destination offsets with a test handshake."""
    r = Runner(core, rom)
    rows = []
    try:
        memory = C.cast(r.lib.retro_get_memory_data(2), C.POINTER(C.c_uint8))
        if not memory: raise RuntimeError('Fixture RAM unavailable')
        for offset in range(256):
            for _ in range(300):
                r.run(1)
                m = r.memory()
                if m[0x7e] == 0x5a and m[0x7d] == 1:
                    if m[0x7c] != offset: raise RuntimeError('Lost fixture handshake')
                    break
            else: raise RuntimeError(f'Stream did not reach offset {offset}')
            if kind == 'nestopia':
                oam, address, latch = nestopia_oam(r.state())
            elif kind == 'fceumm':
                from verify_memory_completion import fcs_oam
                oam, latch = fcs_oam(r.state())
                address = None  # This legacy core resets OAMADDR even in blanking.
            else:
                oam, address, latch = m[0x3800:0x3900], m[0x913], m[0x91b]
                if m[0x90f]: raise RuntimeError('Native fixture trapped')
            rows.append(dict(offset=offset, oam=oam.hex(), oam_address=address,
                             latch=latch, records=m[0x300:0x30c].hex()))
            memory[0x7d] = 0
        for _ in range(300):
            r.run(1)
            if r.memory()[0x7e] == 0xa5: break
        else: raise RuntimeError('Stream completion acknowledgement failed')
        out.write_text(json.dumps(rows, indent=2)+'\n')
    finally:
        r.close()


def validate_stream(rows: list) -> None:
    """Reject missing, reordered, duplicated and overlong observation streams."""
    if not isinstance(rows, list) or len(rows) != 256:
        raise ValueError('An offset stream must contain exactly 256 observations')
    for i, row in enumerate(rows):
        if row.get('offset') != i or type(row.get('offset')) is not int:
            raise ValueError('Unexpected offset ordering in captured state')
        if len(bytes.fromhex(row['oam'])) != 256 or len(bytes.fromhex(row['records'])) != 12:
            raise ValueError('Truncated OAM or register observation')


def diagnose_latch(nes: Path, snes: Path, fceumm: Path, out: Path) -> dict:
    """Retain the unrestricted final-byte disagreement, outside acceptance totals.

    Nestopia masks absent attribute bits in its generic DMA latch; the pinned
    FCEUmm implementation and this bridge leave the source byte in the latch.
    This test must expose that discrepancy, not redefine a mismatch as a pass.
    """
    out.mkdir(parents=True, exist_ok=True)
    create(out, seed=7, oam_address=127, neutral_latch=False)
    build(out/'fixture.nes', out, out/'snes')
    subprocess.run([sys.executable, str(Path(__file__)), '--capture-nestopia',
                    '--nes-core', str(nes), '--rom', str(out/'fixture.nes'),
                    '--out', str(out/'nestopia.bin')], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify_memory_completion.py')),
                    '--capture-oam', '--nes-core', str(fceumm),
                    '--rom', str(out/'fixture.nes'), '--out', str(out/'fceumm.bin')], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify_native_cpu.py')),
                    '--capture', '--core', str(snes), '--rom', str(out/'snes/native-prototype.sfc'),
                    '--output', str(out/'snes.ram')], check=True)
    np = json.loads((out/'nestopia.json').read_text())
    fp = json.loads((out/'fceumm.json').read_text())
    sp = json.loads((out/'snes.ppu.json').read_text())
    report = dict(status='unresolved_reference_disagreement', included_in_pass_totals=False,
                  fixture=dict(offset=127, seed=7, neutral_latch=False),
                  latch_values=dict(nestopia=np['ppu_io_latch'], fceumm=fp['ppu_io_latch'],
                                    snes=sp['ppu_io_latch']),
                  nes_references_agree=np['ppu_io_latch'] == fp['ppu_io_latch'],
                  nestopia_vs_snes_oam=compare_oam((out/'nestopia.bin').read_bytes(),
                                                   (out/'snes.oam.bin').read_bytes()),
                  nestopia_vs_fceumm_oam=compare_oam((out/'nestopia.bin').read_bytes(),
                                                     (out/'fceumm.bin').read_bytes()),
                  limitation='No claim of unrestricted nonzero-offset DMA latch equivalence. '
                  'The acceptance fixture clears disputed bits only in its final RAM-source byte; '
                  'all destination offsets and other source bytes remain independently checked.')
    (out/'reference-disagreement.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def stream_matrix(nes: Path, snes: Path, out: Path, fceumm: Path | None, runtime_counters: bool = True) -> tuple[list, dict | None]:
    out.mkdir(parents=True, exist_ok=True)
    create(out, neutral_latch=True, stream_offsets=True)
    build(out/'fixture.nes', out, out/'snes', runtime_counters=runtime_counters)
    configs = [('nestopia', nes, out/'fixture.nes'),
               ('snes', snes, out/'snes/native-prototype.sfc')]
    if fceumm: configs.append(('fceumm', fceumm, out/'fixture.nes'))
    captures = {}
    for name, core, rom in configs:
        path = out/(name+'-offsets.json')
        subprocess.run([sys.executable, str(Path(__file__)), '--capture-stream',
                        '--kind', name, '--nes-core', str(core), '--rom', str(rom),
                        '--out', str(path)], check=True)
        captures[name] = json.loads(path.read_text())
        validate_stream(captures[name])
    rows = []
    divergences = []
    for n, s in zip(captures['nestopia'], captures['snes']):
        offset = n['offset']
        cmp = compare_oam(bytes.fromhex(n['oam']), bytes.fromhex(s['oam']))
        if cmp['mismatch_count'] or n['records'] != s['records'] or n['oam_address'] != offset or s['oam_address'] != offset:
            raise RuntimeError(f'Independent streamed OAM/register mismatch at {offset}')
        rows.append(dict(name=f'offset-{offset:02x}', offset=offset, oam=cmp,
                         cpu=dict(records_checked=3, bytes_checked=12, mismatch_count=0),
                         stream=True, runtime_counters=runtime_counters))
        if fceumm:
            f = captures['fceumm'][offset]
            disagreement = compare_oam(bytes.fromhex(n['oam']), bytes.fromhex(f['oam']))
            if disagreement['mismatch_count'] or f['records'] != n['records']:
                divergences.append(dict(offset=offset, oam=disagreement,
                                        cpu_records_agree=(f['records'] == n['records'])))
    if len(rows) != 256: raise RuntimeError('Incomplete offset stream')
    reference_report = None if not fceumm else dict(
        core_sha256=hashlib.sha256(fceumm.read_bytes()).hexdigest(),
        disagreement_count=len(divergences), disagreements=divergences,
        acceptance_oracle=False,
        explanation='Retained legacy FCEUmm disagreement; it redirects certain nonzero-offset OAM writes. '
                    'Primary acceptance uses Nestopia plus documented OAM destination wrapping, not this behavior.')
    return rows, reference_report


def run(nes: Path, snes: Path, out: Path, offsets: list[int] | None = None,
        previous_root: Path | None = None, fceumm: Path | None = None) -> dict:
    use_stream = offsets is None
    offsets = list(range(256)) if offsets is None else offsets
    if not offsets or any(type(i) is not int or not 0 <= i <= 255 for i in offsets):
        raise ValueError('Offsets must be bytes')
    if len(set(offsets)) != len(offsets):
        raise ValueError('Offsets must be unique')
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    def check(name: str, offset: int, **kwargs) -> None:
        r = case(nes, snes, out/name, offset, **kwargs)
        rows.append(dict(name=name, **r))
        # Write partial evidence as we go, so an interrupted test is resumable
        # without confusing its completed prefix with a passing full matrix.
        (out/'partial-results.json').write_text(json.dumps(rows, indent=2)+'\n')
        if r['oam']['mismatch_count']:
            raise RuntimeError(f'{name}: independent OAM mismatch: {r["oam"]}')
        print(f'OAM_CHECK_OK {name}', flush=True)
    references = None
    if use_stream:
        rows, references = stream_matrix(nes, snes, out/'stream', fceumm)
        print('OAM_CHECK_OK all-256-counted-offsets', flush=True)
        fast_rows, _ = stream_matrix(nes, snes, out/'stream-counter-free', None, False)
        for row in fast_rows: row['name'] = 'counter-free-' + row['name']
        rows.extend(fast_rows)
        print('OAM_CHECK_OK all-256-counter-free-offsets', flush=True)
    else:
        for offset in offsets:
            check(f'offset-{offset:02x}', offset)
    extras = [
        ('mirrored-ram', 0xff, dict(page=0x1a, mutate_source=True)),
        ('rom-80', 7, dict(page=0x80)),
        ('rom-c0', 0xfc, dict(page=0xc0)),
        ('rom-ff', 0xfd, dict(page=0xff)),
        ('c0-ram', 3, dict(c0=True)),
        ('c0-rom', 0xfe, dict(page=0xff, c0=True)),
        ('stx', 0x80, dict(writer='STX')),
        ('sty', 0xff, dict(writer='STY')),
        ('legacy-copy', 0x81, dict(options={'word_oam': False})),
        ('no-direct', 0x7f, dict(options={'direct': False})),
        ('generic', 0xff, dict(options={'direct': False, 'quick_io': False})),
    ]
    for n in (0, 1, 2, 3, 0x7f, 0x80, 0xfe, 0xff):
        extras.append((f'post-write-{n:02x}', n,
                       dict(post_write=(n ^ 0xad), mutate_source=True)))
    for name, offset, kw in extras:
        check(name, offset, **kw)
    negative = None
    if previous_root is not None:
        negative = case(nes, snes, out/'previous-offset-1', 1,
                        previous_root=previous_root)
        if negative['oam']['mismatch_count'] < 240 or negative['cpu']['mismatch_count'] != 0:
            raise RuntimeError('Baseline did not reproduce the expected offset-only error')
    latch_disagreement = diagnose_latch(nes, snes, fceumm, out/'unrestricted-latch') if fceumm else None
    report = dict(passed=True, unrestricted_latch_disagreement=latch_disagreement, primary_oracle='Unmodified Nestopia 8f00f500912a847062de432e38765c7285483e62', baseline_revision='a19a87c328e47e3603e3f049b605a85693e230c9',
                  offsets_checked=offsets, exhaustive_offsets=(sorted(offsets) == list(range(256))),
                  configurations=len(rows), counter_free_offsets_checked=256 if use_stream else 0, reference_disagreements=references,
                  oam_bytes_checked=sum(r['oam']['bytes_checked'] for r in rows),
                  records_checked=sum(r['cpu']['records_checked'] for r in rows),
                  record_bytes_checked=sum(r['cpu']['bytes_checked'] for r in rows),
                  mismatch_count=0, previous_runtime_negative_control=negative,
                  nes_core_sha256=hashlib.sha256(nes.read_bytes()).hexdigest(),
                  snes_core_sha256=hashlib.sha256(snes.read_bytes()).hexdigest(),
                  scope='Forced-blanking OAM destination wrapping, compared with absent attribute bits masked. '
                        'RAM source final bytes neutralize disputed DMA-latch bits; eager copies from selected RAM/ROM; '
                        'no active-rendering, stack-page, I/O-source, cycle-accurate or whole-game claim.',
                  results=rows)
    (out/'oam-offset-matrix.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def capture_nestopia(core: Path, rom: Path, out: Path) -> None:
    r = Runner(core, rom)
    try:
        for _ in range(300):
            r.run(1)
            if r.memory()[0x7e] == 0x5a:
                oam, address, latch = nestopia_oam(r.state())
                out.write_bytes(oam)
                out.with_suffix('.json').write_text(json.dumps(dict(
                    oam_address=address, ppu_io_latch=latch))+'\n')
                return
        raise RuntimeError('Nestopia fixture did not reach completion')
    finally:
        r.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nes-core', type=Path, required=True)
    p.add_argument('--snes-core', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--capture-nestopia', action='store_true')
    p.add_argument('--rom', type=Path)
    p.add_argument('--fceumm-core', type=Path, help='Retain secondary reference disagreements')
    p.add_argument('--capture-stream', action='store_true')
    p.add_argument('--kind', choices=('nestopia', 'snes', 'fceumm'))
    p.add_argument('--offsets', help='Optional comma-separated subset; default tests all 256 offsets')
    p.add_argument('--previous-root', type=Path, help='Optional preceding source for a negative control')
    a = p.parse_args()
    if a.capture_stream:
        if not a.rom or not a.kind: p.error('Stream capture needs --rom and --kind')
        capture_stream(a.nes_core, a.rom, a.out, a.kind)
        raise SystemExit(0)
    if a.capture_nestopia:
        if not a.rom: p.error('--capture-nestopia requires --rom')
        capture_nestopia(a.nes_core, a.rom, a.out)
        raise SystemExit(0)
    if not a.snes_core: p.error('--snes-core is required')
    offsets = [int(i, 0) for i in a.offsets.split(',')] if a.offsets else None
    r = run(a.nes_core.resolve(), a.snes_core.resolve(), a.out.resolve(), offsets,
            a.previous_root.resolve() if a.previous_root else None,
            a.fceumm_core.resolve() if a.fceumm_core else None)
    print(json.dumps({k: v for k, v in r.items() if k not in ('results', 'previous_runtime_negative_control')}, indent=2))
