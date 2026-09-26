"""Fail closed when deterministic replay evidence is not comparable."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from compare_replays import compare


class ReplayComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, times in [('old', (10, 18)), ('new', (5, 9))]:
            folder = self.root / name
            folder.mkdir()
            report = dict(rom_sha256=name, input_sha256='same-input', core_sha256='same-core',
                          samples=[dict(name=n, render_frame=i + 1, snes_frame=t)
                                   for i, (n, t) in enumerate(zip(('a', 'b'), times))])
            (folder / 'replay.json').write_text(json.dumps(report))
            for image in ('a', 'b'):
                Image.new('RGB', (2, 2)).save(folder / (image + '.png'))

    def run_compare(self):
        return compare(self.root / 'old', self.root / 'new', self.root / 'result.json')

    def test_matching_pixels_and_interval_speed(self):
        result = self.run_compare()
        self.assertEqual(result['pixel_mismatches'], 0)
        self.assertEqual(result['pixels_checked'], 8)
        self.assertEqual(result['intervals'][0]['speed_ratio'], 2)

    def test_counts_pixel_difference(self):
        with Image.open(self.root / 'new/a.png') as source:
            image = source.copy()
        image.putpixel((0, 0), (255, 0, 0))
        image.save(self.root / 'new/a.png')
        self.assertEqual(self.run_compare()['pixel_mismatches'], 1)

    def test_refuses_different_input_or_core(self):
        path = self.root / 'new/replay.json'
        original = path.read_text()
        for field in ('input_sha256', 'core_sha256'):
            report = json.loads(original)
            report[field] = 'different'
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, field):
                self.run_compare()

    def test_refuses_mixed_frame_tagging_methods(self):
        path=self.root / 'new/replay.json'
        report=json.loads(path.read_text())
        report['alignment']='video-callback-presented-id-v1'
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError,'alignment'):
            self.run_compare()

    def test_refuses_different_render_frame(self):
        path = self.root / 'new/replay.json'
        report = json.loads(path.read_text())
        report['samples'][0]['render_frame'] = 50
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'logical render frames'):
            self.run_compare()


if __name__ == '__main__':
    unittest.main()
