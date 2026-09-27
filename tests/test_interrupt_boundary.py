"""Interrupt entry contract, real assembly and independent-output negative tests."""
from dataclasses import replace
from pathlib import Path
import copy
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from interrupt_boundary import Boundary, SUPPORTED, enter
from interrupt_fixture import cases,native_fixture
from verify_interrupt_boundary import check_native,expected,Observation
from instrument_interrupt_probe import instrument,BEGIN,END,PRE,POST,HEADER


class BoundaryTests(unittest.TestCase):
    def state(self,**changes):
        return replace(Boundary(0xEA,0x38,0x38,False,False,0xFF,0xABCD,0x9000,0xA000),**changes)

    def test_no_request_preserves_every_guest_byte(self):
        b=self.state();stack=bytes(range(256));out,page=enter(b,stack)
        self.assertEqual(out,b.record());self.assertEqual(page,stack)

    def test_nmi_priority_and_latch_consumption(self):
        out,page=enter(self.state(irq=True,nmi=True),bytes(256))
        self.assertEqual(out[8:10],bytes((2,7)));self.assertEqual(out[3:5],bytes((1,0)))
        self.assertEqual(out[6:8],bytes.fromhex('00a0'));self.assertEqual(page[253:256],bytes.fromhex('28cdab'))

    def test_irq_obeys_mask_without_consuming_level(self):
        for mask in (0,4):
            out,page=enter(self.state(after_p=mask,irq=True),bytes(256))
            self.assertEqual(out[8],0 if mask else 1);self.assertEqual(out[3],1)
            self.assertEqual(out[9],0 if mask else 7)

    def test_cli_sei_plp_use_before_i(self):
        for opcode in (0x58,0x78,0x28):
            for before,after in ((4,0),(0,4)):
                out,_=enter(self.state(opcode=opcode,before_p=before,after_p=after,irq=True),bytes(256))
                self.assertEqual(out[8],0 if before else 1)

    def test_rti_uses_restored_i(self):
        for before,after in ((4,0),(0,4)):
            out,_=enter(self.state(opcode=0x40,before_p=before,after_p=after,irq=True),bytes(256))
            self.assertEqual(out[8],0 if after else 1)

    def test_all_flag_values_preserve_decimal_and_push_b_clear(self):
        for p in range(256):
            out,page=enter(self.state(after_p=p,nmi=True),bytes(256))
            self.assertEqual(out[2],p|4);self.assertEqual(page[253],(p&0xEF)|0x20)

    def test_all_stack_positions_wrap_inside_page_one(self):
        for s in range(256):
            out,page=enter(self.state(s=s,nmi=True),bytes(range(256)))
            self.assertEqual(out[5],(s-3)&255)
            expected=bytearray(range(256))
            for offset,value in enumerate((0xAB,0xCD,0x28)):expected[(s-offset)&255]=value
            self.assertEqual(page,expected)

    def test_return_pc_uses_completed_instruction_pc(self):
        for pc in (0,1,0xFFFF):
            _,page=enter(self.state(pc=pc,nmi=True),bytes(256))
            self.assertEqual(page[254],pc&255);self.assertEqual(page[255],pc>>8)

    def test_nmi_ignores_irq_mask(self):
        out,_=enter(self.state(before_p=4,after_p=4,nmi=True),bytes(256))
        self.assertEqual(out[8],2)

    def test_brk_and_every_undocumented_opcode_rejected(self):
        self.assertEqual(len(SUPPORTED),150)
        for opcode in set(range(256))-SUPPORTED:
            with self.assertRaises(ValueError):self.state(opcode=opcode).record()

    def test_bad_boolean_and_address_types_rejected(self):
        for key,value in (('opcode',True),('before_p',-1),('after_p',256),('irq',1),('nmi',0),('s',False),('pc',65536),('irq_vector',True),('nmi_vector',-1)):
            with self.subTest(key=key),self.assertRaises(ValueError):self.state(**{key:value}).record()

    def test_stack_must_be_complete_immutable_bytes(self):
        for stack in (bytes(255),bytes(257),bytearray(256),None):
            with self.assertRaises(ValueError):enter(self.state(),stack)

    def test_all_valid_opcodes_have_fixture_evidence(self):
        plan=cases();self.assertEqual({r['opcode'] for r in plan},set(SUPPORTED))
        self.assertEqual(len(plan),1712);self.assertEqual(len({r['name'] for r in plan}),len(plan))
        self.assertEqual({r['initial_s'] for r in plan},set(range(256)))
        self.assertTrue(all('expected' not in r and 'next_p' not in r for r in plan))

    def test_actual_assembly_and_runtime_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            native_fixture(Path(folder),[(self.state().record(),bytes(256))])
        root=Path(__file__).resolve().parents[1]
        for path in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('guest_interrupt',(root/path).read_text())

    def test_fixture_shape_rejected_before_writing(self):
        for records in ([],[(bytes(15),bytes(256))],[(bytes(16),bytes(255))],[(bytes(16),bytes(256))]*65):
            with self.assertRaises(ValueError):native_fixture(Path('unused'),records)

    def test_native_comparator_detects_descriptor_stack_and_host_changes(self):
        values=enter(self.state(nmi=True),bytes(256))
        context=bytes.fromhex('34127856cdab55037e4df01f');out=values[0]+values[1]+context
        check_native([values],{'records':[out.hex()]})
        for offset in (0,2,5,8,9,10,16,269,271,272,283):
            bad=bytearray(out);bad[offset]^=1
            with self.assertRaises(RuntimeError):check_native([values],{'records':[bad.hex()]})

    def test_missing_or_extra_native_records_rejected(self):
        values=enter(self.state(),bytes(256))
        for records in ([],['00','00']):
            with self.assertRaises(RuntimeError):check_native([values],{'records':records})

    def test_reference_comparator_requires_complete_independent_record(self):
        row=dict(opcode=0xEA,irq=False,nmi=False,name='none')
        obs=dict(before_p=0x34,after_p=0x34,next_p=0x34,s=255,next_s=255,pc=0x8101,next_pc=0x8101,
                 a=1,x=2,y=3,next_a=1,next_x=2,next_y=3,complete=1,boundary_time=100,next_time=100,
                 before_stack=bytes(256).hex(),after_stack=bytes(256).hex())
        expected(row,{'observation':obs})
        for key,value in (('boundary_time',-1),('next_time',True),('extra',0),('complete',False),('next_time',101),('next_pc',0x8123),('next_a',9),('next_p',0),('after_stack',bytes([1])*256)):
            bad=dict(obs,**{key:value.hex() if isinstance(value,bytes) else value})
            with self.subTest(key=key),self.assertRaises(RuntimeError):expected(row,{'observation':bad})


