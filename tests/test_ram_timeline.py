"""Opt-in addressing contract and full-memory evidence gates."""
from pathlib import Path
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ram_timeline_fixture import cases, fault_cases, memory_case, edge_cases
from timeline_program import decode, validate_plan, memory_bytes, create_native, generate
from timeline_fixture import expected_initial, cases as old_cases
from timeline_ram import access, jump
from verify_timeline import compare, sample_native
from verify_host_nmi import sample
from verify_ram_timeline import unchanged_on_fault
from instrument_timeline_probe import instrument, HEADER, BEGIN, END


class RamTimelineTests(unittest.TestCase):
    def test_all_authored_plans_validate_and_no_expected_rows_are_inputs(self):
        plans=cases();self.assertEqual(len(plans),214)
        for p in plans:
            validate_plan(p);self.assertEqual(len(expected_initial(p)),2080)
            self.assertEqual(memory_bytes(p),2048)
            self.assertNotIn('records',p)
        for p in fault_cases():validate_plan(p)

    def test_high_index_edge_inputs_are_declared_and_bounded(self):
        rows=edge_cases();self.assertEqual(len(rows),30)
        self.assertEqual({p['x'] for p in rows},{1,127,128,254,255})
        for p in rows:validate_plan(p)
        for invalid in (True,-1,256):
            with self.assertRaises(ValueError):memory_case(0xBD,1,index_override=invalid)

    def test_extension_is_explicit_and_old_contract_still_rejects_indexing(self):
        for raw in (bytes.fromhex('bd0000'),bytes.fromhex('b1ff'),bytes.fromhex('6cff02')):
            with self.assertRaises(ValueError):decode(raw,0x8000,[0x8000])
            self.assertEqual(len(decode(raw,0x8000,[0x8000],ram=True)),1)
        self.assertEqual(memory_bytes(old_cases()[0]),512)

    def test_bad_profile_boolean_gate_and_capture_capacity_rejected(self):
        p=memory_case(0xBD,1)
        for value in (None,True,'all-memory'):
            with self.assertRaises(ValueError):validate_plan(dict(p,memory_model=value))
        for value in (32,112,True):
            with self.assertRaises(ValueError):validate_plan(dict(p,steps=value))
        with self.assertRaises(ValueError):decode(b'\xea',0x8000,[0x8000],ram=1)

    def test_io_rom_brk_and_unsupported_opcodes_remain_excluded(self):
        for raw in (bytes.fromhex('ad0020'),bytes.fromhex('8dffff'),bytes.fromhex('6c0020'),b'\x00',b'\x02'):
            with self.assertRaises(ValueError):decode(raw,0x8000,[0x8000],ram=True)

    def test_full_mirrors_allowed_but_no_native_raw_access_emitted(self):
        text=generate(bytes.fromhex('adc018'),0x8000,[0x8000],ram=True)
        self.assertIn('jsr TimelineResolveRAM',text)
        self.assertIn('<MR_VALUE,>MR_VALUE',text)
        self.assertNotIn('.byte $AD,$C0,$18',text)

    def test_nmos_jump_wrap_uses_pointer_page_not_next_linear_address(self):
        text=jump(0x02FF);self.assertIn('lda $02FF',text);self.assertIn('lda $0200',text)
        text=jump(0x1FFF);self.assertIn('lda $07FF',text);self.assertIn('lda $0700',text)
        for invalid in (True,-1,0x2000):
            with self.assertRaises(ValueError):jump(invalid)

    def test_real_assembler_and_profile_shapes(self):
        p=memory_case(0x91,1)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);rom=create_native(out,p,expected_initial(p),host_mode='loaded')
            self.assertEqual(rom.stat().st_size,65536)
            self.assertIn('cpx #2048',(out/'fixture.s').read_text())
            self.assertEqual((out/'initial-ram.bin').stat().st_size,2048)
            self.assertTrue((out/'timeline_ram.inc').is_file())

    def test_default_binary_isolation(self):
        p=old_cases()[0]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);create_native(out,p,expected_initial(p))
            self.assertFalse((out/'timeline_ram.inc').exists())
            self.assertNotIn('TimelineResolveRAM',(out/'program.inc').read_text())
        root=Path(__file__).resolve().parents[1]
        self.assertNotIn('timeline_ram',(root/'tools/build_native.py').read_text())
        self.assertNotIn('timeline_ram',(root/'snes/src/native.s').read_text())

    def inputs(self):
        p=memory_case(0xBD,1);p['steps']=1
        initial=expected_initial(p);end=bytearray(initial)
        struct.pack_into('<I',end,0,2);struct.pack_into('<H',end,4,p['origin']+1)
        end[9]&=~4;end[14]=2;end[17]=0x58;struct.pack_into('<H',end,18,1)
        return p,dict(name=p['name'],complete=True,records=[initial.hex(),end.hex()]),dict(complete=True,marker=90,status=0,completed_steps=1,records=[end.hex()])

    def test_full_2k_comparison_and_high_memory_mutation(self):
        p,r,n=self.inputs();self.assertEqual(compare(p,r,n)['record_bytes'],2080)
        for off in (32+0x200,32+0x700,2079):
            wrong=copy.deepcopy(n);data=bytearray.fromhex(wrong['records'][0]);data[off]^=1;wrong['records'][0]=data.hex()
            with self.assertRaises(RuntimeError):compare(p,r,wrong)

    def test_old_512_byte_capture_cannot_certify_2k(self):
        p,r,n=self.inputs();n['records'][0]=n['records'][0][:544*2]
        with self.assertRaises(ValueError):compare(p,r,n)

    def test_fault_free_prefix_cannot_pass_a_faulted_access(self):
        p,r,n=self.inputs();n['status']=5
        with self.assertRaises(ValueError):compare(p,r,n)

    def test_sampler_rejects_overflow_before_loading_core(self):
        for b,s in ((2048,32),(512,0),(True,1)):
            with self.assertRaises(ValueError):sample_native(Path('absent'),Path('absent'),Path('unused'),s,ram_bytes=b)
            with self.assertRaises(ValueError):sample(Path('absent'),Path('absent'),Path('unused'),s,ram_bytes=b)

    def test_before_access_fault_gate_rejects_changed_memory_or_clock(self):
        p,r,n=self.inputs();p['steps']=31
        before=bytes.fromhex(n['records'][0]);context=bytearray(32);context[:14]=before[:14];context[14]=5
        failure=dict(marker=0xEE,status=5,completed_steps=1,records=[before.hex()],final_guest_ram=before[32:].hex(),final_guest_context=context.hex())
        self.assertTrue(unchanged_on_fault(p,failure)['rejected'])
        for field,off in (('final_guest_ram',0x7FF),('final_guest_context',0)):
            bad=copy.deepcopy(failure);data=bytearray.fromhex(bad[field]);data[off]^=1;bad[field]=data.hex()
            with self.assertRaises(ValueError):unchanged_on_fault(p,bad)

    def test_capture_profile_installation_is_explicit_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();path=root/'src/x6502.c'
            path.write_text('#include "sound.h"\n'+BEGIN+'\n'+END)
            self.assertTrue(instrument(root,ram_bytes=2048));self.assertFalse(instrument(root,ram_bytes=2048))
            self.assertTrue((root/'src/n2s_timeline_probe.h').read_bytes().startswith(b'#define TL_RAM_BYTES 2048\n'))
            with self.assertRaises(ValueError):instrument(root,ram_bytes=512)
        for invalid in (True,0,1024):
            with self.assertRaises(ValueError):instrument(Path('absent'),ram_bytes=invalid)

    def test_compiled_profile_copies_last_byte_without_overflow(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'probe.h').write_bytes(HEADER.read_bytes())
            (root/'test.c').write_text(r'''
#include <assert.h>
#include <stdint.h>
#define TL_RAM_BYTES 2048
#define FCEU_IQEXT 1
#define FCEU_IQNMI 2
uint8_t *Page[32];
void X6502_IRQBegin(unsigned v){(void)v;}
void X6502_IRQEnd(unsigned v){(void)v;}
void TriggerNMI(void){}
#include "probe.h"
int main(void){uint8_t ram[2048]={0};ram[2047]=0xA7;
assert(sizeof(tl_row)==2080);assert(retro_n2s_timeline_configure(0x8000,1,0,0));
tl_before(0x8000,1,2,3,0x24,255,0,0,ram);
tl_after(0xEA,2);tl_before(0x8001,1,2,3,0x24,255,2,0,ram);
assert(tl_count==2 && tl_rows[1].ram[2047]==0xA7 && !tl_error && !tl_active);return 0;}
''')
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)
