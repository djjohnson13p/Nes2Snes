"""Contract and acceptance gates for dependent native timeline execution."""
from pathlib import Path
import copy
import ctypes as C
import json
import struct
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from timeline_program import decode,generate,validate_events,validate_plan,create_native
from timeline_fixture import cases,expected_initial
from verify_timeline import compare,compare_rebased
from instrument_timeline_probe import instrument,HEADER,PRE,POST,BEGIN,END


class TimelinePlanTests(unittest.TestCase):
    def test_all_authored_programs_and_events_validate(self):
        rows=cases();self.assertEqual(len(rows),18)
        for row in rows:
            validate_plan(row)
            self.assertEqual(len(expected_initial(row)),544)
            self.assertIn('jsr GuestTimelineRetire',__import__('timeline_program').DRIVER)

    def test_codegen_uses_existing_accounting_and_interrupt_components(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'snes/src/guest_timeline.inc').read_text()
        for name in ('GuestInstructionCycles','GuestInterruptBoundary'):self.assertIn('jsr '+name,text)
        for name in ('native.s','native_ppudata.inc'):
            self.assertNotIn('guest_timeline.inc',(root/'snes/src'/name).read_text())
        self.assertNotIn('guest_timeline',(root/'tools/build_native.py').read_text())

    def test_every_declared_entry_and_static_target_is_required(self):
        row=cases()[0];code=bytes.fromhex(row['code'])
        for starts in (row['starts'][1:],row['starts']+[row['starts'][-1]],sorted(row['starts']+[row['origin']+3])):
            with self.assertRaises(ValueError):decode(code,row['origin'],starts)
        with self.assertRaisesRegex(ValueError,'Static control'):
            decode(bytes.fromhex('4c0081'),0x8000,[0x8000])

    def test_unsupported_opcodes_modes_and_io_fail_closed(self):
        for code in (b'\x00',b'\x02',bytes.fromhex('ad0020'),bytes.fromhex('bd0000'),bytes.fromhex('b100'),bytes.fromhex('6c0000')):
            with self.subTest(code=code),self.assertRaises(ValueError):decode(code,0x8000,[0x8000])

    def test_empty_truncated_oversize_nonbytes_and_wrap_rejected(self):
        for code,origin,starts in [(b'',0x8000,[]),(b'\xA9',0x8000,[0x8000]),(b'\xEA'*2049,0x8000,[]),('EA',0x8000,[0x8000]),(b'\xEA'*32,0xFFF0,[])]:
            with self.assertRaises(ValueError):decode(code,origin,starts)

    def test_boolean_addresses_and_unordered_entries_rejected(self):
        for code,origin,starts in [(b'\xEA',True,[1]),(b'\xEA',0x8000,[True]),(b'\xEA\xEA',0x8000,[0x8001,0x8000])]:
            with self.assertRaises(ValueError):decode(code,origin,starts)

    def test_backward_and_forward_original_branches_decode(self):
        rows=decode(bytes.fromhex('18b0fd90fc'),0x8000,[0x8000,0x8001,0x8003])
        self.assertEqual(len(rows),3)

    def test_program_generation_does_not_contain_expected_capture_inputs(self):
        row=cases()[0];text=generate(bytes.fromhex(row['code']),row['origin'],row['starts'])
        self.assertNotIn('records',text);self.assertNotIn('expected',text)
        self.assertIn('sta GC_INPUT+6',text);self.assertIn('jmp retire',text)

    def test_event_order_types_shape_and_capacity(self):
        for events in (None,[dict(cycle=0,irq=False,nmi=False)],[dict(cycle=True,irq=False,nmi=False)],
                       [dict(cycle=1,irq=1,nmi=False)],[dict(cycle=1,irq=False,nmi=False,extra=1)],
                       [dict(cycle=1,irq=False,nmi=False)]*2,
                       [dict(cycle=i+1,irq=False,nmi=False) for i in range(65)]):
            with self.assertRaises(ValueError):validate_events(events)

    def test_malformed_plan_fields_and_names_rejected(self):
        for key,value in [('name','../escape'),('steps',True),('steps',113),('stack',True),('x',-1),('seed',256),('code','not-hex'),('extra',1)]:
            row=cases()[0];row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_plan(row)

    def test_vectors_must_be_distinct_observed_entries(self):
        row=cases()[0]
        for value in (True,0,row['nmi']):
            with self.assertRaises(ValueError):validate_plan(dict(row,irq=value))

    def test_reference_snapshot_cannot_replace_arbitrary_initial_state(self):
        row=cases()[0];initial=expected_initial(row)
        with tempfile.TemporaryDirectory() as d:
            for offset in (0,4,11,18,25):
                altered=bytearray(initial);altered[offset]^=1
                with self.assertRaises(ValueError):create_native(Path(d),row,bytes(altered))

    def test_real_native_assembly(self):
        row=cases()[0]
        with tempfile.TemporaryDirectory() as d:
            rom=create_native(Path(d),row,expected_initial(row))
            self.assertEqual(rom.stat().st_size,65536)


