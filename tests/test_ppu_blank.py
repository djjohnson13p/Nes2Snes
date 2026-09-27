"""Blank-transfer profile, snapshot completeness, and generated context gates."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mmc5_ppu_blank import validate,initial_ppu,initial_ciram,boot_code,register_code,create_native,PROFILE
from ppu_blank_fixture import cases,fault_cases,transfer,latches
from timeline_program import decode,validate_plan
from timeline_fixture import expected_initial
from verify_ppu_blank import check_ppu,exact_hex,reference_disagreement
from unittest.mock import patch


class BlankPPUTests(unittest.TestCase):
    def sample(self):
        p=transfer();init=initial_ppu().hex();ram=initial_ciram().hex()
        return p,dict(ppu_records=[init]*(p['steps']+1),initial_ciram=ram,ciram=ram),dict(ppu_records=[init]*p['steps'],ppu_state=init,ciram=ram)

    def test_explicit_parent_gates(self):
        for kw in ({},{'ppu_blank':True},{'ram':True,'rom':True,'mapper':True,'cartridge_ram':True,'cpu_io':True}):
            with self.assertRaises(ValueError):decode(bytes.fromhex('8d0620'),0xE100,[0xE100],**kw)
        with self.assertRaises(ValueError):decode(b'\xea',0xE100,[0xE100],ppu_blank=1)

    def test_every_authored_plan_valid_and_names_unique(self):
        plans=cases()+fault_cases()
        self.assertEqual(len({p['name'] for p in plans}),len(plans))
        for p in plans:self.assertIs(validate_plan(p),p)

    def test_all_supported_nametable_combinations(self):
        mappings=[int(p['name'].split('-')[-1],16) for p in cases() if p['name'].startswith('pv-map')]
        self.assertEqual(len(mappings),81)
        self.assertEqual(set(mappings),{v for v in range(256) if all((v>>s)&3!=2 for s in (0,2,4,6))})

    def test_guarded_registers_are_not_silently_executed(self):
        for n,a in (('LDA',0x2002),('LDA',0x2004),('STA',0x2003),('STA',0x2004)):
            self.assertIn('jmp PpuUnsupported',register_code(n,a))

    def test_data_and_address_register_mirrors(self):
        for a in (0x2006,0x200E,0x3FFE):self.assertIn('PpuAddress',register_code('STA',a))
        for a in (0x2007,0x201F,0x3FFF):self.assertIn('PpuDataRead',register_code('LDA',a))
        for a in (0x2000,0x2001,0x2005,0x2006):self.assertIn('PpuLatchRead',register_code('LDA',a))

    def test_unsupported_api_values(self):
        for n,a in (('INC',0x2007),('STA',True),('STA',0x4000),('LDA',0x5106)):
            with self.assertRaises(ValueError):register_code(n,a)

    def test_initial_state_shape(self):
        self.assertEqual(len(initial_ppu()),16);self.assertEqual(len(initial_ciram()),2048)
        self.assertEqual(initial_ciram()[:1024],b'\x3c'*1024)
        self.assertEqual(initial_ciram()[1024:],b'\xc3'*1024)
        self.assertLessEqual(len(boot_code()),512)

    def test_boot_helper_rejects_code_and_data_overlap(self):
        for field,value in [('bank_code',[dict(bank=31,origin=0xF000,code='ea',starts=[0xF000])]),
                            ('bank_data',[dict(bank=31,offset=0x1100,bytes='01')])]:
            p=transfer();p[field]=value
            with self.assertRaisesRegex(ValueError,'boot helper'):validate(p)

    def test_old_profile_does_not_admit_ppu_registers(self):
        p=transfer();p['memory_model']='mmc5-cpu-io'
        with self.assertRaises(ValueError):validate_plan(p)

    def test_snapshot_acceptance_scope(self):
        p,a,b=self.sample();result=check_ppu(p,a,b)
        self.assertEqual(result['ppu_register_bytes'],p['steps']*16)
        self.assertEqual(result['final_ciram_bytes'],2048)

    def test_missing_short_or_whitespace_snapshots_rejected(self):
        for value in (None,False,'','00','00  '*512,'gg'*2048):
            p,a,b=self.sample();b['ciram']=value
            with self.assertRaises(ValueError):check_ppu(p,a,b)

    def test_missing_and_changed_ppu_records_rejected(self):
        for change in ('missing','count','state','final'):
            p,a,b=self.sample()
            if change=='missing':del b['ppu_records']
            elif change=='count':b['ppu_records'].pop()
            elif change=='state':b['ppu_records'][7]='01'+b['ppu_records'][7][2:]
            else:b['ppu_state']='01'+b['ppu_state'][2:]
            with self.assertRaises((ValueError,RuntimeError)):check_ppu(p,a,b)

    def test_bad_original_boot_never_accepted(self):
        for key in ('ppu','memory'):
            p,a,b=self.sample()
            if key=='ppu':a['ppu_records'][0]='01'+a['ppu_records'][0][2:]
            else:a['initial_ciram']='01'+a['initial_ciram'][2:]
            with self.assertRaises(ValueError):check_ppu(p,a,b)

    def test_changed_ciram_byte_rejected(self):
        p,a,b=self.sample();b['ciram']='01'+b['ciram'][2:]
        with self.assertRaises(RuntimeError):check_ppu(p,a,b)

    def test_equal_but_out_of_contract_ppu_states_rejected(self):
        for offset,value in ((0,128),(1,8),(2,2),(3,8),(10,2),(12,4),(13,1)):
            p,a,b=self.sample();raw=bytearray(initial_ppu());raw[offset]=value
            a['ppu_records'][1]=b['ppu_records'][0]=raw.hex()
            with self.assertRaises(ValueError):check_ppu(p,a,b)

    def test_actual_native_assembly_and_context_extension(self):
        with tempfile.TemporaryDirectory() as d:
            p=latches(255,128);out=Path(d);create_native(out,p,expected_initial(p),host_mode='nested')
            handler=(out/'timeline_host_nmi.inc').read_text();driver=(out/'fixture.s').read_text()
            self.assertIn('cpx #48\n    bne save_capture',handler)
            self.assertIn('ldx #46\nrestore_capture',handler)
            self.assertIn('cpx #48\n    bne poison_capture',driver)
            self.assertIn('jsr PpuCapture',driver)

    def diagnostic_inputs(self):
        row=bytearray(2080);row[32+0x681]=0x11;row[32+0x682]=0x54
        a=dict(complete=True,records=[row.hex()]*32)
        return a,dict(complete=True)

    def test_reference_disagreement_is_not_reported_as_an_accuracy_pass(self):
        a,b=self.diagnostic_inputs()
        with tempfile.TemporaryDirectory() as folder, patch('verify_ppu_blank.nes_capture',side_effect=[a,b]):
            result=reference_disagreement(Path('plain'),Path('probe'),Path(folder))
            self.assertTrue(result['diagnostic_reproduced'])
            self.assertFalse(result['reference_accuracy_passed'])
            self.assertEqual(result['documented_attribute'],0)
            self.assertEqual(result['observed_attribute'],0x54)

    def test_incomplete_changed_or_interfering_diagnostic_rejected(self):
        for change in ('incomplete','value','control'):
            a,b=self.diagnostic_inputs()
            if change=='incomplete':a['records'].pop()
            elif change=='value':
                row=bytearray.fromhex(a['records'][-1]);row[32+0x682]=0;a['records'][-1]=row.hex()
            else:b['complete']=False
            with tempfile.TemporaryDirectory() as folder, patch('verify_ppu_blank.nes_capture',side_effect=[a,b]):
                with self.assertRaises(RuntimeError):reference_disagreement(Path('plain'),Path('probe'),Path(folder))

    def test_production_remains_separate(self):
        root=Path(__file__).resolve().parents[1]
        for file in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('mmc5_ppu_blank',(root/file).read_text())


if __name__=='__main__':unittest.main()
