"""Fixture and independent-state parsing contracts for the memory completion pass."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_native import QUICK_ZPX
from zero_page_store_fixture import create as sty_create
from oam_copy_fixture import create as oam_create
from verify_memory_completion import fcs_oam


def tagged(tag, payload):
    return tag + len(payload).to_bytes(4, 'little') + payload


def state(payload):
    return b'FCS' + bytes(13) + b'\x03' + len(payload).to_bytes(4, 'little') + payload


class MemoryCompletionTests(unittest.TestCase):
    def test_sty_has_a_selected_fast_path(self):
        self.assertIn('STY', QUICK_ZPX)

    def test_sty_fixture_is_bounded(self):
        with tempfile.TemporaryDirectory() as t:
            m = sty_create(Path(t), 7, True)
            self.assertEqual(m['store_cases'], 128)
            self.assertEqual(len(m['records']), 256)
            self.assertLessEqual(m['program_bytes'], 0x1ffa)
            self.assertLessEqual(m['result_end'], 0x780)
            self.assertTrue(m['c0'])
            self.assertTrue(any('baseff' in row['name'] for row in m['records']))

    def test_fixture_is_reproducible(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t)/'a', Path(t)/'b'
            sty_create(a, 21); sty_create(b, 21)
            for name in ('fixture.nes', 'counts.u32', 'trace-summary.json'):
                self.assertEqual((a/name).read_bytes(), (b/name).read_bytes())

    def test_oam_fixture_declares_its_limited_scope(self):
        with tempfile.TemporaryDirectory() as t:
            m = oam_create(Path(t), 0x1a, 7, True, 'STY')
            self.assertEqual(m['oam_address'], 0)
            self.assertEqual(m['page'], 0x1a)
            self.assertEqual(len(m['records']), 3)
            self.assertIn('last_dma_byte_on_ppu_latch', [r['name'] for r in m['records']])
            self.assertLessEqual(m['program_bytes'], 0x1ffa)

    def test_oam_fixture_rejects_uncovered_pages_and_instructions(self):
        with tempfile.TemporaryDirectory() as t:
            for page in (1, 3, 0x20, 0x40, 0x100):
                with self.assertRaises(ValueError): oam_create(Path(t), page)
            with self.assertRaises(ValueError): oam_create(Path(t), writer='LDA')

    def test_fcs_extracts_oam_and_latch(self):
        data = bytes(range(256))
        payload = tagged(b'SPRA', data) + tagged(b'PGEN', b'\xa9')
        self.assertEqual(fcs_oam(state(payload)), (data, 0xa9))

    def test_fcs_skips_unrelated_sections_and_tags(self):
        payload = tagged(b'XOFF', b'\x00') + tagged(b'PGEN', b'\x09') + tagged(b'SPRA', bytes(256))
        unrelated = b'\x01' + (3).to_bytes(4, 'little') + b'abc'
        d = state(payload)
        self.assertEqual(fcs_oam(d[:16] + unrelated + d[16:]), (bytes(256), 9))

    def test_fcs_rejects_missing_required_fields(self):
        for payload in (b'', tagged(b'SPRA', bytes(256)), tagged(b'PGEN', b'\x00')):
            with self.assertRaises(ValueError): fcs_oam(state(payload))

    def test_fcs_rejects_duplicate_fields(self):
        payload = tagged(b'SPRA', bytes(256)) + tagged(b'SPRA', bytes(256)) + tagged(b'PGEN', b'\x00')
        with self.assertRaises(ValueError): fcs_oam(state(payload))

    def test_fcs_rejects_wrong_lengths(self):
        for n in (0, 255, 257):
            with self.assertRaises(ValueError):
                fcs_oam(state(tagged(b'SPRA', bytes(n)) + tagged(b'PGEN', b'\x00')))

    def test_fcs_rejects_truncation_and_bad_magic(self):
        valid = state(tagged(b'SPRA', bytes(256)) + tagged(b'PGEN', b'\x00'))
        for data in (b'', valid[:15], valid[:-1], b'XXX'+valid[3:], valid+b'\x03'):
            with self.assertRaises(ValueError): fcs_oam(data)

    def test_fcs_rejects_incomplete_ppu_field_header(self):
        with self.assertRaises(ValueError): fcs_oam(state(b'SPR'))


if __name__ == '__main__': unittest.main()