class TimelineAcceptanceTests(unittest.TestCase):
    def inputs(self):
        row=cases()[0];row['steps']=1
        initial=expected_initial(row);end=bytearray(initial)
        struct.pack_into('<I',end,0,2);struct.pack_into('<H',end,4,row['origin']+1)
        end[9]|=8;end[14]=2;end[17]=0xF8;struct.pack_into('<H',end,18,1)
        ref=dict(name=row['name'],complete=True,records=[initial.hex(),end.hex()])
        native=dict(complete=True,marker=90,status=0,completed_steps=1,records=[end.hex()])
        return row,ref,native

    def test_complete_stream_passes(self):
        self.assertEqual(compare(*self.inputs())['steps'],1)

    def test_fault_and_partial_outputs_never_pass(self):
        for key,value in [('complete',False),('marker',0xEE),('status',1),('completed_steps',0)]:
            plan,ref,native=self.inputs();native[key]=value
            with self.assertRaises(ValueError):compare(plan,ref,native)
        plan,ref,native=self.inputs();ref['complete']=False
        with self.assertRaises(ValueError):compare(plan,ref,native)

    def test_falsey_faults_and_boolean_metadata_are_rejected(self):
        for fault in (False,0,{},[],""):
            for side in (1,2):
                args=list(self.inputs());args[side]['fault']=fault
                with self.assertRaises(ValueError):compare(*args)
        for key,value in [('status',False),('completed_steps',True)]:
            plan,ref,native=self.inputs();native[key]=value
            with self.assertRaises(ValueError):compare(plan,ref,native)

    def test_changed_cycle_flags_register_memory_and_stack_are_detected(self):
        for offset in (0,4,6,9,10,11,14,15,16,17,18,32,32+256,543):
            plan,ref,native=self.inputs();data=bytearray.fromhex(native['records'][0]);data[offset]^=1;native['records'][0]=data.hex()
            with self.subTest(offset=offset),self.assertRaises(RuntimeError):compare(plan,ref,native)

    def test_truncated_missing_and_extra_steps_rejected(self):
        for records in ([],['00'],['00','00']):
            plan,ref,native=self.inputs();native['records']=records
            with self.assertRaises(ValueError):compare(plan,ref,native)

    def test_matching_but_nonclosing_time_is_rejected(self):
        plan,ref,native=self.inputs();data=bytearray.fromhex(native['records'][0]);data[0]=3
        native['records'][0]=ref['records'][1]=data.hex()
        with self.assertRaisesRegex(ValueError,'Nonclosing'):compare(plan,ref,native)

    def test_clock_epoch_comparison_is_exact_and_keeps_state_checks(self):
        plan,ref,native=self.inputs();epoch=0xFFF0
        row=bytearray.fromhex(native['records'][0]);row[:4]=(epoch+2).to_bytes(4,'little');native['records'][0]=row.hex()
        self.assertTrue(compare_rebased(plan,ref,native,epoch)['passed'])
        row[1]^=1;native['records'][0]=row.hex()
        with self.assertRaises((RuntimeError,ValueError)):compare_rebased(plan,ref,native,epoch)
        with self.assertRaises(ValueError):compare_rebased(plan,ref,native,True)

    def test_unexercised_event_is_not_claimed_as_tested(self):
        plan,ref,native=self.inputs();plan['events']=[dict(cycle=100,irq=True,nmi=False)]
        with self.assertRaisesRegex(ValueError,'every declared event'):compare(plan,ref,native)

    def test_wrong_initial_boot_and_identity_rejected(self):
        plan,ref,native=self.inputs();ref['name']='another'
        with self.assertRaises(ValueError):compare(plan,ref,native)
        plan,ref,native=self.inputs();raw=bytearray.fromhex(ref['records'][0]);raw[32]^=1;ref['records'][0]=raw.hex()
        with self.assertRaisesRegex(ValueError,'boot'):compare(plan,ref,native)


