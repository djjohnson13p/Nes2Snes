"""Whole-routine recognition, fallback planning and frame-tag boundary tests."""
import ctypes as C
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import native_controller as nc
from controller_fixture import create
from rom import Rom
from replay_native import TaggedRunner

class NativeControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.meta=create(self.path,indices=[0,1,2])
        self.prg=Rom.read(self.path/'fixture.nes').prg
        self.counts=list(struct.unpack('<262144I',(self.path/'counts.u32').read_bytes()))
        self.sites,self.source=nc.plan(self.prg,self.counts)
        self.offset=0x3e000+self.sites[0]['original_target']-0xe000
    def tearDown(self):self.tmp.cleanup()
    def test_matches_complete_body(self):
        self.assertTrue(nc.matches(self.prg,self.counts,self.offset));self.assertEqual(len(self.sites),3)
    def test_no_fixed_game_addresses(self):
        self.assertNotIn('E2B1',self.source)
    def test_rejects_modified_opcode(self):
        data=bytearray(self.prg);data[self.offset]=0xEA
        self.assertFalse(nc.matches(data,self.counts,self.offset))
    def test_rejects_modified_scratch_operand(self):
        data=bytearray(self.prg);data[self.offset+15]=0x06
        self.assertFalse(nc.matches(data,self.counts,self.offset))
    def test_rejects_modified_loop_branch(self):
        data=bytearray(self.prg)
        # Final BNE relative byte directly precedes RTS.
        from opcodes6502 import OPS
        end=self.offset
        for _ in nc.PATTERN:end+=OPS[data[end]][2]
        data[end-2]^=1
        self.assertFalse(nc.matches(data,self.counts,self.offset))
    def test_requires_every_instruction_classified(self):
        counts=self.counts.copy();counts[self.offset+2]=0
        self.assertFalse(nc.matches(self.prg,counts,self.offset))
    def test_rejects_overlapping_entry(self):
        counts=self.counts.copy();counts[self.offset+1]=1
        self.assertFalse(nc.matches(self.prg,counts,self.offset))
    def test_rejects_bad_trace_size(self):
        with self.assertRaises(ValueError):nc.plan(self.prg,[])
    def test_rejects_nonfixed_bank(self):
        data=bytearray(self.prg)
        for site in self.sites:
            i=site['prg_offset'];data[i+1:i+3]=b'\x00\x80'
        self.assertEqual(nc.plan(bytes(data),self.counts)[0],[])
    def test_wrapper_guards_runtime_and_scratch_aliases(self):
        for needle in ('lda RUNNING','cmp #$01','cpx #$03','@fallback:','jmp $'):
            self.assertIn(needle,self.source)
    def test_replacement_only_changes_call_operands(self):
        label=self.sites[0]['label'];result=nc.apply(self.prg,self.sites,{label:0x1400})
        changed={i for i,(a,b) in enumerate(zip(self.prg,result)) if a!=b}
        allowed={i for site in self.sites for i in (site['prg_offset']+1,site['prg_offset']+2)}
        self.assertLessEqual(changed,allowed)
        self.assertEqual(result[self.offset:self.offset+37],self.prg[self.offset:self.offset+37])
    def test_rejects_bad_wrapper_range(self):
        for address in (0xfff,0x1800,0x801000):
            with self.assertRaises(ValueError):nc.apply(self.prg,self.sites,{self.sites[0]['label']:address})
    def test_rejects_already_modified_call(self):
        data=bytearray(self.prg);data[self.sites[0]['prg_offset']]=0xea
        with self.assertRaises(ValueError):nc.apply(data,self.sites,{self.sites[0]['label']:0x1400})
    def test_guarded_fallback_fixture(self):
        m=create(self.path,indices=[3,4,5,255]);self.assertEqual(m['expected_native_calls'],0)
    def test_c0_and_main_loop_fixture_no_native_calls(self):
        self.assertEqual(create(self.path,c0=True)['expected_native_calls'],0)
        self.assertEqual(create(self.path,outside_nmi=True)['expected_native_calls'],0)
    def test_fixture_bounds(self):
        for indices in ([],[-1],[256],[0]*29,[0x6f],[0x70],[0x7d],[0x7e],[0x5f],[0x60]):
            with self.assertRaises(ValueError):create(self.path,indices=indices)
    def test_bit_reversal_matches_eight_serial_shifts(self):
        for bits in range(256):
            result=0;shift=bits
            for _ in range(8):result=((result<<1)|(shift&1))&255;shift=(shift>>1)|128
            self.assertEqual(result,int(f'{bits:08b}'[::-1],2));self.assertEqual(shift,255)

class FrameTagTests(unittest.TestCase):
    def runner(self):
        r=TaggedRunner.__new__(TaggedRunner);r.render_tag=None;r.frames=0;r.errors=[]
        r.frame=None;ram=C.create_string_buffer(0x20000)
        class Lib:
            def retro_get_memory_size(self,kind):return len(ram)
            def retro_get_memory_data(self,kind):return C.addressof(ram)
        r.lib=Lib();return r,ram
    def test_callback_captures_id_before_later_runtime_changes(self):
        r,ram=self.runner();C.memmove(C.addressof(ram)+0x974,b'\x34\x12',2)
        pixels=C.create_string_buffer(b'\0\0');r.video(C.addressof(pixels),1,1,2)
        C.memmove(C.addressof(ram)+0x974,b'\x35\x12',2)
        self.assertEqual(r.render_tag,0x1234);self.assertEqual(r.frames,1)
    def test_duplicate_callback_does_not_retag_old_pixels(self):
        r,ram=self.runner();r.render_tag=42;r.video(None,1,1,2)
        self.assertEqual(r.render_tag,42)
    def test_missing_snes_ram_is_reported(self):
        r,ram=self.runner();r.lib.retro_get_memory_size=lambda kind:2048
        pixels=C.create_string_buffer(b'\0\0');r.video(C.addressof(pixels),1,1,2)
        self.assertTrue(r.errors)

if __name__=='__main__':unittest.main()