class ProbeTests(unittest.TestCase):
    def seed(self,root):
        (root/'src').mkdir();(root/'src/x6502.c').write_text('#include "sound.h"\n'+BEGIN+'\n'+END)

    def test_install_is_exact_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            text=(root/'src/x6502.c').read_text();self.assertEqual(text.count(PRE),1);self.assertEqual(text.count(POST),1)

    def test_changed_anchor_rejected_without_partial_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);p=root/'src/x6502.c';text=p.read_text().replace(END,'different');p.write_text(text)
            with self.assertRaises(ValueError):instrument(root)
            self.assertEqual(p.read_text(),text);self.assertFalse((root/'src/n2s_interrupt_probe.h').exists())

    def test_changed_installed_header_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);instrument(root);(root/'src/n2s_interrupt_probe.h').write_text('changed')
            with self.assertRaises(ValueError):instrument(root)

    def test_changed_hook_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);instrument(root);p=root/'src/x6502.c';p.write_text(p.read_text().replace(POST,'changed'))
            with self.assertRaises(ValueError):instrument(root)

    def test_compiled_harness_changes_requests_not_guest_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'probe.h').write_bytes(HEADER.read_bytes())
            (root/'probe.c').write_text(r'''
#include <assert.h>
static int irq_count,nmi_count;
#define FCEU_IQEXT 1
static void X6502_IRQBegin(int w){assert(w==1);irq_count++;}
static void TriggerNMI(void){nmi_count++;}
#include "probe.h"
int main(void){
 uint8_t ram[2048],copy[2048];unsigned i;
 for(i=0;i<2048;i++)ram[i]=(uint8_t)i;
 memcpy(copy,ram,2048);
 assert(sizeof(n2s_interrupt_row)==544);
 assert(!retro_n2s_interrupt_configure(0x8000,0xea,2,0));
 assert(retro_n2s_interrupt_configure(0x8000,0xea,1,1));
 n2s_ib_before(0x8000,0x34,255,1,2,3,100,ram);
 n2s_ib_after(0xea,0x8001,0x34,255,1,2,3,102,ram);
 assert(irq_count==1 && nmi_count==1 && !memcmp(copy,ram,2048));
 n2s_ib_before(0xa000,0x34,252,1,2,3,109,ram);
 assert(n2s_ib_row.complete && n2s_ib_row.pc==0x8001 && n2s_ib_row.next_pc==0xa000);
 assert(n2s_ib_row.next_time-n2s_ib_row.boundary_time==7);
 assert(!memcmp(n2s_ib_row.before_stack,ram+256,256));
 assert(retro_n2s_interrupt_configure(0x8000,0xea,0,0));
 n2s_ib_before(0x8000,0,255,0,0,0,100,ram);
 n2s_ib_after(0x58,0x8001,0,255,0,0,0,102,ram);
 assert(retro_n2s_interrupt_status(1)==1 && !retro_n2s_interrupt_status(0));
 return 0;
}
''')
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'probe.c'),'-o',str(root/'probe')],check=True)
            subprocess.run([str(root/'probe')],check=True)


if __name__=='__main__':unittest.main()
