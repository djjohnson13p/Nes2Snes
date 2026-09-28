"""Strict set selection, serialized-bank fields, and final-state provenance."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from chr_sets import PROFILE, validate, underlying, boot_code, initial, create_nes, create_native, register_b
from chr_sets_fixture import cases, switching, guard_cases
from chr_sets_state import decode_sets, native_registers
from palette_state import decode, decode_mmc5
from oam_state import _chunks
from verify_chr_sets import compare_registers, run


def chunk(tag,raw):return tag+len(raw).to_bytes(4,'little')+raw


def snapshot(reg=None,ctrl=0x20,pc=0xE100):
    r=bytearray(11);r[0]=ctrl;r[3:7]=b'\x00\x21\x00\x21'
    cpu=chunk(b'REG\0',pc.to_bytes(2,'little')+bytes.fromhex('fd5a030334'))+chunk(b'RAM\0',b'\0'+bytes(2048))
    ppu=chunk(b'REG\0',r)+chunk(b'PAL\0',b'\0'+bytes(32))+chunk(b'NMT\0',b'\0'+bytes(2048))+chunk(b'OAM\0',b'\0'+bytes(256))
    if reg is None:
        reg=bytearray(32);reg[0]=0x2F;reg[22]=0x82
    mm5=chunk(b'REG\0',reg)+chunk(b'RAM\0',b'\0'+bytes(1024))
    image=chunk(b'MPR\0',chunk(b'MM5\0',mm5))
    return chunk(b'NST\x1a',chunk(b'CPU\0',cpu)+chunk(b'PPU\0',ppu)+chunk(b'IMG\0',image))


def native_state():
    b=bytearray(9);b[8]=1
    context=bytearray(28);context[26]=2
    row=bytearray(48);row[0]=3;row[1]=2;row[34:43]=b
    return dict(chr_set_b=b.hex(),ppu_chr_context=context.hex(),chr_records=[row.hex()],completed_steps=1)


class ChrSetStateTests(unittest.TestCase):
    def test_default_decoder_keeps_8x16_guard(self):
        with self.assertRaises(ValueError):decode(snapshot())
        with self.assertRaises(ValueError):decode_mmc5(snapshot())
        self.assertEqual(bytes.fromhex(decode(snapshot(),sprite_16=True)['ppu_state'])[0],0x20)

    def test_sprite_gate_must_be_boolean(self):
        for value in (1,None,'yes'):
            with self.assertRaises(ValueError):decode(snapshot(),sprite_16=value)
            with self.assertRaises(ValueError):decode_mmc5(snapshot(),sprite_16=value)

    def test_new_profile_requires_8x16_and_refuses_nmi(self):
        for ctrl in (0,0x40,0x80,0x60,0xA0):
            with self.assertRaises(ValueError):decode_sets(snapshot(ctrl=ctrl))

    def test_each_serialized_high_bit_has_its_own_register(self):
        for i in range(12):
            for high in range(4):
                reg=bytearray(32);reg[0]=0x2F
                if i<8:reg[7+i]=0xA5;reg[19+i//4]=high<<(2*(i%4))
                else:reg[15+i-8]=0xA5;reg[21]=high<<(2*(i-8))
                result=bytes.fromhex(decode_sets(snapshot(reg))['chr_set_registers'])
                words=[int.from_bytes(result[3+2*k:5+2*k],'little') for k in range(12)]
                self.assertEqual(words[i],0xA5+256*high)
                self.assertEqual(sum(bool(v) for v in words),1)

    def test_last_set_upper_latch_and_mode_decoded_from_raw_registers(self):
        for mode in range(4):
            for upper in range(4):
                for last in range(2):
                    r=bytearray(32);r[0]=0x20|(mode<<2);r[22]=upper|(last<<7)
                    image=bytes.fromhex(decode_sets(snapshot(r))['chr_set_registers'])
                    self.assertEqual(image[:3],bytes((mode,upper,last)))

    def test_malformed_unknown_and_missing_serialized_state_rejected(self):
        r=bytearray(32);r[0]=0x2F;r[22]=0x40
        for raw in (snapshot(r),snapshot()[:-1],snapshot()+b'x',b''):
            with self.assertRaises(ValueError):decode_sets(raw)
        raw=snapshot();root=_chunks(raw[8:]);image=chunk(b'NST\x1a',chunk(b'CPU\0',root[b'CPU\0'])+chunk(b'PPU\0',root[b'PPU\0']))
        with self.assertRaises(ValueError):decode_sets(image)

    def test_native_and_reference_registers_agree(self):
        compare_registers(decode_sets(snapshot()),native_state())
        self.assertEqual(len(native_registers(native_state())),27)

    def test_final_bank_state_is_bound_to_retired_record(self):
        for key,pos in (('chr_set_b',0),('chr_set_b',8),('ppu_chr_context',16),('ppu_chr_context',24),('ppu_chr_context',26)):
            state=native_state();data=bytearray.fromhex(state[key]);data[pos]^=1;state[key]=data.hex()
            with self.assertRaises(ValueError):native_registers(state)

    def test_impossible_high_bits_last_set_and_padding_rejected(self):
        for pos in (1,3,5,7,8):
            state=native_state();data=bytearray.fromhex(state['chr_set_b']);data[pos]=4;state['chr_set_b']=data.hex()
            with self.assertRaises(ValueError):native_registers(state)
        state=native_state();r=bytearray.fromhex(state['chr_records'][0]);r[43]=1;state['chr_records']=[r.hex()]
        with self.assertRaises(ValueError):native_registers(state)

    def test_missing_whitespace_shortened_or_wrong_count_cannot_pass(self):
        for key,value in (('chr_set_b',None),('chr_set_b','00'*8+'  '),('completed_steps',True),('completed_steps',2),('chr_records',[])):
            with self.assertRaises(ValueError):native_registers(dict(native_state(),**{key:value}))

    def test_changed_reference_byte_is_not_tolerated(self):
        ref=decode_sets(snapshot());raw=bytearray.fromhex(ref['chr_set_registers']);raw[3]^=1;ref['chr_set_registers']=raw.hex()
        with self.assertRaises(RuntimeError):compare_registers(ref,native_state())


class ChrSetProfileTests(unittest.TestCase):
    def plan(self):return switching(3,5,'ba',0x59,3,1024)

    def test_explicit_profile_does_not_mutate_input(self):
        p=self.plan();copy_p=copy.deepcopy(p)
        self.assertIs(validate(p),p);self.assertEqual(underlying(p)['memory_model'],'mmc5-oam-blank')
        self.assertEqual(p,copy_p)
        with self.assertRaises(ValueError):validate(underlying(p))

    def test_malformed_plan_values_rejected(self):
        for k,v in (('chr_banks',True),('chr_mode',4),('steps',32),('extra',1),('name','../escape')):
            with self.assertRaises(ValueError):validate(dict(self.plan(),**{k:v}))

    def test_guest_event_injection_is_not_admitted(self):
        p=self.plan();p['events']=[dict(cycle=1,irq=False,nmi=True)]
        with self.assertRaises(ValueError):validate(p)

    def test_b_register_address_validation(self):
        for address in (True,0x5127,0x512C,'5128'):
            with self.assertRaises(ValueError):register_b(address)
        self.assertIn('CS_B+6',register_b(0x512B))

    def test_boot_fits_reserved_region_and_ends_in_return(self):
        for mode in range(4):
            raw=boot_code(mode);self.assertLessEqual(len(raw),512);self.assertEqual(raw[-1],0x60)
            self.assertIn(bytes.fromhex('a9208d0020'),raw)

    def test_matrix_has_unique_programs_and_all_declared_modes_capacities(self):
        plans=cases()
        self.assertEqual(len(plans),len({p['name'] for p in plans}))
        self.assertEqual(len(plans),len({(p['code'],p['chr_mode'],p['chr_banks']) for p in plans}))
        self.assertEqual({p['chr_mode'] for p in plans},set(range(4)))
        self.assertEqual({p['chr_banks'] for p in plans},{1<<i for i in range(3,11)})
        self.assertTrue(all(not p['events'] for p in plans))

    def test_guards_are_admitted_and_have_real_original_prefixes(self):
        self.assertEqual(len(guard_cases()),5)
        for p,pc,n in guard_cases():
            self.assertIs(validate(p),p);self.assertEqual(p['starts'][n],pc)

    def test_generated_original_cartridge_matches_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=switching(0,7,'ba',0x59,0,8)
            nes=create_nes(root/'nes',p).read_bytes()
            snes=create_native(root/'snes',p,initial(p)).read_bytes()
            length=p['prg_banks']*8192
            self.assertEqual(snes[32768:32768+length],nes[16:16+length])
            program=(root/'snes/program.inc').read_text()
            self.assertIn('sta f:CS_LAST',program)
            self.assertIn('cmp #$20',(root/'snes/mmc5_ppu_blank.inc').read_text())
            self.assertIn('.proc ChrBankA',(root/'snes/mmc5_chr_blank.inc').read_text())
            self.assertNotIn('CR+11',program)

    def test_host_stack_snapshot_is_unchanged(self):
        import oam_ports
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=switching(3,0,'ab',banks=8)
            create_native(root/'new',p,initial(p),host_mode='nested')
            oam_ports.create_native(root/'old',underlying(p),initial(p),host_mode='nested')
            self.assertEqual((root/'new/timeline_host_nmi.inc').read_bytes(),(root/'old/timeline_host_nmi.inc').read_bytes())

    def test_unfinished_smoke_and_invalid_workers_do_not_claim_a_matrix(self):
        for jobs in (True,0,5,1.5):
            with self.assertRaises(ValueError):run(None,None,Path('unused'),jobs=jobs)
        for limit in (True,0,len(cases())+1):
            with self.assertRaises(ValueError):run(None,None,Path('unused'),limit=limit)

    def test_refused_prefix_waits_through_original_initialization(self):
        import verify_chr_sets as check
        early=bytearray(32); early[0]=0
        first=snapshot(early,ctrl=0,pc=0xE000)
        class BootRunner:
            frames=0
            def __init__(self,*args):pass
            def run(self,n):self.frames+=n
            def state(self):return first if self.frames==1 else snapshot()
            def memory(self):return bytes(2048)
            def close(self):pass
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core=root/'core';rom=root/'rom'
            core.write_bytes(b'core');rom.write_bytes(b'authored')
            with patch.object(check,'Runner',BootRunner):
                check.nes_sample(core,rom,root/'result.json',0xE100)
            import json
            self.assertEqual(json.loads((root/'result.json').read_text())['frames'],2)

    def test_invalid_prefix_pc_rejected_before_core_use(self):
        from verify_chr_sets import nes_sample
        for stop in (True,-1,0x7FFF,65536):
            with self.assertRaises(ValueError):nes_sample(None,None,None,stop)

    def test_no_production_runtime_link(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('chr_sets',(root/name).read_text())


if __name__=='__main__':unittest.main()
