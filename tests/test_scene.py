from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_scene import sprite_oam


def fixture(y=20,tile=0,attr=0,x=30):
    return bytes((y,tile,attr,x))+bytes((240,0,0,0))*63


class SceneTests(unittest.TestCase):
    def test_hidden_and_size(self):
        result=sprite_oam(bytes((240,0,0,0))*64,0x20)
        self.assertEqual(len(result),544)
        self.assertEqual(result[:512],bytes((0,240,0,0))*128)
        self.assertEqual(result[512:],bytes(32))
    def test_8x8_second_pattern_table(self):
        result=sprite_oam(fixture(tile=42),0x08)
        self.assertEqual(result[:4],bytes((30,13,42,0x31)))
        self.assertEqual(result[4:8],bytes((0,240,0,0)))
    def test_8x16_table_bit(self):
        result=sprite_oam(fixture(tile=5),0x20)
        self.assertEqual(result[:8],bytes((30,13,4,0x31,30,21,5,0x31)))
    def test_vertical_flip_swaps_halves(self):
        result=sprite_oam(fixture(tile=5,attr=0x80),0x20)
        self.assertEqual(result[:8],bytes((30,13,5,0xB1,30,21,4,0xB1)))
    def test_horizontal_flip(self):
        result=sprite_oam(fixture(attr=0x40),0x20)
        self.assertEqual(result[3],0x70);self.assertEqual(result[7],0x70)
    def test_palette_and_behind_background(self):
        result=sprite_oam(fixture(attr=0x23),0x20)
        self.assertEqual(result[3],0x16)
    def test_all_64_tall_objects(self):
        raw=bytes((20,5,0,30))*64
        result=sprite_oam(raw,0x20)
        self.assertEqual(len(result),544);self.assertEqual(result[508:512],bytes((30,21,5,0x31)))
        self.assertEqual(raw,bytes((20,5,0,30))*64)
    def test_invalid_length(self):
        with self.assertRaises(ValueError):sprite_oam(bytes(255),0x20)

if __name__=='__main__':unittest.main()
