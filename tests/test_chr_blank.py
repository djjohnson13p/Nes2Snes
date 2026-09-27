"""CHR profile boundaries, actual assembly and strict comparison checks."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from chr_blank_fixture import cases,read_case,seal
from mmc5_chr_blank import validate,create_native,create_nes,chr_image,boot_code,register_code
from timeline_fixture import expected_initial
from verify_chr_blank import packed_registers,check_chr
from instrument_chr_blank import fetch_snapshots


class CHRTests(unittest.TestCase):
    def plan(self):return read_case(3,0,0x31,32)

    def test_sizes_and_modes_are_explicit(self):
        for bank in (8,16,32,64,128,256,512,1024):
            for mode in range(4):self.assertEqual(len(chr_image(bank)),bank*1024);validate(read_case(mode,0,1,bank))

    def test_bad_sizes_modes_types_and_fields(self):
        for key,value in (('chr_banks',True),('chr_banks',0),('chr_banks',7),('chr_banks',24),('chr_banks',2048),('chr_mode',False),('chr_mode',-1),('chr_mode',4),('extra',1)):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate(dict(self.plan(),**{key:value}))

    def test_missing_options_not_silently_defaulted(self):
        for key in ('chr_banks','chr_mode'):
            p=self.plan();del p[key]
            with self.assertRaises(ValueError):validate(p)

    def test_other_profiles_do_not_admit_chr_options(self):
        p=self.plan();p['memory_model']='mmc5-ppu-blank'
        from timeline_program import validate_plan
        with self.assertRaises(ValueError):validate_plan(p)

    def test_static_mode_and_set_b_are_runtime_guards(self):
        self.assertIn('ChrModeWrite',register_code(0x5101))
        for a in range(0x5128,0x512C):self.assertIn('PpuUnsupported',register_code(a))
        with self.assertRaises(ValueError):register_code(0x5200)

    def test_fixture_covers_all_set_a_slots_and_sizes(self):
        plans=cases();self.assertEqual(len({p['name'] for p in plans}),len(plans))
        self.assertEqual({p['chr_banks'] for p in plans},{8,16,32,64,128,256,512,1024})
        self.assertEqual({p['chr_mode'] for p in plans},set(range(4)))
        for m in range(4):
            self.assertTrue(all(any(f'chr-m{m}-s{s}-' in p['name'] for p in plans) for s in range(8)))

    def test_boot_stays_in_reserved_region(self):
        for mode in range(4):self.assertLessEqual(len(boot_code(mode)),512)

    def test_real_native_build_has_exact_original_chr(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.plan();root=Path(d)
            nes=create_nes(root/'nes',p).read_bytes();sfc=create_native(root/'native',p,expected_initial(p)).read_bytes()
            offset=p['prg_banks']*8192
            self.assertEqual(nes[16+offset:],chr_image(32))
            self.assertEqual(sfc[32768+offset:32768+offset+32768],chr_image(32))
            self.assertEqual(nes[5],4)

    def test_real_host_build_preserves_existing_stack_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.plan();create_native(root,p,expected_initial(p),host_mode='nested')
            self.assertIn('cpx #60\n    bne save_capture',(root/'timeline_host_nmi.inc').read_text())
            self.assertIn('ldx #58\nrestore_capture:',(root/'timeline_host_nmi.inc').read_text())
            self.assertIn('cpx #60\n    bne poison_capture',(root/'fixture.s').read_text())
        from verify_host_nmi import check_host
        import inspect
        self.assertIn('0x1E90',inspect.getsource(check_host))

    def test_prior_profile_reusing_directory_drops_stale_chr(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.plan();create_native(root/'reuse',p,expected_initial(p))
            from ppu_blank_fixture import buffer_case
            from mmc5_ppu_blank import create_native as old
            p=buffer_case();a=old(root/'reuse',p,expected_initial(p)).read_bytes();b=old(root/'fresh',p,expected_initial(p)).read_bytes()
            self.assertEqual(a,b);self.assertFalse((root/'reuse/original-chr.bin').exists())

    def test_production_runtime_stays_isolated(self):
        root=Path(__file__).resolve().parents[1]
        for file in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('mmc5_chr_blank',(root/file).read_text())

    def test_fetch_invalid_counts_rejected_before_core_access(self):
        for count in (True,0,-1,32):
            with self.assertRaises(ValueError):fetch_snapshots(None,count)

    def observations(self):
        p=self.plan();r=bytearray(48);r[0]=3;ref={'chr_records':[r.hex()]*(p['steps']+1)}
        native={'chr_records':[r.hex()]*p['steps'],'chr_registers':bytes(11).hex()}
        return p,ref,native

    def test_comparison_accepts_exact_records(self):
        p,a,n=self.observations();self.assertEqual(check_chr(p,a,n)['chr_state_bytes'],31*48)

    def test_comparison_rejects_missing_changed_and_whitespace_records(self):
        for kind in ('missing','changed','whitespace','wrongfinal'):
            p,a,n=self.observations()
            if kind=='missing':n['chr_records']=n['chr_records'][:-1]
            elif kind=='changed':n['chr_records'][0]='ff'+n['chr_records'][0][2:]
            elif kind=='whitespace':n['chr_records'][0]='  '*48
            else:n['chr_registers']='ff'*11
            with self.subTest(kind=kind),self.assertRaises((ValueError,RuntimeError)):check_chr(p,a,n)

    def test_packed_state_rejects_high_bits_and_padding(self):
        for index,value in ((3,4),(34,1),(47,1)):
            r=bytearray(48);r[index]=value
            with self.assertRaises(ValueError):packed_registers(r.hex())

    def test_bank_selection_is_bound_to_actual_record_range(self):
        p,a,n=self.observations();r=bytearray.fromhex(a['chr_records'][1]);r[18:20]=(p['chr_banks']).to_bytes(2,'little')
        a['chr_records'][1]=n['chr_records'][0]=r.hex()
        with self.assertRaisesRegex(ValueError,'outside'):check_chr(p,a,n)

if __name__=='__main__':unittest.main()