class TimelineHarnessTests(unittest.TestCase):
    def test_pinned_hook_idempotence_and_alteration_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();p=root/'src/x6502.c'
            p.write_text('#include "sound.h"\n'+BEGIN+'\n'+END)
            self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            p.write_text(p.read_text().replace(POST,'changed'))
            with self.assertRaises(ValueError):instrument(root)

    def test_missing_or_duplicate_anchor_does_not_partially_install(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();p=root/'src/x6502.c'
            for text in ('unknown','#include "sound.h"\n'+BEGIN+'\n'+END+'\n'+BEGIN):
                p.write_text(text)
                with self.assertRaises(ValueError):instrument(root)
                self.assertEqual(p.read_text(),text);self.assertFalse((root/'src/n2s_timeline_probe.h').exists())

    def test_compiled_c99_harness_layout_stimuli_and_completion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'observer.h').write_bytes(HEADER.read_bytes())
            (root/'test.c').write_text(r'''
#include <stdint.h>
#include <assert.h>
#define FCEU_IQEXT 1
#define FCEU_IQNMI 2
static unsigned requests;
static uint8_t image[65536],*Page[32];
static void X6502_IRQBegin(unsigned a){requests|=a;}
static void X6502_IRQEnd(unsigned a){requests&=~a;}
static void TriggerNMI(void){requests|=FCEU_IQNMI;}
#include "observer.h"
int main(void){
 unsigned i;uint8_t ram[512]={0};tl_event es[3]={{1,1,0,{0,0}},{2,0,1,{0,0}},{3,1,0,{0,0}}};
 for(i=0;i<32;i++)Page[i]=image;
 image[0xFFFA]=0;image[0xFFFB]=0x90;
 assert(sizeof(tl_row)==544 && sizeof(tl_event)==8);
 assert(retro_n2s_timeline_configure(0x8000,2,es,3));
 tl_before(0x8000,0,0,0,4,255,100,0,ram);tl_after(0xEA,104);
 assert(tl_event_index==3 && requests==3);
 requests=1;tl_before(0x9000,0,0,0,4,252,111,requests,ram);
 assert(tl_rows[1].entry==7 && tl_rows[1].kind==2 && tl_rows[1].cost==4);
 tl_after(0xEA,113);tl_before(0x9001,0,0,0,4,252,113,requests,ram);
 assert(!tl_active && tl_count==3 && !tl_error);
 es[1].cycle=es[0].cycle;assert(!retro_n2s_timeline_configure(0x8000,2,es,3));
 assert(!tl_active && !tl_count);
 assert(!retro_n2s_timeline_configure(0x8000,113,0,0));
 assert(retro_n2s_timeline_configure(0x8000,1,0,0));
 tl_before(0x8000,0,0,0,4,255,100,0,ram);tl_after(0xEA,104);
 tl_before(0x9000,0,0,0,4,252,112,0,ram);assert(tl_error==3);
 return 0;
}
''')
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
