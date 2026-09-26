import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from raster_fixture import create
from rom import Rom

class TestRasterFixture(unittest.TestCase):
    def test_invalid_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            for y in (-1,240):
                with self.assertRaises(ValueError):create(Path(d),y)
            for delay in (-1,41):
                with self.assertRaises(ValueError):create(Path(d),178,delay)
    def test_original_fixture_layout(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);m=create(p,178);r=Rom.read(p/'fixture.nes')
            self.assertEqual(r.mapper,5);self.assertEqual(len(r.prg),0x40000);self.assertEqual(len(r.chr),0x20000)
            self.assertEqual(m['rom_sha256'],hashlib.sha256((p/'fixture.nes').read_bytes()).hexdigest())
            self.assertNotEqual(r.prg[-6:-4],r.prg[-2:]);self.assertFalse(any(r.chr[127*1024:]))
            self.assertTrue(any(r.chr[:8192]));self.assertFalse(any(r.chr[8192:]))
    def test_fine_y_cases_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            hashes=[create(Path(d)/str(y),y)['rom_sha256'] for y in (0,1,7,8,63,178,239)]
            self.assertEqual(len(set(hashes)),7)
    def test_no_copyrighted_input_dependency(self):
        with tempfile.TemporaryDirectory() as d:
            a=create(Path(d)/'a');b=create(Path(d)/'b');self.assertEqual(a['rom_sha256'],b['rom_sha256'])
            self.assertEqual(len((Path(d)/'a/rgb-palette.bin').read_bytes()),192)
