import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from rom import Rom,nes2_size
from graphics import nes_to_snes,snes_to_nes,decode_nes_tile,encode_nes_tile,synthetic_chr,nametable_to_snes
from build_viewer import finalize_rom,validate_sfc
from opcodes6502 import OPS,format_instruction


def fixture(*,nes2=False,trainer=False,prg=1,chr_banks=1,mapper=0,extra=b''):
    h=bytearray(b'NES\x1a'+bytes(12));h[4]=prg;h[5]=chr_banks
    h[6]=((mapper&15)<<4)|(4 if trainer else 0)
    h[7]=(mapper&240)|(8 if nes2 else 0)
    return bytes(h)+(bytes(512) if trainer else b'')+bytes(prg*16384)+bytes(chr_banks*8192)+extra


class RomTests(unittest.TestCase):
    def test_ines_layout(self):
        r=Rom.parse(fixture());self.assertFalse(r.nes2);self.assertEqual(len(r.prg),16384);self.assertEqual(len(r.chr),8192)
    def test_nes2(self):
        r=Rom.parse(fixture(nes2=True,mapper=5));self.assertTrue(r.nes2);self.assertEqual(r.mapper,5)
    def test_trainer(self):
        r=Rom.parse(fixture(trainer=True));self.assertEqual(r.prg_offset,528);self.assertEqual(len(r.trainer),512)
    def test_chr_ram(self):
        r=Rom.parse(fixture(chr_banks=0));self.assertEqual(r.chr,b'');self.assertTrue(r.metadata()['warnings'])
    def test_bad_magic(self):
        with self.assertRaises(ValueError):Rom.parse(b'bad!'+bytes(40000))
    def test_short_header(self):
        with self.assertRaises(ValueError):Rom.parse(b'NES\x1a')
    def test_truncated(self):
        with self.assertRaises(ValueError):Rom.parse(fixture()[:-1])
    def test_zero_prg(self):
        with self.assertRaises(ValueError):Rom.parse(fixture(prg=0))
    def test_trailing(self):
        r=Rom.parse(fixture(extra=b'TAIL'));self.assertEqual(r.trailing,b'TAIL')
    def test_unrecognized_header(self):
        raw=bytearray(fixture());raw[7]=4
        with self.assertRaises(ValueError):Rom.parse(bytes(raw))
    def test_nes2_extended_mapper(self):
        raw=bytearray(fixture(nes2=True,mapper=0x35));raw[8]=0xA2
        r=Rom.parse(bytes(raw));self.assertEqual(r.mapper,0x235);self.assertEqual(r.submapper,10)
    def test_exponent_size(self):
        self.assertEqual(nes2_size(14<<2,15,16384),16384)
        self.assertEqual(nes2_size((12<<2)|1,15,8192),12288)
    def test_nes2_ram_sizes(self):
        raw=bytearray(fixture(nes2=True));raw[10]=0x87;raw[11]=0x06
        m=Rom.parse(bytes(raw)).metadata();self.assertEqual(m['prg_ram_bytes'],8192);self.assertEqual(m['prg_nvram_bytes'],16384);self.assertEqual(m['chr_ram_bytes'],4096)
    def test_vectors(self):
        raw=bytearray(fixture(mapper=5));struct.pack_into('<HHH',raw,16+16384-6,0xE053,0xE00B,0xE11A)
        self.assertEqual(Rom.parse(bytes(raw)).metadata()['prg_tail_vector_words']['reset'],'$E00B')
    def test_input_unchanged(self):
        raw=fixture(nes2=True);old=bytes(raw);Rom.parse(raw).metadata();self.assertEqual(raw,old)


class GraphicsTests(unittest.TestCase):
    def test_plane_interleave(self):
        raw=bytes(range(16));self.assertEqual(nes_to_snes(raw),bytes(x for y in range(8) for x in (y,y+8)))
    def test_four_bpp_padding(self):
        self.assertEqual(nes_to_snes(bytes(range(16)),4)[16:],bytes(16))
    def test_random_roundtrip(self):
        raw=random.Random(42).randbytes(16*1024)
        for bpp in (2,4):self.assertEqual(snes_to_nes(nes_to_snes(raw,bpp),bpp),raw)
    def test_decode_orientation(self):
        tile=bytes([0x80]+[0]*7+[1]+[0]*7);pixels=decode_nes_tile(tile)
        self.assertEqual(pixels[0][0],1);self.assertEqual(pixels[0][7],2);self.assertEqual(pixels[7][0],0)
    def test_encode_roundtrip(self):
        raw=bytes(range(16));self.assertEqual(encode_nes_tile(decode_nes_tile(raw)),raw)
    def test_partial_tile(self):
        with self.assertRaises(ValueError):nes_to_snes(bytes(15))
    def test_invalid_bpp(self):
        with self.assertRaises(ValueError):nes_to_snes(bytes(16),8)
    def test_refuse_lossy(self):
        with self.assertRaises(ValueError):snes_to_nes(bytes(31)+b'\x01',4)
    def test_synthetic(self):
        self.assertEqual(len(synthetic_chr(4)),16384)
    def test_attributes(self):
        n=bytearray(1024);n[960]=0b11100100
        words=struct.unpack('<1024H',nametable_to_snes(bytes(n)))
        for x,y,palette in [(0,0,0),(2,0,1),(0,2,2),(2,2,3)]:
            self.assertEqual(words[y*32+x]>>10,palette)
        self.assertEqual(words[30*32:],(0,)*64)
    def test_invalid_nametable(self):
        with self.assertRaises(ValueError):nametable_to_snes(bytes(960))
    def test_tile_offset(self):
        n=bytearray(1024);n[0]=7
        self.assertEqual(struct.unpack_from('<H',nametable_to_snes(bytes(n),256,2,True))[0],263|(2<<10)|0x2000)
    def test_invalid_pixel(self):
        with self.assertRaises(ValueError):encode_nes_tile([[4]*8 for _ in range(8)])


class SnesTests(unittest.TestCase):
    def core(self):
        b=bytearray(32768);b[0x7FD5]=0x20;struct.pack_into('<H',b,0x7FFC,0x8000);return bytes(b)
    def test_checksum(self):
        r=finalize_rom(self.core(),bytes(32768));self.assertEqual(validate_sfc(r)['bytes'],65536)
    def test_power_two_padding(self):
        r=finalize_rom(self.core(),bytes(131072));self.assertEqual(len(r),262144);validate_sfc(r)
    def test_corruption_detected(self):
        r=bytearray(finalize_rom(self.core(),bytes(32768)));r[5]^=1
        with self.assertRaises(ValueError):validate_sfc(bytes(r))
    def test_header_size(self):
        with self.assertRaises(ValueError):finalize_rom(bytes(100),bytes(4096))
    def test_opcode_count(self):
        self.assertEqual(len(OPS),151);self.assertEqual(OPS[0xDE],('DEC','absx',3))
    def test_hardware_label(self):self.assertEqual(format_instruction(bytes.fromhex('8d0620'),0xE000),'sta PPUADDR')
    def test_branch_wrap(self):self.assertEqual(format_instruction(bytes.fromhex('d0fc'),0x0000),'bne $FFFE')

if __name__=='__main__':unittest.main()
