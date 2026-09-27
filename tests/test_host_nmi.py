"""Actual assembly plus strict nonvacuous host-interrupt evidence checks."""
from pathlib import Path
import copy
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from timeline_program import create_native
from timeline_fixture import cases,expected_initial
from timeline_host import MODES,PROTECTED,prepare,replace_once
from host_nmi_fixture import create as create_registers,inputs,scratch
from verify_host_nmi import check_host,check_registers,sample


class HostBuildTests(unittest.TestCase):
    def test_default_is_unchanged_and_explicit_none_is_identical(self):
        plan=cases()[0]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            a=create_native(root/'a',plan,expected_initial(plan))
            b=create_native(root/'b',plan,expected_initial(plan),host_mode=None)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            self.assertNotIn('TimelineHostNMI',(a.parent/'fixture.s').read_text())
            self.assertFalse((a.parent/'timeline_host_nmi.inc').exists())

    def test_every_host_mode_really_assembles(self):
        plan=cases()[3]
        with tempfile.TemporaryDirectory() as d:
            for mode in MODES:
                with self.subTest(mode=mode):
                    rom=create_native(Path(d)/mode,plan,expected_initial(plan),host_mode=mode)
                    self.assertEqual(rom.stat().st_size,65536)
                    self.assertIn('TimelineHostNMI',(rom.parent/'fixture.s').read_text())
                    nmi=struct.unpack_from('<H',rom.read_bytes(),0x7FEA)[0]
                    self.assertGreaterEqual(nmi,0x8000)

    def test_invalid_modes_reject_before_creating_files(self):
        plan=cases()[0]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'unused'
            for mode in (False,True,1,{},[],'unknown','FREE'):
                with self.subTest(mode=mode),self.assertRaises(ValueError):
                    create_native(out,plan,expected_initial(plan),host_mode=mode)
                self.assertFalse(out.exists())

    def test_standalone_register_matrix_actually_assembles_in_both_banks(self):
        with tempfile.TemporaryDirectory() as d:
            for nested in (False,True):
                for mirror in (False,True):
                    rom=create_registers(Path(d)/f'{nested}-{mirror}',nested=nested,mirror=mirror)
                    self.assertEqual(rom.stat().st_size,65536)

    def test_invalid_register_flags_reject_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'unused'
            for kwargs in ({'nested':1},{'mirror':0},{'nested':'yes'}):
                with self.assertRaises(ValueError):create_registers(out,**kwargs)
                self.assertFalse(out.exists())

    def test_changed_or_duplicate_integration_anchor_fails(self):
        with self.assertRaises(ValueError):replace_once('ab','x','y')
        with self.assertRaises(ValueError):replace_once('aba','a','y')
        self.assertEqual(replace_once('abc','b','X'),'aXc')

    def test_context_map_is_bounded_disjoint_and_outside_guest_ram(self):
        addresses=[a+i for a,n in PROTECTED for i in range(n)]
        self.assertEqual(len(addresses),132)
        self.assertEqual(len(set(addresses)),132)
        self.assertTrue(all(0x0200<=a<0x1D00 for a in addresses))
        self.assertEqual(len(scratch()),132)

    def test_inputs_exercise_every_native_status_and_width_combination(self):
        rows=inputs()
        self.assertEqual({r['p'] for r in rows},set(range(256)))
        for widths in (0,16,32,48):
            self.assertEqual(sum((r['p']&48)==widths for r in rows),64)
        self.assertTrue(all(r['a']>255 and r['d']!=0 for r in rows))
        self.assertEqual({r['dbr'] for r in rows},{0x7E,0x7F})

    def test_production_game_runtime_does_not_include_test_worker(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('timeline_host',(root/name).read_text())


class HostAcceptanceTests(unittest.TestCase):
    def args(self):
        plan=cases()[0];plan['steps']=1
        initial=expected_initial(plan);end=bytearray(initial)
        struct.pack_into('<I',end,0,2);struct.pack_into('<H',end,4,plan['origin']+1)
        end[9]|=8;end[14]=2;end[17]=0xF8;struct.pack_into('<H',end,18,1)
        ref=dict(name=plan['name'],complete=True,records=[initial.hex(),end.hex()])
        native=dict(complete=True,marker=90,status=0,completed_steps=1,host_nmi_enabled=True,records=[end.hex()],
                    protected_memory=bytes(132).hex(),host=dict(count=1,work=1,depth=0,peak=1,
                       fault=0,wait_hits=0,nested_wait_hits=0,low_canary=0xA5,high_canary=0x5A,min_sp=0x1F00))
        return plan,ref,native,'free'

    def test_no_host_control_does_not_interpret_uninitialized_host_ram(self):
        from unittest.mock import patch
        class FakeRunner:
            def __init__(self,*args):self.frames=0
            def run(self,n):self.frames+=n
            def close(self):pass
            def memory(self):
                ram=bytearray(131072);ram[0x1D06]=255
                if self.frames==2:ram[0x1FFF]=90;ram[0x18D0]=1
                return bytes(ram)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core=root/'core';rom=root/'rom';core.write_bytes(b'unit core');rom.write_bytes(b'unit rom')
            with patch('verify_host_nmi.Runner',FakeRunner):
                baseline=sample(core,rom,root/'base.json',1,host_expected=False)
                enabled=sample(core,rom,root/'enabled.json',1)
            self.assertTrue(baseline['complete']);self.assertEqual(baseline['host_frames'],2)
            self.assertFalse(enabled['complete']);self.assertEqual(enabled['host_frames'],1)
            args=list(self.args());args[2]['host_nmi_enabled']=False
            with self.assertRaises(ValueError):check_host(*args)

    def test_complete_nonvacuous_guest_and_host_result_passes(self):
        self.assertTrue(check_host(*self.args())['passed'])

    def test_equal_guest_without_host_interrupts_never_passes(self):
        args=self.args();args[2]['host'].update(count=0,work=0,peak=0,min_sp=0)
        with self.assertRaises(ValueError):check_host(*args)

    def test_fault_work_depth_canaries_and_watermark_are_strict(self):
        for key,value in [('fault',1),('work',0),('depth',1),('peak',2),('low_canary',0),
                          ('high_canary',0),('min_sp',0x1E7F),('min_sp',0x1FF1),('count',2**32)]:
            args=self.args();args[2]['host'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):check_host(*args)

    def test_falsey_fault_payloads_and_boolean_metadata_rejected(self):
        for fault in (False,0,{},[],""):
            args=self.args();args[2]['fault']=fault
            with self.assertRaises(ValueError):check_host(*args)
        for key in ('fault','depth','count','peak'):
            args=self.args();args[2]['host'][key]=False
            with self.assertRaises(ValueError):check_host(*args)

    def test_missing_extra_and_malformed_host_fields_rejected(self):
        for variant in (None,{},dict(extra=0)):
            args=self.args();args[2]['host']=variant
            with self.assertRaises(ValueError):check_host(*args)
        args=self.args();args[2]['host']['extra']=0
        with self.assertRaises(ValueError):check_host(*args)

    def test_protected_memory_must_be_complete(self):
        for value in (None,'',bytes(132),'00'*131,'not-hex'):
            args=self.args();args[2]['protected_memory']=value
            with self.assertRaises(ValueError):check_host(*args)

    def test_deliberate_site_requires_all_waits(self):
        args=list(self.args());args[3]='time'
        with self.assertRaises(ValueError):check_host(*args)
        args[2]['host']['wait_hits']=1
        self.assertTrue(check_host(*args)['passed'])
        args[2]['host']['wait_hits']=2
        with self.assertRaises(ValueError):check_host(*args)

    def test_nested_waits_require_two_real_service_levels(self):
        args=list(self.args());args[3]='nested';args[2]['host'].update(count=2,work=2,peak=2,wait_hits=1,nested_wait_hits=1)
        self.assertTrue(check_host(*args)['passed'])
        for key,value in [('peak',1),('nested_wait_hits',0),('count',3)]:
            bad=copy.deepcopy(args);bad[2]['host'][key]=value
            with self.assertRaises(ValueError):check_host(*bad)

    def test_empty_guest_or_unknown_mode_never_passes(self):
        args=self.args();args[2]['records']=[]
        with self.assertRaises(ValueError):check_host(*args)
        args=list(self.args());args[3]='other'
        with self.assertRaises(ValueError):check_host(*args)


class NativeRegisterAcceptanceTests(unittest.TestCase):
    def report(self):
        rows=[]
        for r in inputs():
            x=r['x']&255 if r['p']&16 else r['x'];y=r['y']&255 if r['p']&16 else r['y']
            raw=(struct.pack('<HHHHBBHB',r['a'],x,y,r['d'],r['dbr'],r['p'],0x1FF0,0x80)+scratch())
            rows.append(raw.hex())
        return dict(complete=True,marker=90,completed_cases=256,records=rows,
                    host=dict(count=512,depth=0,peak=2,fault=0,wait_hits=256,nested_wait_hits=256,
                              work=512,low_canary=0xA5,high_canary=0x5A,min_sp=0x1EC0))

    def test_every_declared_native_context_matches(self):
        self.assertTrue(check_registers(self.report(),nested=True,mirror=True)['passed'])

    def test_hidden_accumulator_and_bank_restoration_are_checked(self):
        for offset in (1,2,4,6,8,9,10,12,13,144):
            report=self.report();raw=bytearray.fromhex(report['records'][32]);raw[offset]^=1
            report['records'][32]=raw.hex()
            with self.subTest(offset=offset),self.assertRaises(RuntimeError):
                check_registers(report,nested=True,mirror=True)

    def test_failed_or_incomplete_register_matrix_never_passes(self):
        for key,value in [('complete',False),('marker',238),('completed_cases',255),('completed_cases',True),('records',[])]:
            report=self.report();report[key]=value
            with self.assertRaises(ValueError):check_registers(report,nested=True,mirror=True)

    def test_fault_even_with_equal_context_is_rejected(self):
        report=self.report();report['host']['fault']=1
        with self.assertRaises(ValueError):check_registers(report,nested=True,mirror=True)
        for fault in (False,0,{},[]):
            report=self.report();report['fault']=fault
            with self.assertRaises(ValueError):check_registers(report,nested=True,mirror=True)

    def test_mismatched_bank_nested_settings_and_unknown_metadata_rejected(self):
        with self.assertRaises(RuntimeError):check_registers(self.report(),nested=True,mirror=False)
        with self.assertRaises(ValueError):check_registers(self.report(),nested=False,mirror=True)
        for field in ('peak','min_sp','wait_hits'):
            report=self.report();report['host'][field]=True
            with self.assertRaises(ValueError):check_registers(report,nested=True,mirror=True)


if __name__=='__main__':unittest.main()
