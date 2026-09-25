"""Source-only unit tests for explicit veneers and the original SPC program."""
import json,struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import direct_calls as d
from audio_program import program,brr_wave,pitch,write_assets,ENTRY,DIRECTORY,SAMPLES
from direct_fixture import create
class DirectTests(unittest.TestCase):
    def test_writes_all_registers(self):
        for op in (0x8D,0x8E,0x8C):
            for addr in range(0x2000,0x4000):self.assertEqual(d.handler_kind(op,addr),('write',addr&7))
    def test_live_bank_selectors_excluded(self):
        for op in (0x8D,0x8E,0x8C):
            for addr in (0x5115,0x5116,0x5117):self.assertIsNone(d.handler_kind(op,addr))
    def test_unknowns_not_rewritten(self):
        for op,addr in ((0xAE,0x2002),(0xAD,0x2007),(0x8D,0x4017),(0xEE,0x2000),(0x8D,0x5205)):
            self.assertIsNone(d.handler_kind(op,addr))
    def test_status_alias(self):self.assertEqual(d.handler_kind(0xAD,0x3ffa),('read',0))
    def test_same_width_replacement(self):
        sites,source=d.plan(bytes([0x8D,0,0x20]),[dict(prg_offset=0,mode='abs')])
        self.assertIn('DirectWriteA',source)
        self.assertEqual(d.apply(b'\x02\x8D\x20',sites,{sites[0]['label']:0x1000}),b'\x20\x00\x10')
    def test_bad_veneer_range(self):
        sites,_=d.plan(b'\x8D\x00\x20',[dict(prg_offset=0,mode='abs')])
        for address in (0xfff,0x1800,0x801000):
            with self.assertRaises(ValueError):d.apply(b'\x02\x8D\x20',sites,{sites[0]['label']:address})
    def test_non_code_rejected(self):
        sites,_=d.plan(b'\x8D\x00\x20',[dict(prg_offset=0,mode='abs')])
        with self.assertRaises(ValueError):d.apply(b'\x8D\x00\x20',sites,{sites[0]['label']:0x1000})
    def test_fixture_covers_all_banks_and_stores(self):
        with tempfile.TemporaryDirectory() as td:
            meta=create(Path(td));self.assertEqual(len(meta['records']),192)
            self.assertEqual(sum(x['name'].startswith('bank15_7_') for x in meta['records']),6)
class AudioTests(unittest.TestCase):
    def test_program_deterministic(self):self.assertEqual(program(),program())
    def test_sample_directory(self):
        data=program()
        for i in range(5):
            start,loop=struct.unpack_from('<HH',data,DIRECTORY-ENTRY+4*i)
            self.assertEqual(start,SAMPLES+18*i);self.assertEqual(start,loop)
            self.assertEqual(data[start-ENTRY],0xA0);self.assertEqual(data[start-ENTRY+9],0xA3)
    def test_brr_validation(self):
        for samples in ([0]*31,[0]*33,[8]*32,[-9]*32):
            with self.assertRaises(ValueError):brr_wave(samples)
    def test_pitch_11bit_range(self):
        for timer in (-1,2048):
            with self.assertRaises(ValueError):pitch(timer)
    def test_pitch_monotonic(self):
        for triangle in (False,True):
            values=[pitch(i,triangle) for i in range(2048)]
            self.assertEqual(values,sorted(values,reverse=True));self.assertLessEqual(max(values),0x3fff)
    def test_assets_have_full_tables(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td);meta=write_assets(path)
            self.assertEqual(len((path/'pulse-pitch.bin').read_bytes()),4096)
            self.assertEqual(len((path/'triangle-pitch.bin').read_bytes()),4096)
            self.assertEqual(meta['program_bytes'],len(program()))
    def test_expected_a_note(self):self.assertAlmostEqual(pitch(253)*32000/(4096*32),440,delta=1)
if __name__=='__main__':unittest.main()
