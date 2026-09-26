"""Checks for the opt-in indexed-indirect reader and its authored test input."""
import inspect
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from build_native import build
from indirect_x_fixture import create, READS

class IndirectXTests(unittest.TestCase):
    def test_option_is_off_by_default(self):
        self.assertIs(inspect.signature(build).parameters['quick_indirect_x'].default, False)

    def test_invalid_blocks_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            for block in (-1, 16, 256):
                with self.assertRaises(ValueError):
                    create(Path(name), block=block)

    def test_all_pointer_offsets_and_all_indexes_are_exercised(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            seen_pointers, seen_indexes, seen_banks = set(), set(), set()
            for block in range(16):
                for indexes in (False, True):
                    meta = create(root, block=block, seed=7, sweep_indexes=indexes)
                    self.assertEqual(meta['expected_fast_reads'], 112)
                    self.assertEqual(meta['expected_io_reads'], 24)
                    self.assertEqual(len(meta['records']), 136)
                    self.assertLessEqual(meta['program_bytes'], 0x1FFA)
                    self.assertEqual({row['operation'] for row in meta['coverage']}, set(READS))
                    for row in meta['coverage']:
                        seen_pointers.add(row['pointer'])
                        seen_indexes.add(row['index'])
                        seen_banks.add((row['primary_bank'], row['c_bank']))
            self.assertEqual(seen_pointers, set(range(256)))
            self.assertEqual(seen_indexes, set(range(256)))
            self.assertEqual(seen_banks, {(p, c) for p in range(16) for c in (7, 30)})

    def test_nmi_fixture_has_bounded_code_and_the_same_records(self):
        with tempfile.TemporaryDirectory() as name:
            meta = create(Path(name), block=15, seed=255, in_nmi=True)
            self.assertTrue(meta['in_nmi'])
            self.assertEqual(len(meta['records']), 136)
            self.assertLessEqual(meta['program_bytes'], 0x1FFA)

    @unittest.skipUnless(shutil.which('ca65') and shutil.which('ld65'), 'requires cc65')
    def test_actual_build_tables_and_master_disable(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            create(root)
            expected_labels = {'Quick'+op+'_IX' for op in READS}
            for label, args, enabled in [
                ('default', {}, False),
                ('enabled', {'quick_indirect_x': True}, True),
                ('master-off', {'quick_indirect_x': True, 'quick_indirect': False}, False),
            ]:
                out = root/label
                result = build(root/'fixture.nes', root, out, **args)
                self.assertIs(result['quick_indirect_x'], enabled)
                table = (out/'native-assets/quick-zp-table.inc').read_text().splitlines()
                actual = {line.removeprefix('.word ') for line in table if line.endswith('_IX')}
                self.assertEqual(actual, expected_labels if enabled else set())
                # $81 is STA (zp,X); writes never use the read-only shortcut.
                self.assertEqual(table[0x81], '.word CopGeneric')
                self.assertFalse(result['complete_game_port'])

if __name__ == '__main__':
    unittest.main()
