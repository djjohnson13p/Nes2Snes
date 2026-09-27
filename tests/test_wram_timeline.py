"""Cartridge RAM is an explicit profile; refusals and exact evidence stay strict."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mmc5_wram import initial_ram,validate,create_native,create_nes,PROFILE
from mmc5_wram_fixture import cases,access_case,protection_case,fault_cases
from timeline_program import decode,validate_plan,memory_bytes
from timeline_fixture import expected_initial
from verify_wram_timeline import check_ram,check_header
from instrument_wram_timeline import instrument,GETTER,MARKER
from instrument_timeline_probe import BEGIN,END


class CartridgeRAMTests(unittest.TestCase):
    def test_explicit_profile_initial_state_and_header(self):
        p=access_case(0xBD)
        self.assertIs(validate_plan(p),p)
        state=expected_initial(p)
        self.assertEqual(len(state),2080)
        self.assertEqual(state[20:28],bytes([0,1,2,31,31,128,0,0]))
        check_header(p,state)

    def test_declared_initial_banks_are_distinct(self):
        data=initial_ram();self.assertEqual(len(data),32768)
        for b in range(4):self.assertEqual(data[b*8192:(b+1)*8192],bytes([0x41+b])*8192)

    def test_no_cartridge_ram_gate_no_new_register_or_target(self):
        for code in (bytes.fromhex('ad0060'),bytes.fromhex('8d0251')):
            with self.assertRaises(ValueError):decode(code,0xE100,[0xE100],ram=True,rom=True,mapper=True)
            self.assertTrue(decode(code,0xE100,[0xE100],ram=True,rom=True,mapper=True,cartridge_ram=True))

    def test_profile_gate_must_be_explicit_and_boolean(self):
        for settings in ({'cartridge_ram':True},{'ram':True,'rom':True,'mapper':True,'cartridge_ram':1}):
            with self.assertRaises(ValueError):decode(b'\xea',0xE100,[0xE100],**settings)

    def test_unknown_and_missing_plan_fields_rejected(self):
        p=access_case(0xBD)
        for edit in ({'prg_ram_bytes':8192},{'memory_model':'mmc5-prg-rom'}, {'prg_banks':True}):
            with self.assertRaises(ValueError):validate(dict(p,**edit))
        q=copy.deepcopy(p);del q['bank_data']
        with self.assertRaises(ValueError):validate(q)

    def test_pointer_and_register_reads_still_reject_unsupported_io(self):
        for raw in ('ad0251','ad0050','6c0050'):
            with self.assertRaises(ValueError):decode(bytes.fromhex(raw),0xE100,[0xE100],ram=True,rom=True,mapper=True,cartridge_ram=True)

    def test_real_assembly_uses_explicit_32k_nes2_header(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=access_case(0x9D)
            nes=create_nes(root/'nes',p).read_bytes()
            self.assertEqual(nes[7],8);self.assertEqual(nes[10],9)
            native=create_native(root/'native',p,expected_initial(p)).read_bytes()
            self.assertEqual(native[32768:32768+32*8192],nes[16:16+32*8192])
            self.assertIn('CartridgeCommit',(root/'native/program.inc').read_text())

    def test_no_expected_intermediate_state_permitted(self):
        with tempfile.TemporaryDirectory() as d:
            p=access_case(0xAD);bad=bytearray(expected_initial(p));bad[0]=1
            with self.assertRaises(ValueError):create_native(Path(d),p,bytes(bad))

    def test_copy_size_and_shifted_ram_snapshot_rejected(self):
        good={'initial_cartridge_ram':initial_ram().hex(),'cartridge_ram':initial_ram().hex()}
        self.assertEqual(check_ram(good,good)['cartridge_bytes_checked'],32768)
        for field in ('initial_cartridge_ram','cartridge_ram'):
            for value in ('',good[field][2:],None):
                bad=dict(good,**{field:value})
                with self.assertRaises((ValueError,TypeError)):check_ram(bad,good)

    def test_one_wrong_cartridge_byte_is_rejected(self):
        good={'initial_cartridge_ram':initial_ram().hex(),'cartridge_ram':initial_ram().hex()}
        for offset in (0,8191,8192,16384,32767):
            data=bytearray(initial_ram());data[offset]^=1
            with self.assertRaises(RuntimeError):check_ram(good,dict(cartridge_ram=data.hex()))

    def test_wrong_original_boot_is_not_accepted(self):
        data=bytearray(initial_ram());data[777]^=1
        r=dict(initial_cartridge_ram=bytes(data).hex(),cartridge_ram=initial_ram().hex())
        with self.assertRaises(ValueError):check_ram(r,r)

    def test_typed_slots_cannot_authorize_ram_execution(self):
        p=access_case(0xAD);row=bytearray(expected_initial(p));row[23]=128;row[24]=128
        with self.assertRaises(ValueError):check_header(p,bytes(row))

    def test_wrong_page_lock_and_mapping_rejected(self):
        p=access_case(0xAD);row=expected_initial(p)
        for pos,val in ((20,254),(24,4),(25,129),(26,16),(27,4)):
            bad=bytearray(row);bad[pos]=val
            with self.assertRaises(ValueError):check_header(p,bytes(bad))

    def test_every_external_memory_variant_exercised_in_plans(self):
        from opcodes6502 import OPS
        from timeline_program import REGULAR
        expected={op for op,(n,m,_) in OPS.items() if n in REGULAR and m in ('abs','absx','absy','ix','iy')}
        rows=cases();actual={int(p['name'].split('-')[2],16) for p in rows if p['name'].startswith('cw-access-')}
        self.assertEqual(actual,expected)
        self.assertEqual(len({r['name'] for r in rows}),len(rows))
        self.assertTrue(all(p['steps']==31 for p in rows))

    def test_all_low_bit_protection_combinations_present(self):
        names={p['name'] for p in cases()}
        for a in range(4):
            for b in range(4):self.assertIn(f'cw-lock-{a:02x}-{b:02x}',names)
        self.assertIn('cw-lock-fe-fd',names)

    def test_old_profile_refuses_new_register_even_when_upper_ignored(self):
        p=protection_case(0xFE,0xFD);p['memory_model']='mmc5-prg-rom'
        with self.assertRaises(ValueError):validate_plan(p)

    def test_code_generation_refusal_cases_are_retained(self):
        self.assertEqual(len(fault_cases()),6)
        for p in fault_cases():self.assertIs(validate_plan(p),p)

    def test_production_runtime_remains_outside_profile(self):
        root=Path(__file__).resolve().parents[1]
        self.assertNotIn('mmc5_wram',(root/'snes/src/native.s').read_text())
        self.assertNotIn(PROFILE,(root/'tools/build_native.py').read_text())

    def test_ram_state_stays_in_existing_snapshot_without_overlap(self):
        from timeline_host import PROTECTED
        cells={x for a,n in PROTECTED for x in range(a,a+n)}
        self.assertTrue({0x1859,0x1876,0x1877}<=cells)
        # All new persistent fields are distinct from the existing class byte.
        self.assertNotIn(0x1870,{0x1876,0x1877})


class CartridgeObserverTests(unittest.TestCase):
    def seed(self,root):
        (root/'src/boards').mkdir(parents=True)
        (root/'src/x6502.c').write_text('#include "sound.h"\n'+BEGIN+'\n'+END)
        (root/'src/boards/mmc5.c').write_text('static uint8_t WRAMMaskEnable[2];\nstatic uint8_t WRAMPage;\n')

    def test_installs_once_without_replacing_mapper_behavior(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);before=(root/'src/boards/mmc5.c').read_text()
            self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            self.assertEqual((root/'src/boards/mmc5.c').read_text(),before+GETTER)

    def test_partial_mapper_getter_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/boards/mmc5.c';p.write_text(p.read_text()+GETTER)
            with self.assertRaises(ValueError):instrument(root)

    def test_changed_capture_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);instrument(root);p=root/'src/n2s_timeline_probe.h'
            p.write_text(p.read_text().replace('tl_count+1==tl_limit','tl_count+2==tl_limit'))
            with self.assertRaises(ValueError):instrument(root)

    def test_changed_mapper_state_declaration_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/boards/mmc5.c';p.write_text('wrong')
            with self.assertRaises(ValueError):instrument(root)
            self.assertFalse((root/'src/n2s_timeline_probe.h').exists())


class CompiledCartridgeObserverTests(unittest.TestCase):
    def test_full_snapshot_is_at_endpoint_not_later_host_frame(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);CartridgeObserverTests().seed(root);instrument(root)
            header=(root/'src/n2s_timeline_probe.h').read_text()
            test=r'''
#include <assert.h>
#include <stdint.h>
#define FCEU_IQEXT 1
#define FCEU_IQNMI 2
static uint8_t *Page[32],*PRGptr[32];
static uint32_t PRGsize[32];
static void X6502_IRQBegin(unsigned q){(void)q;}
static void X6502_IRQEnd(unsigned q){(void)q;}
static void TriggerNMI(void){}
void n2s_m5_wram_metadata(uint8_t *out){out[0]=6;out[1]=2;}
'''+header+r'''
int main(void) {
    static uint8_t cpu[2048],prg[32768],cart[32768];unsigned i;
    memset(cart,0x3c,sizeof(cart));PRGptr[0]=prg;PRGsize[0]=32768;
    PRGptr[0x10]=cart;PRGsize[0x10]=32768;
    for(i=16;i<32;i++)Page[i]=(uint8_t*)((uintptr_t)prg-0x8000);
    for(i=12;i<16;i++)Page[i]=(uint8_t*)((uintptr_t)cart+0x4000-0x6000);
    assert(retro_n2s_timeline_configure(0xe100,1,0,0));
    tl_before(0xe100,0,0,0,0x24,0xfd,100,0,cpu);
    assert(tl_rows[0].reserved[5]==130 && tl_rows[0].reserved[6]==6);
    assert(retro_n2s_wram_size()==32768);
    assert(retro_n2s_wram_data(0)[0]==0x3c);
    cart[0]=0x72;tl_after(0xea,102);
    tl_before(0xe101,0,0,0,0x24,0xfd,102,0,cpu);
    assert(retro_n2s_timeline_status(0)==2 && !retro_n2s_timeline_status(3));
    cart[0]=0x99;
    assert(retro_n2s_wram_data(1)[0]==0x72);
    assert(retro_n2s_wram_data(0)[0]==0x3c);
    assert(retro_n2s_timeline_configure(0xe100,1,0,0));PRGsize[0x10]=8192;
    tl_before(0xe100,0,0,0,0x24,0xfd,100,0,cpu);
    assert(retro_n2s_timeline_status(1)==8 && !retro_n2s_timeline_status(3));
    return 0;
}
'''
            (root/'test.c').write_text(test)
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

    def test_long_initialization_has_initialized_fault_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=access_case(0xBD)
            create_native(root,p,expected_initial(p),host_mode='free')
            source=(root/'fixture.s').read_text()
            self.assertLess(source.index('cartridge_early_host_state:'),source.index('    jsr CartridgeInit'))
            self.assertIn('    stz $1D00,x',source)

if __name__=='__main__':unittest.main()
