import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from mask_fixture import create
from rom import Rom


class MaskFixtureTests(unittest.TestCase):
    def test_invalid_masks(self):
        with tempfile.TemporaryDirectory() as d:
            for value in (-2, -1, 1, 31, 32, 256, True, '24', 24.0):
                with self.subTest(mask=value), self.assertRaises(ValueError):
                    create(Path(d), value)

    def test_invalid_sprite_size_type(self):
        with tempfile.TemporaryDirectory() as d:
            for value in (0, 1, 'true', None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    create(Path(d), 24, value)

    def test_invalid_split(self):
        with tempfile.TemporaryDirectory() as d:
            for value in (-1, 1, 31, 32, True, '24'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    create(Path(d), split_mask=value)
            for line in (0, 8, 136, 240, True, 96.0):
                with self.subTest(line=line), self.assertRaises(ValueError):
                    create(Path(d), split_mask=24, split_line=line)
            for mask in (0, 2, 4, 6):
                with self.subTest(mask=mask), self.assertRaises(ValueError):
                    create(Path(d), mask=mask, split_mask=24)

    def test_deterministic_no_external_assets(self):
        with tempfile.TemporaryDirectory() as d:
            a = create(Path(d)/'a'); b = create(Path(d)/'b')
            self.assertEqual(a, b)
            self.assertEqual(a['rom_sha256'], hashlib.sha256((Path(d)/'a/fixture.nes').read_bytes()).hexdigest())
            self.assertEqual(len((Path(d)/'a/rgb-palette.bin').read_bytes()), 192)

    def test_all_32_variants_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            hashes = {create(Path(d), mask, size)['rom_sha256']
                      for mask in range(0, 32, 2) for size in (False, True)}
            self.assertEqual(len(hashes), 32)

    def test_fixture_layout_and_declared_sites(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); meta = create(p); rom = Rom.read(p/'fixture.nes')
            self.assertEqual(rom.mapper, 5)
            self.assertEqual(len(rom.prg), 262144)
            self.assertEqual(len(rom.chr), 131072)
            counts = struct.unpack('<262144I', (p/'counts.u32').read_bytes())
            pcs = struct.unpack('<262144H', (p/'cpu-address.u16').read_bytes())
            self.assertTrue(all(pc == 0xe000+i-0x3e000 for i, pc in enumerate(pcs) if counts[i]))
            self.assertGreater(sum(counts), 100)
            self.assertTrue(all(c in (0, 1) for c in counts))
            self.assertTrue(meta['mask_fixture'])

    def test_split_has_distinct_interrupt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); create(p, split_mask=0)
            rom = Rom.read(p/'fixture.nes')
            self.assertNotEqual(rom.prg[-6:-4], rom.prg[-2:])
            meta = json.loads((p/'trace-summary.json').read_text())
            self.assertEqual(meta['split_line'], 96)
            self.assertEqual(meta['split_mask'], 0)

    def test_cycle_input_validation(self):
        with tempfile.TemporaryDirectory() as d:
            for value in (0, 1, 'true', None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    create(Path(d), cycle=value)
            with self.assertRaises(ValueError):
                create(Path(d), split_mask=24, cycle=True)

    def test_cycle_is_distinct_and_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            static = create(p/'static')
            dynamic = create(p/'dynamic', cycle=True)
            again = create(p/'again', cycle=True)
            self.assertNotEqual(static['rom_sha256'], dynamic['rom_sha256'])
            self.assertEqual(dynamic, again)
            self.assertTrue(dynamic['cycle'])

    def test_left_window_truth_table(self):
        text = (Path(__file__).resolve().parents[1]/'snes/src/native_masks.inc').read_text()
        entries = text.split('WindowMasks:')[1].split('.byte')[1].splitlines()[0]
        actual = [int(x.strip().replace('$', ''), 16) for x in entries.split(',')]
        for mask in range(256):
            expected = (0 if mask & 2 else 3) | (0 if mask & 4 else 16)
            self.assertEqual(actual[(mask >> 1) & 3], expected)
