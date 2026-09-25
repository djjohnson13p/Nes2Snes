"""Independent encoding examples and deterministic source-only regression input."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_object_cache import expected_objects
from ppu_fixture import create as create_ppu
from video_fixture import create as create_video
from replay_native import inputs,SAMPLES
from rom import Rom

class VideoPathTests(unittest.TestCase):
    def sprite(self,y,tile,attr,x,ctrl):
        source=bytes([y,tile,attr,x])+bytes([255,0,0,0])*63
        return expected_objects(source,ctrl)
    def test_hidden_threshold(self):
        for y in (239,240,255):
            self.assertEqual(self.sprite(y,255,255,255,32),bytes([0,240,0,0])*128)
    def test_size(self):
        self.assertEqual(len(self.sprite(7,0,0,0,0)),512)
    def test_bad_oam_sizes(self):
        for n in (0,255,257):
            with self.assertRaises(ValueError):expected_objects(bytes(n),0)
    def test_small_sprite_and_hidden_partner(self):
        self.assertEqual(self.sprite(20,65,0,100,0)[:8],bytes([100,13,65,0x30,0,240,0,0]))
    def test_small_sprite_flags_and_pattern_bank(self):
        self.assertEqual(self.sprite(20,65,0xe3,100,8)[:4],bytes([100,13,65,0xd7]))
    def test_large_odd_tile_selects_bank(self):
        self.assertEqual(self.sprite(7,7,0,20,32)[:8],bytes([20,0,6,0x31,20,8,7,0x31]))
    def test_large_vertical_flip_reverses_tile_pair(self):
        self.assertEqual(self.sprite(7,7,0x80,20,32)[:8],bytes([20,0,7,0xb1,20,8,6,0xb1]))
    def test_y_coordinate_wrap(self):
        self.assertEqual(self.sprite(1,0,0,0,32)[:8],bytes([0,250,0,0x30,0,2,1,0x30]))
    def test_replay_length_and_bounds(self):
        data=inputs()
        self.assertEqual(len(data),4096)
        self.assertEqual(data[122:124],bytes([8,8]))
        self.assertEqual(data[917:1037],bytes([128])*120)
        self.assertEqual(data[1037:1062],bytes([129])*25)
        self.assertEqual(data[1062:1087],bytes([2])*25)
        self.assertFalse(any(data[1087:]))
        self.assertEqual(len(SAMPLES),5)
    def test_replay_reproducibility(self):
        self.assertEqual(inputs(),inputs())
    def test_ppu_fixture_reproducibility_and_records(self):
        with tempfile.TemporaryDirectory() as directory:
            a=Path(directory)/'a';b=Path(directory)/'b'
            meta=create_ppu(a,5);create_ppu(b,5)
            self.assertEqual((a/'fixture.nes').read_bytes(),(b/'fixture.nes').read_bytes())
            self.assertEqual(len(meta['records']),47)
            self.assertTrue(meta['procedural_fixture'])
            self.assertEqual(Rom.read(a/'fixture.nes').mapper,5)
    def test_ppu_fixture_seed_changes_input(self):
        with tempfile.TemporaryDirectory() as directory:
            a=Path(directory)/'a';b=Path(directory)/'b'
            self.assertNotEqual(create_ppu(a,0)['rom_sha256'],create_ppu(b,1)['rom_sha256'])
    def test_video_fixture_has_explicit_nmi_and_no_fake_cpu_records(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);meta=create_video(p)
            self.assertTrue(meta['animated_oam_fixture'])
            self.assertEqual(meta['records'],[])
            self.assertEqual(meta['rom_sha256'],hashlib.sha256((p/'fixture.nes').read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
