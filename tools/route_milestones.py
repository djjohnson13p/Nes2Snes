#!/usr/bin/env python3
"""Require named destinations, not merely two equal or completed route budgets.

This reads private captures only. It never patches guest memory or input. A
passing predicate is scoped to its exact route; use independent NES replay and
paired NES/SNES state comparisons separately. No automatic boss-clear claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from route_evidence import FIELDS, atomic_json, load_route


def actions_digest(actions: list[dict]) -> str:
    from gameplay_route import validate_actions
    data = json.dumps(validate_actions(actions), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode()).hexdigest()


def validate_contract(value: object) -> dict:
    keys = {'format', 'label', 'clock_mode', 'steps_requested', 'pattern',
            'actions_sha256', 'milestones'}
    if not isinstance(value, dict) or set(value) != keys or type(value['format']) is not int or value['format'] != 1:
        raise ValueError('Unknown milestone contract format')
    if not isinstance(value['label'], str) or not 1 <= len(value['label']) <= 160:
        raise ValueError('Require a bounded scope label')
    if value['clock_mode'] not in ('guarded', 'legacy') or type(value['steps_requested']) is not int or not 1 <= value['steps_requested'] <= 1000:
        raise ValueError('Invalid route clock or step count')
    from gameplay_route import validate_actions
    pattern = value['pattern']
    if not isinstance(pattern, list) or not 1 <= len(pattern) <= 16 or any(
            not isinstance(p, dict) or set(p) != {'updates', 'buttons'} for p in pattern):
        raise ValueError('Invalid repeated pattern')
    validate_actions([dict(name=f'p-{i}', **p) for i, p in enumerate(pattern)])
    if not isinstance(value['actions_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['actions_sha256']):
        raise ValueError('Invalid action digest')
    milestones = value['milestones']
    if not isinstance(milestones, list) or not 1 <= len(milestones) <= 512:
        raise ValueError('Require nonempty milestones')
    names = set()
    for row in milestones:
        if not isinstance(row, dict) or set(row) != {'name', 'state', 'ram_bytes'}:
            raise ValueError('Invalid milestone fields')
        name = row['name']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name) or name in names:
            raise ValueError('Unsafe or duplicate milestone name')
        names.add(name)
        state = row['state']
        if not isinstance(state, dict) or set(state) != set(FIELDS) or any(
                type(state[k]) is not int or not 0 <= state[k] < 256 ** size
                for k, (_, size) in FIELDS.items()):
            raise ValueError('Require all bounded selected-state predicates')
        checks = row['ram_bytes']
        if not isinstance(checks, list) or len(checks) > 32:
            raise ValueError('Invalid RAM predicates')
        addresses = set()
        for check in checks:
            if not isinstance(check, dict) or set(check) != {'address', 'equals'}:
                raise ValueError('Invalid RAM predicate fields')
            address, expected = check['address'], check['equals']
            if type(address) is not int or not 0 <= address < 2048 or address in addresses or type(expected) is not int or not 0 <= expected < 256:
                raise ValueError('RAM predicate outside unique common NES RAM bytes')
            addresses.add(address)
    return value


def verify(folder: Path, contract_path: Path) -> dict:
    contract = validate_contract(json.loads(contract_path.read_text()))
    report, rows = load_route(folder)
    for key in ('clock_mode', 'steps_requested', 'pattern'):
        if report.get(key) != contract[key]:
            raise ValueError('Route does not match contract: ' + key)
    if actions_digest(report['tail_actions']) != contract['actions_sha256']:
        raise ValueError('Route action digest does not match contract')
    names = [a['name'] for a in report['tail_actions']]
    required = [r['name'] for r in contract['milestones']]
    if any(name not in names for name in required):
        raise ValueError('Contract names an absent action')
    indexes = [names.index(name) for name in required]
    if indexes != sorted(indexes):
        raise ValueError('Milestones must follow action order')
    observed = {r['name']: r['state'] for r in rows}
    results = []
    for row in contract['milestones']:
        actual = observed.get(row['name'])
        differences = {}
        if actual is None:
            differences['missing_checkpoint'] = True
        else:
            differences.update({k: {'expected': row['state'][k], 'actual': actual[k]}
                                for k in FIELDS if actual[k] != row['state'][k]})
            memory = (folder / ('tail-' + row['name'] + '.ram')).read_bytes()
            for check in row['ram_bytes']:
                address = check['address']
                actual_byte = memory[address] if address < len(memory) else None
                if actual_byte != check['equals']:
                    differences[f'ram_{address:04x}'] = {'expected': check['equals'], 'actual': actual_byte}
        results.append({'name': row['name'], 'passed': not differences, 'differences': differences})
    complete = report['status'] == 'completed_budget' and report.get('fault') is None
    return {'passed': complete and all(r['passed'] for r in results),
            'complete_route': complete, 'label': contract['label'], 'platform': report['platform'],
            'milestones_checked': len(results), 'results': results,
            'contract_sha256': hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            'route_report_sha256': hashlib.sha256((folder/'route-report.json').read_bytes()).hexdigest(),
            'actions_sha256': contract['actions_sha256'],
            'rom_sha256': report.get('rom_sha256'), 'core_sha256': report.get('core_sha256'),
            'scope': 'Named selected-state and common-RAM predicates for this exact input. Not full memory, pixels, audio, speed, boss defeat or whole-game equivalence.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('route', 'contract', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.route, args.contract)
    atomic_json(args.out, result)
    print(json.dumps(result, indent=2))
    raise SystemExit(not result['passed'])
