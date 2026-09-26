import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from route_evidence import guarded_update_pc, selected_state, atomic_json, compare_routes

class RouteEvidenceTests(unittest.TestCase):
    def code(self, body):
        p = bytearray([0xEA] * 8192)
        p[:len(body)] = body
        return bytes(p)

    def test_saved_outdoor_route_is_a_valid_extension(self):
        from gameplay_route import validate_actions
        root=Path(__file__).resolve().parents[1]
        stair=json.loads((root/'tools/routes/cv3-stair-room.json').read_text())
        outdoor=validate_actions(json.loads((root/'tools/routes/cv3-outdoor-respawn.json').read_text()))
        self.assertEqual(len(outdoor),84)
        self.assertEqual(outdoor[:len(stair)],stair)

    def test_first_forward_guard(self):
        p = self.code(bytes.fromhex('48 8a 48 98 48 a4 51 d0 06 e6 51 ea ea ea ea 40'))
        self.assertEqual(guarded_update_pc(p, 0xE000), 0xE009)

    def test_zero_page_zero_is_valid(self):
        self.assertEqual(guarded_update_pc(self.code(bytes.fromhex('a4 00 d0 02 e6 00 40')), 0xE000), 0xE004)

    def test_uncertain_control_flow_rejected(self):
        for prefix in ('20 00 e1', '4c 00 e1', '40', '60', '00', 'f8', '02'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                guarded_update_pc(self.code(bytes.fromhex(prefix+' a4 51 d0 02 e6 51 40')), 0xE000)

    def test_wrong_guard_and_backward_branch_rejected(self):
        for code in ('a4 51 f0 02 e6 51', 'a4 51 d0 fe e6 51',
                     'a4 51 d0 02 e6 52', 'a5 51 d0 02 e6 51',
                     'a4 51 d0 01 e6 51', 'a4 51 d0 02 c6 51'):
            with self.subTest(code=code), self.assertRaises(ValueError):
                guarded_update_pc(self.code(bytes.fromhex(code)), 0xE000)

    def test_marker_range_and_scan_bound(self):
        for value in (-1, 0xDFFF, 0xFFFA, 65536, True, 'E000'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guarded_update_pc(bytes(8192), value)
        with self.assertRaises(ValueError):
            guarded_update_pc(bytes(20), 0xE000)
        with self.assertRaises(ValueError):
            guarded_update_pc(self.code(bytes([0xEA]*33)+bytes.fromhex('a4 51 d0 02 e6 51')), 0xE000)

    def test_ram_fields_include_camera_not_just_screen_position(self):
        m = bytearray(2048);m[0x56:0x58] = b'\x34\x12';m[0x438] = 128
        self.assertEqual(selected_state(m)['camera_x'], 0x1234)
        self.assertEqual(selected_state(m)['player_x'], 128)
        with self.assertRaises(ValueError): selected_state(bytes(100))

    def test_atomic_snapshot_and_failed_replacement(self):
        with tempfile.TemporaryDirectory() as name:
            p = Path(name)/'progress.json';atomic_json(p, {'status': 'running', 'done': 1})
            with patch('route_evidence.os.replace', side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError): atomic_json(p, {'done': 2})
            self.assertEqual(json.loads(p.read_text())['done'], 1)
            self.assertEqual([x.name for x in p.parent.iterdir()], ['progress.json'])
            with self.assertRaises(ValueError): atomic_json(p, {'invalid': float('nan')})
            self.assertEqual(json.loads(p.read_text())['done'], 1)
            atomic_json(p, {'status': 'failed', 'done': 1})
            self.assertEqual(json.loads(p.read_text())['status'], 'failed')

    def fixture(self, folder, platform='nes', failed=False):
        folder.mkdir()
        report = dict(platform=platform, status='failed' if failed else 'completed_budget',
                      clock_mode='guarded', steps_requested=31, pattern=[dict(updates=8, buttons=['right'])],
                      tail_actions=[dict(name='first', updates=8, buttons=['right']),
                                    dict(name='second', updates=4, buttons=[])],
                      tail_records=[dict(name='first', emulator_calls=10),
                                    dict(name='second', emulator_calls=20)])
        for marker in report['tail_records']:
            m = bytearray(2048);m[0x438] = 128;m[0x18] = 4
            (folder/('tail-'+marker['name']+'.ram')).write_bytes(m)
        atomic_json(folder/'route-report.json', report)
        return report

    def test_complete_selected_field_match(self):
        with tempfile.TemporaryDirectory() as name:
            a,b = Path(name)/'a',Path(name)/'b';self.fixture(a);self.fixture(b,'snes')
            r = compare_routes(a,b)
            self.assertTrue(r['passed']);self.assertEqual(r['state_bytes_checked'], 18)
            self.assertEqual(r['checkpoints_compared'], 2)

    def test_camera_only_difference_is_failure(self):
        with tempfile.TemporaryDirectory() as name:
            a,b=Path(name)/'a',Path(name)/'b';self.fixture(a);self.fixture(b,'snes')
            p=b/'tail-second.ram';m=bytearray(p.read_bytes());m[0x56]=45;p.write_bytes(m)
            r=compare_routes(a,b);self.assertFalse(r['passed'])
            self.assertEqual(r['mismatches'][0]['index'],1)
            self.assertEqual(set(r['mismatches'][0]['fields']),{'camera_x'})

    def test_failed_or_empty_prefix_never_passes(self):
        with tempfile.TemporaryDirectory() as name:
            a,b=Path(name)/'a',Path(name)/'b';self.fixture(a);d=self.fixture(b,'snes',True)
            self.assertFalse(compare_routes(a,b)['passed'])
            for markers in ([], d['tail_records'][:1]):
                d['tail_records']=markers;atomic_json(b/'route-report.json',d)
                self.assertFalse(compare_routes(a,b)['passed'])

    def test_clock_and_input_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            a,b=Path(name)/'a',Path(name)/'b';self.fixture(a);original=self.fixture(b,'snes')
            for key,value in [('clock_mode','legacy'),('steps_requested',32),('pattern',[{}])]:
                d=copy.deepcopy(original);d[key]=value;atomic_json(b/'route-report.json',d)
                with self.subTest(key=key),self.assertRaises(ValueError):compare_routes(a,b)

    def test_missing_out_of_order_unsafe_markers_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            a,b=Path(name)/'a',Path(name)/'b';self.fixture(a);original=self.fixture(b,'snes')
            for markers in ([], list(reversed(original['tail_records'])),
                            [dict(name='../escape',emulator_calls=10)],
                            [dict(name='first',emulator_calls=True)]):
                d=copy.deepcopy(original);d['tail_records']=markers;atomic_json(b/'route-report.json',d)
                with self.subTest(markers=markers),self.assertRaises(ValueError):compare_routes(a,b)

if __name__ == '__main__': unittest.main()
