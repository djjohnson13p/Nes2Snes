"""Authored RAM fixtures: equal sessions alone must not certify a destination."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from route_evidence import FIELDS, atomic_json, compare_routes
from route_milestones import actions_digest, validate_contract, verify


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'route'
        self.folder.mkdir()
        self.actions = [{'name': 'start', 'updates': 8, 'buttons': ['right']},
                        {'name': 'arrived', 'updates': 4, 'buttons': []}]
        self.state = {'game_state': 4, 'area_bytes': 12, 'camera_x': 17,
                      'player_x': 64, 'player_y': 80}
        for action in self.actions:
            ram = bytearray(2048)
            for key, (offset, size) in FIELDS.items():
                ram[offset:offset+size] = self.state[key].to_bytes(size, 'little')
            ram[60] = 8
            (self.folder/('tail-'+action['name']+'.ram')).write_bytes(ram)
        self.report = dict(platform='nes', status='completed_budget', clock_mode='guarded',
                           steps_requested=31, pattern=[{'updates': 8, 'buttons': ['right']}],
                           tail_actions=self.actions,
                           tail_records=[{'name': 'start', 'emulator_calls': 10},
                                         {'name': 'arrived', 'emulator_calls': 20}])
        self.contract = dict(format=1, label='Procedural destination', clock_mode='guarded',
                             steps_requested=31, pattern=self.report['pattern'],
                             actions_sha256=actions_digest(self.actions),
                             milestones=[{'name': 'arrived', 'state': self.state,
                                          'ram_bytes': [{'address': 60, 'equals': 8}]}])
        self.plan = self.root/'contract.json'
        self.save()

    def save(self):
        atomic_json(self.folder/'route-report.json', self.report)
        atomic_json(self.plan, self.contract)

    def test_complete_expected_destination_passes(self):
        result = verify(self.folder, self.plan)
        self.assertTrue(result['passed'])
        self.assertEqual(result['milestones_checked'], 1)
        self.assertEqual(len(result['route_report_sha256']), 64)

    def test_equal_wrong_routes_do_not_prove_a_destination(self):
        self.assertTrue(compare_routes(self.folder, self.folder)['passed'])
        self.contract['milestones'][0]['state'] = dict(self.state, area_bytes=99)
        self.save()
        self.assertFalse(verify(self.folder, self.plan)['passed'])

    def test_wrong_health_byte_rejected_even_when_coordinates_match(self):
        self.contract['milestones'][0]['ram_bytes'][0]['equals'] = 0
        self.save()
        self.assertFalse(verify(self.folder, self.plan)['passed'])

    def test_failed_prefix_never_passes(self):
        self.report['status'] = 'failed'
        self.report['tail_records'] = self.report['tail_records'][:1]
        self.save()
        result = verify(self.folder, self.plan)
        self.assertFalse(result['passed'])
        self.assertIn('missing_checkpoint', result['results'][0]['differences'])

    def test_recorded_fault_never_passes(self):
        self.report['fault'] = {'code': 1}
        self.save()
        self.assertFalse(verify(self.folder, self.plan)['passed'])

    def test_action_digest_binds_buttons_and_duration(self):
        for key, value in [('buttons', ['left']), ('updates', 9)]:
            original = copy.deepcopy(self.report)
            self.report['tail_actions'][0][key] = value
            self.save()
            with self.assertRaisesRegex(ValueError, 'action digest'):
                verify(self.folder, self.plan)
            self.report = original

    def test_clock_steps_and_pattern_are_bound(self):
        original = copy.deepcopy(self.contract)
        for key, value in [('clock_mode', 'legacy'), ('steps_requested', 32),
                           ('pattern', [{'updates': 9, 'buttons': ['right']}])]:
            self.contract = dict(original, **{key: value})
            self.save()
            with self.assertRaisesRegex(ValueError, 'does not match contract'):
                verify(self.folder, self.plan)

    def test_unsafe_duplicate_absent_and_reordered_milestones_rejected(self):
        row = self.contract['milestones'][0]
        for milestones in ([dict(row, name='../escape')], [row, row],
                           [dict(row, name='absent')], [row, dict(row, name='start')]):
            self.contract['milestones'] = milestones
            self.save()
            with self.assertRaises(ValueError):
                verify(self.folder, self.plan)

    def test_unbounded_boolean_empty_and_unknown_contracts_rejected(self):
        for key, value in [('format', True), ('steps_requested', True), ('milestones', []),
                           ('actions_sha256', 'not-a-hash'), ('extra', 1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_contract(dict(self.contract, **{key: value}))
        for state in ({}, dict(self.state, player_x=True), dict(self.state, player_x=256)):
            contract = copy.deepcopy(self.contract)
            contract['milestones'][0]['state'] = state
            with self.assertRaises(ValueError):
                validate_contract(contract)

    def test_ram_bounds_and_duplicate_bytes_rejected(self):
        for checks in ([{'address': 2048, 'equals': 0}], [{'address': -1, 'equals': 0}],
                       [{'address': True, 'equals': 0}], [{'address': 0, 'equals': 256}],
                       [{'address': 0, 'equals': 0}]*2):
            contract = copy.deepcopy(self.contract)
            contract['milestones'][0]['ram_bytes'] = checks
            with self.assertRaises(ValueError):
                validate_contract(contract)

    def test_saved_block103_route_and_contract_match(self):
        root = Path(__file__).resolve().parents[1]/'tools/routes'
        actions = json.loads((root/'cv3-block103-entry.json').read_text())
        contract = validate_contract(json.loads((root/'cv3-block103-entry.milestones.json').read_text()))
        self.assertEqual(len(actions), 133)
        self.assertEqual(actions_digest(actions), contract['actions_sha256'])
        self.assertEqual(actions[-1]['name'], 'b103-entry-settled')
        old = json.loads((root/'cv3-outdoor-respawn.json').read_text())
        self.assertEqual(actions[:70], old[:70])
        self.assertNotEqual(len(actions), 117)


if __name__ == '__main__':
    unittest.main()
