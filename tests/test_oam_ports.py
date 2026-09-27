"""OAM profile isolation, publication-ready rejection tests and real assembly."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import palette_timeline
from native_fixture import Program
from oam_ports import validate, underlying, create_native, create_nes, boot_code, port_code, PROFILE
from oam_ports_fixture import cases, address_case, interleave_case, guard_cases, seal
from verify_oam_ports import initial, compare_oam, compare, ENDPOINT_BYTES, run
from verify_palette_timeline import native_sample


class OamProfileTests(unittest.TestCase):
    def test_profile_is_explicit(self):
        p=address_case(2,255)
        self.assertIs(validate(p),p)
        self.assertEqual(underlying(p)['memory_model'],palette_timeline.PROFILE)
        with self.assertRaises(ValueError):validate(underlying(p))

    def test_requests_and_unknown_fields_are_not_admitted(self):
        p=address_case(2,255)
        for changed in (dict(p,unknown=True),dict(p,events=[dict(cycle=1,irq=True,nmi=False)])):
            with self.assertRaises(ValueError):validate(changed)

    def test_unsafe_name_rejected(self):
        with self.assertRaises(ValueError):validate(dict(address_case(2,255),name='../escape'))

    def test_every_address_and_attribute_value_occurs(self):
        rows=cases();self.assertEqual(len(rows),514)
        self.assertEqual(len({p['name'] for p in rows}),len(rows))
        names=[p['name'].split('-') for p in rows if p['name'].startswith('oam-address-')]
        self.assertEqual({int(n[2],16) for n in names},set(range(256)))
        self.assertEqual({int(n[3],16) for n in names if int(n[2],16)==2},set(range(256)))

    def test_boot_bound_for_all_four_chr_modes(self):
        for mode in range(4):self.assertLessEqual(len(boot_code(mode)),512)

    def test_invalid_ports_or_opcodes_refused(self):
        for args in ((0xAE,4),(0xAD,2),(0x8D,7)):
            with self.assertRaises(ValueError):port_code(*args)

    def test_address_read_is_latch_read(self):
        self.assertIn('PpuLatchRead',port_code(0xAD,3))
        self.assertIn('OamDataRead',port_code(0xAD,4))

    def test_actual_assembly_relocates_chr_scratch_and_preserves_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);p=interleave_case('chr')
            rom=create_native(d,p,initial(p),host_mode='nested')
            self.assertTrue(rom.is_file())
            code=(d/'program.inc').read_text()
            self.assertNotIn('CR+11',code)
            self.assertIn('OamDataWrite',code)
            self.assertIn('sta MR_VALUE',code)
            self.assertIn('cpx #60\n    bne save_capture',(d/'timeline_host_nmi.inc').read_text())
            self.assertEqual((d/'original-prg.bin').read_bytes(),create_nes(d/'reference',p).read_bytes()[16:16+p['prg_banks']*8192])

    def test_injected_initial_state_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            p=address_case(2,255);wrong=bytearray(initial(p));wrong[-1]^=1
            with self.assertRaises(ValueError):create_native(Path(folder),p,bytes(wrong))

    def test_dma_remains_a_translation_refusal(self):
        p=Program(0xE100);p.op('STA','abs',0x4014)
        with self.assertRaises(ValueError):seal(p,'oam-dma-refused')

    def test_old_profile_does_not_inherit_oam(self):
        with tempfile.TemporaryDirectory() as folder:
            p=underlying(address_case(2,255));d=Path(folder)
            palette_timeline.create_native(d,p,initial(dict(p,memory_model=PROFILE)))
            self.assertIn('jmp PpuUnsupported',(d/'program.inc').read_text())
            self.assertNotIn('oam_ports.inc',(d/'fixture.s').read_text())

    def test_all_guards_are_independently_valid_plans(self):
        rows=guard_cases();self.assertEqual(len(rows),4)
        for p,pc,count in rows:
            self.assertIs(validate(p),p);self.assertIn(pc,p['starts']);self.assertGreater(count,0)

    def test_output_directory_reuse_restores_old_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);p=address_case(2,255)
            create_native(d,p,initial(p))
            old=underlying(p)
            a=palette_timeline.create_native(d,old,initial(p)).read_bytes()
            b=palette_timeline.create_native(d/'fresh',old,initial(p)).read_bytes()
            self.assertEqual(a,b)

    def test_no_production_reference(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('tools/build_native.py','snes/src/native.s'):
            self.assertNotIn('oam_ports',(root/name).read_text())


class OamComparisonTests(unittest.TestCase):
    def samples(self):
        ref=dict(oam=bytes(256).hex(),oam_address='02')
        row=bytearray(16);row[13]=2
        actual=dict(ref,completed_steps=1,ppu_records=[row.hex()])
        return ref,actual

    def test_matching_raw_bytes(self):
        compare_oam(*self.samples());self.assertEqual(ENDPOINT_BYTES,5430)

    def test_changed_oam_byte_rejected(self):
        r,a=self.samples();b=bytearray(256);b[255]=1;a['oam']=b.hex()
        with self.assertRaises(RuntimeError):compare_oam(r,a)

    def test_agreeing_but_impossible_attribute_bits_rejected(self):
        r,a=self.samples();b=bytearray(256);b[2]=0x1C;r['oam']=a['oam']=b.hex()
        with self.assertRaises(ValueError):compare_oam(r,a)

    def test_retired_address_must_match_live(self):
        r,a=self.samples();a['ppu_records']=[bytes(16).hex()]
        with self.assertRaises(ValueError):compare_oam(r,a)

    def test_incomplete_and_whitespace_shortened_bytes_rejected(self):
        for key,value in [('oam',None),('oam',bytes(255).hex()+'  '),('oam_address',''),('completed_steps',True)]:
            r,a=self.samples();a[key]=value
            with self.assertRaises((ValueError,RuntimeError)):compare_oam(r,a)

    def test_limited_matrix_validation_before_any_execution(self):
        for limit in (0,True,515):
            with self.assertRaises(ValueError):run(Path('unused'),Path('unused'),Path('unused'),limit=limit)


class SnapshotHookTests(unittest.TestCase):
    def test_bad_extra_range_refused_before_loading_a_core(self):
        for ranges in ([],{'x':(True,1)},{'x':(-1,1)},{'x':(0,0)},{'x':(131072,1)},{'x':(0,1,2)}):
            with self.assertRaises(ValueError):native_sample(None,None,None,31,False,extra_ranges=ranges)

    def exercise(self,extra):
        class FakeRunner:
            def __init__(self,*args):
                self.ram=bytearray(131072);self.ram[0x1FFF]=0x5A;self.ram[0x5900]=0x73
            def run(self,n):pass
            def memory(self):return bytes(self.ram)
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);core=d/'core';core.write_bytes(b'authored test placeholder')
            with patch('verify_palette_timeline.Runner',FakeRunner):
                native_sample(core,core,d/'output.json',31,False,extra_ranges=extra)
            return json.loads((d/'output.json').read_text())

    def test_default_output_unchanged_and_extra_read_is_exact(self):
        default=self.exercise(None);extra=self.exercise({'oam':(0x5900,256)})
        self.assertEqual(bytes.fromhex(extra.pop('oam')),bytes([0x73])+bytes(255))
        self.assertEqual(extra,default)

    def test_existing_key_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):self.exercise({'status':(0,1)})
