"""CPU I/O profile contracts, independent snapshot integrity and old gates."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mmc5_cpu_io import validate,register_code,jump,initial_exram,create_native,PROFILE
from mmc5_cpu_io_fixture import cases,access_case,transition_case,fault_cases
from timeline_program import decode,memory_bytes
from timeline_fixture import expected_initial
from verify_cpu_io_timeline import check_exram
from timeline_host import PROTECTED


class CPUIOTests(unittest.TestCase):
    def test_explicit_profile_is_required(self):
        p=access_case(0xAD);p['memory_model']='mmc5-prg-ram32'
        with self.assertRaises(ValueError):validate(p)
        for kw in ({},{'ram':True,'rom':True,'mapper':True,'cartridge_ram':True}):
            with self.assertRaises(ValueError):decode(bytes.fromhex('ad005c'),0xE100,[0xE100],**kw)

    def test_both_parent_gates_required(self):
        for kw in ({'cpu_io':True},{'cpu_io':1},{'cpu_io':True,'mapper':True}):
            with self.assertRaises(ValueError):decode(b'\xea',0xE100,[0xE100],**kw)

    def test_complete_fixture_and_initial_state(self):
        p=access_case(0xAD);self.assertIs(validate(p),p)
        self.assertEqual(memory_bytes(p),2048)
        initial=expected_initial(p);self.assertEqual(len(initial),2080)
        self.assertEqual(initial[28:32],bytes((3,0,0,0)))
        self.assertEqual(initial_exram(),b'\xa5'*1024)

    def test_every_external_memory_form_is_declared(self):
        from timeline_program import REGULAR
        from opcodes6502 import OPS
        forms={op for op,(n,m,_) in OPS.items() if n in REGULAR and m in ('abs','absx','absy','ix','iy')}
        planned=cases();self.assertEqual(len({p['name'] for p in planned}),len(planned))
        self.assertEqual({int(p['name'].split('-')[2],16) for p in planned if p['name'].startswith('ex-access')},forms)
        self.assertEqual(len(forms),61)
        for p in planned:self.assertIs(validate(p),p)

    def test_only_supported_direct_register_operations(self):
        kw=dict(ram=True,rom=True,mapper=True,cartridge_ram=True,cpu_io=True)
        for raw in ('ad0451','ee0552','8e0552','8d0551'):
            with self.assertRaises(ValueError):decode(bytes.fromhex(raw),0xE100,[0xE100],**kw)
        for raw in ('8d0451','ad0552','ad0652','8d0552','8d0652'):
            self.assertTrue(decode(bytes.fromhex(raw),0xE100,[0xE100],**kw))

    def test_wrong_codegen_operations_rejected(self):
        for name,address in (('LDA',0x5104),('STA',0x5204),('INC',0x5205)):
            with self.assertRaises(ValueError):register_code(name,address)

    def test_mode_mask_and_guard_precede_state_write(self):
        text=register_code('STA',0x5104)
        self.assertLess(text.index('and #3'),text.index('cmp #2'))
        self.assertLess(text.index('jmp fault'),text.index('sta EX_MODE'))

    def test_indirect_pointer_wrap(self):
        text=jump(0x5CFF)
        self.assertIn('#$5CFF',text);self.assertIn('#$5C00',text)
        self.assertNotIn('#$5D00',text)
        for address in (True,-1,0x2000,0x5BFF,65536):
            with self.assertRaises(ValueError):jump(address)

    def test_full_exram_snapshots_required(self):
        a=dict(initial_exram=initial_exram().hex(),exram=initial_exram().hex());b=dict(exram=initial_exram().hex())
        self.assertEqual(check_exram(a,b)['exram_bytes_checked'],1024)
        for bad in ({},{'exram':False},{'exram':'00'},{'exram':'xx'*1024},{'exram':'00  '*512}):
            with self.assertRaises(ValueError):check_exram(a,bad)

    def test_mutated_initial_or_final_snapshot_rejected(self):
        good=initial_exram().hex();bad='00'+good[2:]
        with self.assertRaises(ValueError):check_exram(dict(initial_exram=bad,exram=good),dict(exram=good))
        with self.assertRaises(RuntimeError):check_exram(dict(initial_exram=good,exram=good),dict(exram=bad))

    def test_guard_cases_are_present(self):
        guards=fault_cases();self.assertEqual(len(guards),6)
        for p in guards:self.assertIs(validate(p),p)

    def test_native_assembly_state_and_profile_isolation(self):
        p=transition_case();root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);create_native(out,p,expected_initial(p),host_mode='nested')
            source=(out/'mmc5_prg.inc').read_text()
            for symbol,address in [('EX_MODE',0x18D8),('EX_MUL',0x18D9),('EX_PRODUCT',0x18DC)]:
                self.assertIn(f'{symbol}=${address:04X}',source)
                self.assertTrue(any(a<=address and address+2<=a+n for a,n in PROTECTED))
            self.assertIn('cmp #2\n    bne locked',source)
        for path in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('mmc5_cpu_io',(root/path).read_text())

    def test_existing_profile_native_binary_unchanged(self):
        # The generated baseline hash is pinned to the restored PR16 source.
        from mmc5_wram_fixture import protection_case
        from mmc5_wram import create_native as old_create
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            p=protection_case(2,1)
            rom=old_create(Path(d),p,expected_initial(p))
            self.assertEqual(hashlib.sha256(rom.read_bytes()).hexdigest(),BASELINE_HASH)


# Filled from an independent build of the unchanged, restored source tree.
BASELINE_HASH='4b581aad752b83ec24d052a46b73c417b1541f96e86d2ebad74d84661638532a'

if __name__=='__main__':unittest.main()
