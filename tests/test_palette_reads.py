"""Fixture provenance and strict-comparison checks; execution oracle is separate."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from palette_read_fixture import create
from verify_palette_reads import compare


class PaletteReads(unittest.TestCase):
    def setUp(self):
        self.records = [dict(name='one', address=0x300), dict(name='two', address=0x304)]
        self.memory = bytes(0x800)

    def test_full_records(self):
        result = compare(self.records, self.memory, self.memory)
        self.assertEqual((result['records_checked'], result['bytes_checked'], result['mismatch_count']), (2, 8, 0))

    def test_all_result_bits_are_compared(self):
        for byte in range(8):
            for bit in range(8):
                changed = bytearray(self.memory); changed[0x300+byte] = 1 << bit
                self.assertEqual(compare(self.records, self.memory, bytes(changed))['mismatch_count'], 1)

    def test_truncated_or_oversized_captures_rejected(self):
        for length in (0, 0x307, 0x7ff, 0x801):
            with self.assertRaises(ValueError): compare(self.records, bytes(length), self.memory)
            with self.assertRaises(ValueError): compare(self.records, self.memory, bytes(length))

    def test_empty_records_rejected(self):
        for records in ([], None, {}):
            with self.assertRaises(ValueError): compare(records, self.memory, self.memory)

    def test_invalid_layout_rejected(self):
        for value in (0x300, 0x305, -1, 0x800, True, 772.0):
            rows = copy.deepcopy(self.records); rows[1]['address'] = value
            with self.assertRaises(ValueError): compare(rows, self.memory, self.memory)

    def test_duplicate_or_invalid_names_rejected(self):
        for name in ('one', '', None, 7):
            rows = copy.deepcopy(self.records); rows[1]['name'] = name
            with self.assertRaises(ValueError): compare(rows, self.memory, self.memory)

    def test_fixture_is_deterministic_and_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root)/'a', Path(root)/'b'
            meta = create(a, 0, 0); other = create(b, 0, 0)
            self.assertEqual(meta, other)
            self.assertEqual((a/'fixture.nes').read_bytes(), (b/'fixture.nes').read_bytes())
            self.assertTrue(meta['procedural_fixture'])
            self.assertEqual(len(meta['records']), 148)
            self.assertLessEqual(meta['program_bytes'], 0x1ffa)
            self.assertEqual(len(meta['cases']), 37)
            self.assertEqual({c['mode'] for c in meta['cases']}, {'absolute', 'register-mirror', 'indexed', 'indirect'})
            self.assertEqual({c['increment'] for c in meta['cases']}, {1, 32})
            self.assertEqual({c['bus_high'] for c in meta['cases']}, {0, 64, 128, 192})
            self.assertEqual(meta, json.loads((a/'trace-summary.json').read_text()))

    def test_fixture_rejects_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            for seed in (-1, 256, True, '1'):
                with self.assertRaises(ValueError): create(Path(root), seed, 0)
            for bank in (-1, 2, 4, True):
                with self.assertRaises(ValueError): create(Path(root), 0, bank)
