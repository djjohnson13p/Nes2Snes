"""Explicit ROM profile boundaries; old profiles remain unchanged."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from timeline_program import validate_plan,decode,create_native,memory_bytes
from timeline_fixture import expected_initial,create_nes,cases as original_cases
from rom_timeline_fixture import cases,read_case,jump_case,fault_cases
from timeline_rom import validate_data,jump
from timeline_ram import WRITES
from opcodes6502 import OPS


class ROMTimelineTests(unittest.TestCase):
    def plan(self):return read_case(0xBD,1)

    def test_explicit_profile_and_complete_ram_abi(self):
        p=self.plan();self.assertEqual(memory_bytes(p),2048)
        self.assertEqual(len(expected_initial(p)),2080)
        self.assertIs(validate_plan(p),p)

    def test_omitted_profile_still_rejects_rom_data(self):
        p=original_cases()[0];p['rom_data']=[]
        with self.assertRaises(ValueError):validate_plan(p)

    def test_absolute_rom_reads_require_rom_gate(self):
        p=read_case(0xAD,1);code=bytes.fromhex(p['code'])
        with self.assertRaises(ValueError):decode(code,p['origin'],p['starts'],ram=True)
        self.assertTrue(decode(code,p['origin'],p['starts'],ram=True,rom=True))

    def test_rom_gate_requires_ram_gate_and_boolean(self):
        for kw in ({'rom':True},{'ram':True,'rom':1}):
            with self.assertRaises(ValueError):decode(b'\xea',0x8000,[0x8000],**kw)

    def test_missing_or_wrong_data_list_rejected(self):
        for patches in (None,{},True):
            p=self.plan();p['rom_data']=patches
            with self.assertRaises(ValueError):validate_plan(p)

    def test_invalid_data_address_types_and_ranges(self):
        for address in (True,-1,0x7FFF,0xFFFA,65536):
            p=self.plan();p['rom_data']=[dict(address=address,bytes='aa')]
            with self.assertRaises(ValueError):validate_plan(p)

    def test_invalid_encoding_and_empty_data_rejected(self):
        for text in ('','  ','zz','abc',None,'aa'*4097):
            p=self.plan();p['rom_data']=[dict(address=0x9000,bytes=text)]
            with self.assertRaises(ValueError):validate_plan(p)

    def test_unknown_fields_and_overlapping_patches_rejected(self):
        for patches in ([dict(address=0x9000,bytes='aa',extra=1)],
                        [dict(address=0x9000,bytes='aabb'),dict(address=0x9001,bytes='cc')]):
            p=self.plan();p['rom_data']=patches
            with self.assertRaises(ValueError):validate_plan(p)

    def test_code_boot_and_vector_overlaps_rejected(self):
        for address,text in ((0x80C0,'aa'),(0xDFFF,'aaaa'),(0xE080,'aa'),(0xFFF9,'aaaa')):
            p=self.plan();p['rom_data']=[dict(address=address,bytes=text)]
            with self.assertRaises(ValueError):validate_plan(p)

    def test_total_data_budget_rejected(self):
        p=self.plan();p['rom_data']=[dict(address=0x9000,bytes='aa'*4096),dict(address=0xB000,bytes='aa')]
        with self.assertRaises(ValueError):validate_plan(p)

    def test_unsafe_profile_and_fixture_names_rejected(self):
        for key,value in (('memory_model','unknown'),('name','../escape')):
            p=self.plan();p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)

    def test_indirect_rom_jump_uses_nmos_page_wrap(self):
        text=jump(0x92FF)
        self.assertIn('#$92FF',text);self.assertIn('#$9200',text);self.assertNotIn('#$9300',text)
        for addr in (True,0x2000,0x7FFF,-1,65536):
            with self.assertRaises(ValueError):jump(addr)

    def test_actual_assembled_raw_cartridge_bank_matches_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.plan()
            original=create_nes(root/'nes',p).read_bytes()[16:32784]
            native=create_native(root/'snes',p,expected_initial(p)).read_bytes()
            self.assertEqual(native[32768:65536],original)
            self.assertNotEqual(native[:32768],original)
            self.assertEqual(native[32768+p['origin']-0x8000],bytes.fromhex(p['code'])[0])

    def test_all_declared_read_opcodes_are_covered(self):
        rows=cases();covered={int(p['name'].split('-')[1],16) for p in rows if 'jmp' not in p['name']}
        from timeline_program import REGULAR
        expected={op for op,(n,m,_) in OPS.items() if n in REGULAR and n not in WRITES and m in {'abs','absx','absy','ix','iy'}}
        self.assertEqual(covered,expected);self.assertEqual(len({p['name'] for p in rows}),len(rows))

    def test_guards_are_valid_plans_not_silently_removed(self):
        self.assertEqual(len(fault_cases()),5)
        for p in fault_cases():self.assertIs(validate_plan(p),p)

    def test_production_runtime_does_not_include_prototype(self):
        root=Path(__file__).resolve().parents[1]
        self.assertNotIn('timeline_rom',(root/'snes/src/native.s').read_text())
        self.assertNotIn('nrom-32k',(root/'tools/build_native.py').read_text())

if __name__=='__main__':unittest.main()
