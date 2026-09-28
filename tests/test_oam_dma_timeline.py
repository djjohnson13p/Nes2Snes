"""Narrow DMA contract, timing rejection, and actual observer bounds."""
from pathlib import Path
import copy
import ctypes as C
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from oam_dma_timeline import masked_code,underlying,validate,sync_code,create_nes,create_native,initial,PROFILE
from oam_dma_fixture import make_case,cases,guard_cases
from verify_oam_dma import Observer,TimingRow,timing,noninterference
from instrument_nestopia_dma import instrument,HEADER,ANCHOR,BEFORE,AFTER
from guest_cycles import Instruction
from opcodes6502 import OPS


class DmaAdapterTests(unittest.TestCase):
    def test_mask_only_exact_decoded_store(self):
        self.assertEqual(masked_code(b'\x8d\x14\x40\xad\x14\x40\x9d\x14\x40'),b'\x8d\x02\x20\xad\x14\x40\x9d\x14\x40')
        for raw in (b'\x8d',b'\x02',None):
            with self.assertRaises(ValueError):masked_code(raw)

    def test_original_plan_not_mutated(self):
        plan=make_case(2,0,255);before=copy.deepcopy(plan)
        self.assertEqual(validate(plan),before)
        self.assertNotIn('8d1440',underlying(plan)['code'])
        self.assertEqual(plan,before)

    def test_old_profile_does_not_admit_dma(self):
        from chr_mode_rewrite import validate as old_validate,PROFILE as old_profile
        with self.assertRaises(ValueError):old_validate(dict(make_case(2,0,255),memory_model=old_profile))

    def test_explicit_profile_required(self):
        for value in ({},None,dict(make_case(2,0,255),memory_model='other')):
            with self.assertRaises(ValueError):validate(value)

    def test_no_guest_requests_admitted(self):
        p=make_case(2,0,255);p['events']=[dict(cycle=10,irq=False,nmi=True)]
        with self.assertRaises(ValueError):validate(p)

    def test_reserved_sync_helper_cannot_be_data(self):
        p=make_case(2,0,255);p['bank_data']=[dict(bank=3,offset=0x1200,bytes='11')]
        with self.assertRaises(ValueError):validate(p)

    def test_reserved_sync_helper_cannot_be_code(self):
        p=make_case(2,0,255);p['bank_code']=[dict(bank=3,origin=0xF200,code='ea',starts=[0xF200])]
        with self.assertRaises(ValueError):validate(p)

    def test_ambiguous_cpu_ranges_are_refused(self):
        p=make_case(2,0,255)
        p['bank_code']=[dict(bank=0,origin=0xE100,code='ea',starts=[0xE100])]
        with self.assertRaises(ValueError):validate(p)

    def test_boot_tail_has_even_twenty_original_cycles(self):
        p=make_case(2,0,255);code=sync_code(p);start=code.index(b'\x8d\x14\x40')+3
        total=0;pos=start
        while pos<len(code):
            op=code[pos];size=OPS[op][2];operand=int.from_bytes(code[pos+1:pos+size],'little')
            total+=Instruction(op,0xF200+pos,operand).cost();pos+=size
        self.assertEqual(total,20)
        self.assertTrue(code.endswith(b'\x4c\x00\xe1'))

    def test_all_source_pages_and_admitted_oam_addresses_covered(self):
        plans=cases()
        self.assertEqual({int(p['name'].split('-')[1],16) for p in plans},set(range(32)))
        self.assertEqual({int(p['name'].split('-')[2],16) for p in plans},{i for i in range(256) if i%4!=3})
        self.assertEqual(len({p['code'] for p in plans}),len(plans))
        self.assertTrue(any(p['name'].endswith('-1') for p in plans))

    def test_refusal_plans_are_preserved(self):
        self.assertEqual(len(guard_cases()),7)
        for p,pc,count in guard_cases():
            self.assertIs(validate(p),p)
            self.assertEqual(p['starts'][count],pc)
            offset=pc-p['origin'];self.assertEqual(bytes.fromhex(p['code'])[offset:offset+3],b'\x8d\x14\x40')

    def test_actual_assembly_and_original_bank_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=make_case(2,0,0xA5)
            original=create_nes(root/'nes',p).read_bytes()[16:16+p['prg_banks']*8192]
            rom=create_native(root/'native',p,initial(p)).read_bytes()
            self.assertEqual(rom[32768:32768+len(original)],original)
            self.assertIn('    sep #$20\n.a8\n    rts',(root/'native/oam_dma_timeline.inc').read_text())

    def test_no_production_import_or_reference(self):
        root=Path(__file__).resolve().parents[1]
        for path in ('tools/build_native.py','snes/src/native.s'):
            self.assertNotIn('oam_dma_timeline',(root/path).read_text())


