"""Bank-qualified execution, profile gates and independently inspectable mappings."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mmc5_timeline import slots, INITIAL, validate, fragments, create_native, write_code
from mmc5_timeline_fixture import read_case, execution_case, current_bank_case, fault_cases
from timeline_fixture import expected_initial
from timeline_program import validate_plan, decode
from instrument_mmc5_timeline import instrument, HELPER
from instrument_timeline_probe import BEGIN,END


class MMC5TimelineTests(unittest.TestCase):
    def test_modes_and_ignored_alignment_bits(self):
        self.assertEqual(slots((1,0x83,0x85,0x89,0x8F),32),(4,5,14,15))
        self.assertEqual(slots((2,0x83,0x85,0x89,0x8F),32),(4,5,9,15))
        self.assertEqual(slots((3,0x83,0x85,0x89,0x8F),32),(3,5,9,15))
        self.assertEqual(slots((0xFE,0x83,0x85,0x89,0x0F),32),(4,5,9,15))

    def test_all_byte_values_for_rom_only_final_register(self):
        for v in range(256):
            for mode in (1,2,3):
                row=slots((mode,0x80,0x81,0x82,v),32)
                self.assertEqual(row[3],((v&31)|1) if mode==1 else v&31)

    def test_bank_chip_sizes_and_unimplemented_ram_selection(self):
        for n in (4,8,16,32,64,128):self.assertEqual(slots(INITIAL,n),(0,1,2,n-1))
        self.assertEqual(slots((2,0,3,4,0),32),(255,255,255,0))

    def test_unsupported_mode_zero_not_silently_aliased(self):
        for value in (0,4,128,252):
            with self.assertRaises(ValueError):slots((value,128,129,130,255),32)

    def test_bad_mapper_state_rejected(self):
        for n in (True,0,3,7,129,256):
            with self.assertRaises(ValueError):slots(INITIAL,n)
        for row in ((3,128),(True,128,129,130,255),(3,-1,129,130,255)):
            with self.assertRaises(ValueError):slots(row,32)

    def test_banked_initial_state_has_exact_abi_and_maps(self):
        p=read_case();initial=expected_initial(p)
        self.assertEqual(len(initial),2080);self.assertEqual(initial[20:25],bytes((0,1,2,31,31)))
        self.assertEqual(initial[25:32],bytes(7))

    def test_reject_unknown_plan_fields_and_model(self):
        for key,value in (('extra',0),('memory_model','mmc5'),('steps',True),('prg_banks',7)):
            p=read_case();p[key]=value
            with self.assertRaises(ValueError):validate(p)

    def test_missing_entries_rejected_even_when_bytes_are_valid(self):
        p=read_case();p['starts']=p['starts'][1:]
        with self.assertRaises(ValueError):validate(p)

    def test_duplicate_physical_code_rejected(self):
        p=execution_case();p['bank_code'].append(copy.deepcopy(p['bank_code'][0]))
        with self.assertRaisesRegex(ValueError,'Overlapping'):validate(p)

    def test_same_virtual_pc_in_different_banks_is_admitted(self):
        p=execution_case();self.assertIs(validate(p),p)
        self.assertEqual([x['origin'] for x in p['bank_code']],[0x8000,0x8000])
        self.assertNotEqual(p['bank_code'][0]['code'],p['bank_code'][1]['code'])

    def test_cross_bank_instruction_and_boot_overlap_rejected(self):
        for pc in (0x9FFF,0xE000):
            p=execution_case();p['bank_code'][0]['bank']=31
            p['bank_code'][0]['origin']=pc
            with self.assertRaises(ValueError):validate(p)

    def test_sparse_data_cannot_overwrite_code_boot_or_vectors(self):
        for bank,offset in ((31,0),(31,0x1FFA),(31,0x100),(3,0)):
            p=execution_case();p['bank_data']=[dict(bank=bank,offset=offset,bytes='00')]
            with self.assertRaises(ValueError):validate(p)

    def test_data_bounds_and_duplicates_rejected(self):
        for rows in ([dict(bank=True,offset=0x1000,bytes='aa')],
                     [dict(bank=0,offset=8191,bytes='aabb')],
                     [dict(bank=0,offset=0x1000,bytes='aa')]*2,
                     [dict(bank=0,offset=0x1000,bytes=' ')],
                     [dict(bank=0,offset=0x1000,bytes='gg')]):
            p=read_case();p['bank_data']=rows
            with self.assertRaises(ValueError):validate(p)

    def test_no_mapper_access_under_older_profiles(self):
        code=bytes.fromhex('8d0051')
        with self.assertRaises(ValueError):decode(code,0x8000,[0x8000],ram=True,rom=True)
        self.assertTrue(decode(code,0x8000,[0x8000],ram=True,rom=True,mapper=True))

    def test_read_of_write_only_mapper_register_rejected(self):
        for code in (bytes.fromhex('ad0051'),bytes.fromhex('ee1551'),bytes.fromhex('8d0551')):
            with self.assertRaises(ValueError):decode(code,0x8000,[0x8000],ram=True,rom=True,mapper=True)

    def test_external_static_targets_require_explicit_mapper(self):
        for kw in ({'static_targets':{0x9000}}, {'mapper':True}, {'ram':True,'rom':True,'mapper':1}):
            with self.assertRaises(ValueError):decode(bytes.fromhex('4c0090'),0x8000,[0x8000],**kw)
        with self.assertRaises(ValueError):decode(bytes.fromhex('4c0090'),0x8000,[0x8000],ram=True,rom=True,mapper=True,static_targets={0x8000})

    def test_dynamic_vectors_and_original_cartridge_are_assembled(self):
        p=current_bank_case(events=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);rom=create_native(root,p,expected_initial(p)).read_bytes()
            original=(root/'original/fixture.nes').read_bytes()[16:-8192]
            self.assertEqual(rom[32768:32768+len(original)],original)
            source=(root/'guest_timeline.inc').read_text()
            self.assertIn('lda #$FFFA\n    jsr MapperRead',source)
            self.assertNotIn('lda #TimelineNMI',source)
            self.assertIn('cmp f:Banks,x',(root/'fixture.s').read_text())

    def test_execution_requires_declared_boot_not_captured_expected_values(self):
        p=read_case();initial=bytearray(expected_initial(p));initial[6]^=1
        with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):create_native(Path(d),p,bytes(initial))

    def test_mapper_mode_and_ram_guards_precede_write(self):
        for address in (0x5100,0x5114,0x5115,0x5116):
            code=write_code(address)
            self.assertLess(code.index('jmp fault'),code.index('sta MB_REG'))
        self.assertNotIn('jmp fault',write_code(0x5117))

    def test_all_fault_cases_are_real_admitted_programs(self):
        self.assertEqual(len(fault_cases()),4)
        for p in fault_cases():self.assertIs(validate_plan(p),p)

    def test_physical_mapping_bytes_are_part_of_strict_acceptance(self):
        from verify_timeline import compare
        p=read_case();p['steps']=1
        initial=expected_initial(p);row=bytearray(initial)
        row[0]=2;row[4]=1;row[9]=0x20;row[14]=2;row[17]=0x58;row[18]=1
        original=dict(name=p['name'],complete=True,records=[initial.hex(),row.hex()])
        native=dict(complete=True,marker=0x5A,status=0,completed_steps=1,records=[row.hex()])
        self.assertTrue(compare(p,original,native)['passed'])
        for offset in (20,24):
            bad=bytearray(row);bad[offset]^=1
            with self.assertRaises(RuntimeError):compare(p,original,dict(native,records=[bad.hex()]))
        bad=bytearray(row);bad[20]=255
        with self.assertRaises(ValueError):compare(p,dict(original,records=[initial.hex(),bad.hex()]),dict(native,records=[bad.hex()]))

    def test_persistent_mapper_registers_do_not_overlap_interrupt_class(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn('GI_CLASS=$1870',(root/'snes/src/guest_interrupt.inc').read_text())
        self.assertIn('MB_REG=$1871',(root/'snes/src/mmc5_prg.inc').read_text())
        self.assertNotIn('mmc5_prg',(root/'snes/src/native.s').read_text())
        self.assertNotIn('mmc5-prg-rom',(root/'tools/build_native.py').read_text())


class MMC5ObservationTests(unittest.TestCase):
    def seed(self,root):
        (root/'src').mkdir();(root/'src/x6502.c').write_text('#include "sound.h"\n'+BEGIN+'\n'+END)

    def test_idempotent_observation_and_changed_header_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            p=root/'src/n2s_timeline_probe.h';p.write_text(p.read_text().replace('slot<4','slot<3'))
            with self.assertRaises(ValueError):instrument(root)

    def test_changed_installed_dispatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);instrument(root)
            f=root/'src/x6502.c';f.write_text(f.read_text().replace('tl_after(b1,','tl_after(0,'))
            with self.assertRaises(ValueError):instrument(root)

    def test_compiled_map_observer_uses_original_pointer_not_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source='''#include <stdint.h>
#include <assert.h>
uint8_t *Page[32],*PRGptr[32];uint32_t PRGsize[32];
'''+HELPER+'''
int main(void){
 static uint8_t rom[262144], ram[8192]; unsigned slot;
 PRGptr[0]=rom;PRGsize[0]=sizeof(rom);
 for(slot=0;slot<4;slot++){unsigned a=0x8000+slot*8192;
  Page[a>>11]=(uint8_t*)((uintptr_t)rom+slot*8192-a);
  assert(tl_mmc5_bank(a)==slot);
 }
 Page[0x8000>>11]=(uint8_t*)((uintptr_t)rom+31*8192-0x8000);
 assert(tl_mmc5_bank(0x8000)==31);
 Page[0x8000>>11]=(uint8_t*)((uintptr_t)ram-0x8000);
 assert(tl_mmc5_bank(0x8000)==255);
 assert(tl_mmc5_bank(0x6000)==255);
 PRGptr[0]=0;assert(tl_mmc5_bank(0x8000)==255);return 0;
}'''
            (root/'test.c').write_text(source)
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
