"""Strict clock selection, durable progress and scoped route-state comparison.

These helpers do not patch ROMs, write guest memory, or certify full-game fidelity.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
from opcodes6502 import OPS

# Candidate fields documented by the route harness, not the entire game state.
FIELDS = {'game_state': (0x18, 1), 'area_bytes': (0x32, 4),
          'camera_x': (0x56, 2), 'player_x': (0x438, 1),
          'player_y': (0x41C, 1)}


def guarded_update_pc(prg: bytes, nmi: int) -> int:
    """Recognize a first, forward LDY zp / BNE skip / INC same-zp guard.

    The returned instruction is entered only on the guard-clear path. This is
    not a general proof that arbitrary NMI handlers have one gameplay update.
    Reject calls, early exits, and other control flow before the guard.
    """
    if len(prg) < 0x2000 or type(nmi) is not int or not 0xE000 <= nmi <= 0xFFF9:
        raise ValueError('Guard recognition requires a fixed-bank NMI')
    base = len(prg) - 0x2000
    pc = nmi
    previous = None
    for _ in range(32):
        off = base + pc - 0xE000
        if pc > 0xFFF9 or off >= len(prg):
            break
        spec = OPS.get(prg[off])
        if spec is None:
            break
        name, mode, size = spec
        if off + size > len(prg):
            break
        if mode == 'rel':
            target = pc + 2 + int.from_bytes(prg[off+1:off+2], 'little', signed=True)
            following = prg[off+2:off+4]
            if (name == 'BNE' and previous is not None
                    and previous[0:2] == ('LDY', 'zp')
                    and len(following) == 2 and following[0] == 0xE6
                    and following[1] == previous[2]
                    and pc + 4 <= target <= 0xFFF9):
                return pc + 2
            break
        if name in ('JMP', 'JSR', 'RTI', 'RTS', 'BRK', 'SED'):
            break
        previous = (name, mode, prg[off+1] if size > 1 else None)
        pc += size
    raise ValueError('No unambiguous first guarded update entry was found')


def selected_state(memory: bytes) -> dict[str, int]:
    if len(memory) < max(address + size for address, size in FIELDS.values()):
        raise ValueError('Insufficient RAM for the selected route fields')
    return {name: int.from_bytes(memory[address:address+size], 'little')
            for name, (address, size) in FIELDS.items()}


def atomic_json(path: Path, value: dict) -> None:
    """Publish one complete JSON snapshot; never replace it with partial JSON."""
    data = json.dumps(value, indent=2, allow_nan=False) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.'+path.name+'.', delete=False) as f:
            temporary = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_route(folder: Path) -> tuple[dict, list[dict]]:
    # Lazy import avoids a dependency cycle with the recording harness.
    from gameplay_route import validate_actions
    path = folder / 'route-report.json'
    report = json.loads(path.read_text())
    if report.get('platform') not in ('nes', 'snes'):
        raise ValueError('Unknown route platform')
    if report.get('status') not in ('completed_budget', 'failed'):
        raise ValueError('Require a finalized route, not an in-progress snapshot')
    if report.get('clock_mode', 'legacy') not in ('legacy', 'guarded'):
        raise ValueError('Unknown route clock policy')
    steps = report.get('steps_requested')
    if type(steps) is not int or not 1 <= steps <= 1000:
        raise ValueError('Invalid route step budget')
    pattern = report.get('pattern')
    if not isinstance(pattern, list) or not 1 <= len(pattern) <= 16:
        raise ValueError('Invalid repeated input pattern')
    if any(not isinstance(p, dict) or set(p) != {'updates', 'buttons'} for p in pattern):
        raise ValueError('Invalid repeated input record')
    validate_actions([dict(name=f'pattern-{i}', **p) for i, p in enumerate(pattern)])
    actions = validate_actions(report.get('tail_actions'))
    markers = report.get('tail_records')
    if not isinstance(markers, list) or len(markers) > len(actions):
        raise ValueError('Invalid marker sequence')
    for i, marker in enumerate(markers):
        if not isinstance(marker, dict) or marker.get('name') != actions[i]['name']:
            raise ValueError('Markers must be the exact ordered action prefix')
        calls = marker.get('emulator_calls')
        if type(calls) is not int or calls <= 0:
            raise ValueError('Invalid emulator call count')
        if i and calls <= markers[i-1]['emulator_calls']:
            raise ValueError('Marker times must increase')
    if report['status'] == 'completed_budget' and len(markers) != len(actions):
        raise ValueError('A completed route is missing action markers')
    rows = []
    for marker in markers:
        # Name has already passed validate_actions; no arbitrary file paths.
        ram = (folder / ('tail-'+marker['name']+'.ram')).read_bytes()
        rows.append({'name': marker['name'], 'state': selected_state(ram)})
    return report, rows


def validate_ram_addresses(value: tuple[int, ...]) -> tuple[int, ...]:
    """Only explicit, unique common-NES-RAM bytes may extend comparison scope."""
    if not isinstance(value, (list, tuple)) or len(value) > 32 or any(
            type(x) is not int or not 0 <= x < 2048 for x in value):
        raise ValueError('Require at most 32 common-RAM byte addresses in 0..2047')
    if len(set(value)) != len(value):
        raise ValueError('Duplicate RAM byte address')
    return tuple(value)


def compare_routes(reference: Path, candidate: Path,
                   ram_addresses: tuple[int, ...] = ()) -> dict:
    ram_addresses = validate_ram_addresses(ram_addresses)
    a, ar = load_route(reference)
    b, br = load_route(candidate)
    for key in ('tail_actions', 'steps_requested', 'pattern'):
        if a.get(key) != b.get(key):
            raise ValueError('Different route input: '+key)
    if a.get('clock_mode', 'legacy') != b.get('clock_mode', 'legacy'):
        raise ValueError('Incompatible update-clock policies')
    common = min(len(ar), len(br))
    mismatches = []
    ram_mismatches = []
    for i, (x, y) in enumerate(zip(ar, br)):
        differences = {name: {'reference': x['state'][name], 'candidate': y['state'][name]}
                       for name in FIELDS if x['state'][name] != y['state'][name]}
        if differences:
            mismatches.append({'index': i, 'name': x['name'], 'fields': differences})
        if ram_addresses:
            memories = [(folder / ('tail-'+x['name']+'.ram')).read_bytes()
                        for folder in (reference, candidate)]
            if any(len(m) <= max(ram_addresses) for m in memories):
                raise ValueError('Insufficient captured RAM for requested bytes')
            changed = {f'{address:04x}': {'reference': memories[0][address],
                                         'candidate': memories[1][address]}
                       for address in ram_addresses
                       if memories[0][address] != memories[1][address]}
            if changed:
                ram_mismatches.append({'index': i, 'name': x['name'], 'bytes': changed})
    complete = (a['status'] == b['status'] == 'completed_budget'
                and common == len(a['tail_actions']) and common > 0)
    fault_free = a.get('fault') is None and b.get('fault') is None
    return {'passed': complete and fault_free and not mismatches and not ram_mismatches,
            'complete_routes': complete, 'fault_free': fault_free,
            'reference_fault': a.get('fault'),
            'ram_addresses': list(ram_addresses),
            'ram_bytes_checked': common * len(ram_addresses),
            'ram_mismatched_checkpoints': len(ram_mismatches),
            'ram_mismatches': ram_mismatches,
            'clock_mode': a.get('clock_mode', 'legacy'),
            'reference_platform': a['platform'], 'candidate_platform': b['platform'],
            'reference_status': a['status'], 'candidate_status': b['status'],
            'candidate_fault': b.get('fault'),
            'planned_checkpoints': len(a['tail_actions']), 'checkpoints_compared': common,
            'state_fields_checked': common * len(FIELDS),
            'state_bytes_checked': common * sum(size for _, size in FIELDS.values()),
            'mismatched_checkpoints': len(mismatches),
            'mismatches': mismatches,
            'reference_report_sha256': hashlib.sha256((reference/'route-report.json').read_bytes()).hexdigest(),
            'candidate_report_sha256': hashlib.sha256((candidate/'route-report.json').read_bytes()).hexdigest(),
            'reference_rom_sha256': a.get('rom_sha256'), 'candidate_rom_sha256': b.get('rom_sha256'),
            'reference_core_sha256': a.get('core_sha256'), 'candidate_core_sha256': b.get('core_sha256'),
            'scope': 'Selected area, camera and player fields plus explicitly requested common-RAM bytes at named input endpoints. Non-null faults reject acceptance. Not full RAM, pixels, audio, cycle timing, boss completion or whole-game equivalence.'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--ram-byte', type=lambda value: int(value, 0), action='append', default=[],
                        help='Additional common RAM byte to compare; repeat up to 32 times')
    args = parser.parse_args()
    result = compare_routes(args.reference, args.candidate, tuple(args.ram_byte))
    atomic_json(args.out, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'mismatches'}, indent=2))
    raise SystemExit(not result['passed'])
