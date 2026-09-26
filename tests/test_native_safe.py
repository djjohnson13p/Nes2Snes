"""Proof-domain and integration checks for conservative native RAM replacements."""
from pathlib import Path
import sys, unittest, tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from opcodes6502 import OPS
import native_safe as n
import direct_calls as d
from safe_address_fixture import create

class SafeAddressTests(unittest.TestCase):
    def test_procedural_fixture_is_repeatable(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ma = create(Path(a)); mb = create(Path(b))
            self.assertEqual(ma, mb)
            self.assertTrue(ma['safe_address_fixture'])
            self.assertEqual((Path(a)/'fixture.nes').read_bytes(), (Path(b)/'fixture.nes').read_bytes())
            self.assertTrue(any('index255' in r['name'] for r in ma['records']))

    def test_zero_index_base_only(self):
        for op, (name, mode, size) in OPS.items():
            if mode not in ('zpx', 'zpy'): continue
            for base in range(256):
                result = n.replacement(op, base)
                self.assertEqual(result is not None, base == 0)
                if result:
                    for index in range(256):
                        self.assertEqual((base + index) & 255, result[0] + index)

    def test_absolute_mirrors_for_every_address(self):
        for address in range(65536):
            result = n.replacement(0xAD, address)
            self.assertEqual(result is not None, 0x800 <= address < 0x2000)
            if result: self.assertEqual(result[0], address & 0x7ff)

    def test_indexed_mirrors_every_selected_address_and_index(self):
        for op in (0xBD, 0xB9):
            for address in range(0x800, 0x2000):
                result = n.replacement(op, address)
                if result:
                    for index in range(256):
                        self.assertLess(address + index, 0x2000)
                        self.assertLess(result[0] + index, 0x800)
                        self.assertEqual((address + index) & 0x7ff, result[0] + index)

    def test_alias_boundary_and_hardware_rejected(self):
        for op in (0xBD, 0xB9):
            for address in (0x701, 0x7ff, 0xf01, 0x1701, 0x1f01, 0x2000, 0x4000, 0x5115, 0xffff):
                self.assertIsNone(n.replacement(op, address))

    def test_control_flow_and_indirect_not_substituted(self):
        for op, operand in ((0x20,0x900),(0x4c,0x900),(0x6c,0x900),(0,0),(2,0),(0xb1,0xfe),(0x91,0xfe)):
            self.assertIsNone(n.replacement(op, operand))

    def test_input_domain_validation(self):
        for value in (-1, 0x10000):
            with self.assertRaises(ValueError): n.replacement(0xAD, value)
        with self.assertRaises(ValueError): n.replacement(0xB5, 256)

    def test_only_classified_sites_are_changed(self):
        prg = bytes((0xb5, 0, 0xad, 0, 0x0a, 0xb5, 0, 0xb5, 1))
        code = bytes((2, 0xb5, 2, 0xad, 0x0a, 0, 0, 2, 0xb5))
        result, selected, left = n.apply(prg, code, [dict(prg_offset=p) for p in (0, 2, 7)])
        self.assertEqual(result, bytes((0xb5, 0, 0xad, 0, 2, 0, 0, 2, 0xb5)))
        self.assertEqual(len(selected), 2)
        self.assertEqual(left, [dict(prg_offset=7)])

    def test_non_cop_rejected(self):
        with self.assertRaises(ValueError):
            n.apply(b'\xb5\x00', b'\xb5\x00', [dict(prg_offset=0)])
        with self.assertRaises(ValueError):
            n.apply(b'\xb5\x00', b'\x02', [dict(prg_offset=0)])

class SimpleWriterTests(unittest.TestCase):
    def source(self, opcode, address, simple=True):
        prg = bytes((opcode, address & 255, address >> 8))
        return d.plan(prg, [dict(prg_offset=0, mode='abs')], simple=simple)[1]

    def test_only_simple_writer_whitelist(self):
        for op, reg in d.STORE_OPS.items():
            for address in (0x2000, 0x2001, 0x2002, 0x2003, 0x2005, 0x2006, 0x5203, 0x5204):
                self.assertIn('DirectSimpleWrite' + reg, self.source(op, address))
                self.assertIn('DirectWrite' + reg, self.source(op, address, False))

    def test_complex_writers_still_save_full_context(self):
        for op, reg in d.STORE_OPS.items():
            for address in (0x2004, 0x2007, 0x4014, 0x4016):
                source = self.source(op, address)
                self.assertIn('DirectWrite' + reg, source)
                self.assertNotIn('DirectSimpleWrite', source)

    def test_no_direct_mapper_bank_change(self):
        for op in d.STORE_OPS:
            for address in (0x5115, 0x5116, 0x5117):
                self.assertNotIn('jsl', self.source(op, address))

if __name__ == '__main__': unittest.main()