class DmaTimingTests(unittest.TestCase):
    def data(self):
        p={'steps':1,'name':'test','origin':0xE100,'prg_banks':4,'code':'8d1440','starts':[0xE100],'bank_code':[]}
        ref={'timings':[dict(start=100,end=100+518*12,pc=0xE100,next_pc=0xE103,clock=12,opcode=0x8D)]}
        record=bytearray(2080);record[:4]=(518).to_bytes(4,'little');record[4:6]=b'\x03\xe1';record[17]=0x8D
        meta=b'\x01\0\x02\x02\x02\x02\0\0'
        actual={'records':[record.hex()],'dma_records':meta.hex(),'dma_state':meta.hex()}
        return p,ref,actual

    def test_exact_independent_duration(self):
        p,r,a=self.data();result=timing(p,r,a)
        self.assertEqual(result['delays'],[514]);self.assertEqual(result['span_cycles'],518)

    def test_changed_independent_clock_and_pc_refused(self):
        for key,value in [('end',6304),('pc',0xE101),('next_pc',0xE104),('clock',13),('opcode',0xEA),('start',True)]:
            p,r,a=self.data();r['timings'][0][key]=value
            with self.subTest(key=key),self.assertRaises((ValueError,RuntimeError)):timing(p,r,a)

    def test_changed_native_clock_and_ledger_refused(self):
        p,r,a=self.data()
        for key in ('records','dma_records','dma_state'):
            bad=copy.deepcopy(a)
            if key=='records':bad[key][0]='00'+bad[key][0][2:]
            else:bad[key]='00'+bad[key][2:]
            with self.assertRaises((ValueError,RuntimeError)):timing(p,r,bad)

    def test_missing_records_refused(self):
        p,r,a=self.data();r['timings']=[]
        with self.assertRaises(ValueError):timing(p,r,a)

    def test_missing_native_or_malformed_record_refused(self):
        for records in ([],None,['00']):
            p,r,a=self.data();a['records']=records
            with self.assertRaises(ValueError):timing(p,r,a)
        for record in ({},None,{'start':0}):
            p,r,a=self.data();r['timings']=[record]
            with self.assertRaises(ValueError):timing(p,r,a)

    def test_clock_origins_preserve_phase_and_exact_carry(self):
        for origin in (True,1,-2,2**32):
            p,r,a=self.data()
            with self.assertRaises(ValueError):timing(p,r,a,origin)
        p,r,a=self.data();record=bytearray.fromhex(a['records'][0])
        record[:4]=(0xFF00+518).to_bytes(4,'little');a['records']=[record.hex()]
        self.assertEqual(timing(p,r,a,0xFF00)['delays'],[514])

    def test_observer_cannot_hide_logical_changes(self):
        a={'cpu_ram':'a','core_sha256':'plain','frames':1};b=dict(a,core_sha256='probe',timings=[])
        noninterference(a,b)
        b['cpu_ram']='b'
        with self.assertRaises(RuntimeError):noninterference(a,b)

    def test_observer_invalid_configuration_before_core_access(self):
        self.assertEqual(C.sizeof(TimingRow),32)
        for entry,count in [(True,1),(0x7FFF,1),(0x8000,0),(0x8000,65),(0x8000,True)]:
            with self.assertRaises(ValueError):Observer(None,entry,count)


class DmaInstrumentationTests(unittest.TestCase):
    def seed(self,root):
        path=root/'source/core';path.mkdir(parents=True)
        (path/'NstCpu.cpp').write_text(ANCHOR+'\n')
        return path/'NstCpu.cpp'

    def test_exact_single_install_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=self.seed(root)
            self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            self.assertEqual(path.read_text().count(BEFORE),1);self.assertEqual(path.read_text().count(AFTER),1)

    def test_changed_anchor_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=self.seed(root);path.write_text('changed')
            with self.assertRaises(ValueError):instrument(root)
            self.assertEqual(path.read_text(),'changed');self.assertFalse(path.with_name('n2s_dma_trace.h').exists())

    def test_changed_installed_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=self.seed(root);instrument(root)
            path.with_name('n2s_dma_trace.h').write_text('changed')
            with self.assertRaises(ValueError):instrument(root)

    def test_compiled_observer_bounds_and_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'observer.h').write_bytes(HEADER.read_bytes())
            (root/'test.cpp').write_text(r'''
#include "observer.h"
#include <cassert>
int main() {
 assert(sizeof(n2s_dma_row)==32);
 assert(!retro_n2s_dma_configure(0x7fff,1));
 assert(!retro_n2s_dma_configure(0x8000,65));
 assert(retro_n2s_dma_configure(0x8000,1));
 n2s_dma_begin(0xe000,100,12);n2s_dma_end(0xe002,0xa9,124);
 assert(!retro_n2s_dma_status(0));
 n2s_dma_begin(0x8000,124,12);n2s_dma_end(0x8003,0x8d,6340);
 assert(retro_n2s_dma_status(0)==1 && !retro_n2s_dma_status(1));
 assert(n2s_dma_rows[0].end-n2s_dma_rows[0].start==6216);
 n2s_dma_begin(0x8003,6340,12);n2s_dma_end(0x8005,0xa9,6364);
 assert(retro_n2s_dma_status(0)==1);
 assert(retro_n2s_dma_configure(0x8000,1));
 n2s_dma_begin(0x8000,100,12);n2s_dma_end(0x8001,0xea,101);
 assert(retro_n2s_dma_status(1)==2);
 assert(retro_n2s_dma_configure(0x8000,1));
 n2s_dma_begin(0x8000,100,12);assert(retro_n2s_dma_status(3)==1);
 assert(!retro_n2s_dma_configure(0x8000,0));assert(!retro_n2s_dma_status(3));
}
''')
            subprocess.run(['c++','-std=c++11','-Wall','-Wextra','-Werror',str(root/'test.cpp'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
