"""Matching coordinates do not override faults or explicit RAM mismatches."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from route_evidence import compare_routes, atomic_json, validate_ram_addresses


class RouteFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('nes','snes'):
            p=self.root/name;p.mkdir()
            report=dict(platform=name,status='completed_budget',clock_mode='guarded',
                        steps_requested=31,pattern=[dict(updates=8,buttons=[])],
                        tail_actions=[dict(name='first',updates=8,buttons=[])],
                        tail_records=[dict(name='first',emulator_calls=10)])
            atomic_json(p/'route-report.json',report)
            (p/'tail-first.ram').write_bytes(bytes(2048))

    def compare(self, addresses=()):
        return compare_routes(self.root/'nes',self.root/'snes',addresses)

    def test_matching_faulted_reports_rejected_on_either_platform(self):
        for platform in ('nes','snes'):
            p=self.root/platform/'route-report.json';d=json.loads(p.read_text())
            for fault in ({'code':1}, {}, False, 0, ''):
                d['fault']=fault;atomic_json(p,d)
                r=self.compare();self.assertFalse(r['passed']);self.assertFalse(r['fault_free'])
                self.assertEqual(r['reference_fault' if platform=='nes' else 'candidate_fault'],fault)
            d['fault']=None;atomic_json(p,d)
            self.assertTrue(self.compare()['passed'])

    def test_rng_difference_fails_only_when_explicitly_in_scope(self):
        p=self.root/'snes/tail-first.ram';data=bytearray(p.read_bytes());data[31]=39;p.write_bytes(data)
        self.assertTrue(self.compare()['passed'])
        r=self.compare((31,60));self.assertFalse(r['passed'])
        self.assertEqual(r['mismatched_checkpoints'],0)
        self.assertEqual(r['ram_bytes_checked'],2)
        self.assertEqual(r['ram_mismatches'][0]['bytes'],{'001f':{'reference':0,'candidate':39}})

    def test_ram_counts_remain_separate_from_selected_state_counts(self):
        r=self.compare((0,2047));self.assertTrue(r['passed'])
        self.assertEqual(r['state_bytes_checked'],9);self.assertEqual(r['ram_bytes_checked'],2)

    def test_invalid_address_scope_rejected(self):
        for value in (None, '31', (True,), (-1,), (2048,), (31,31), tuple(range(33))):
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_ram_addresses(value)

    def test_requested_missing_byte_rejected(self):
        (self.root/'nes/tail-first.ram').write_bytes(bytes(1200))
        with self.assertRaisesRegex(ValueError,'Insufficient captured RAM'):
            self.compare((2047,))

    def test_empty_scope_preserves_legacy_counts(self):
        r=self.compare();self.assertTrue(r['passed']);self.assertEqual(r['ram_bytes_checked'],0)
        self.assertEqual(r['ram_mismatches'],[])


if __name__=='__main__':unittest.main()
