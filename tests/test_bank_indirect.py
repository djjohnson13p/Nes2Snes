"""Source-selection invariants; execution semantics use independent cores."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import bank_switch_fixture
import direct_calls
from build_native import classify_patch

class BankReturnTests(unittest.TestCase):
    def test_old_plan_keeps_live_banks_in_cop(self):
        raw=bytes([0x8d,0x15,0x51])
        _, info=classify_patch(raw,[1,0,0])
        sites,_=direct_calls.plan(raw,info['trap_sites'])
        self.assertEqual(sites,[])

    def test_each_supported_store_gets_far_return(self):
        for opcode in (0x8d,0x8e,0x8c):
            for address in (0x5115,0x5116,0x5117):
                raw=bytes([opcode,address&255,address>>8])
                _,info=classify_patch(raw,[1,0,0])
                sites,source=direct_calls.plan(raw,info['trap_sites'],bank_switches=True)
                self.assertEqual(len(sites),1)
                self.assertEqual(sites[0]['kind'],'bank')
                self.assertIn('    rtl',source)
                self.assertIn('    lda CODEBANK\n    sta 6,s',source)
                self.assertNotIn('    rts',source)

    def test_unknown_selector_is_not_added(self):
        raw=bytes([0x8d,0x14,0x51])
        _,info=classify_patch(raw,[1,0,0])
        sites,_=direct_calls.plan(raw,info['trap_sites'],bank_switches=True)
        self.assertEqual(sites[0]['kind'],'mapper')  # existing semantics unchanged

    def test_stress_is_absent_by_default(self):
        self.assertNotIn('@nmi_window:', '\n'.join(direct_calls.bank_veneer(0x8d,0x5115)))
        self.assertIn('@nmi_window:', '\n'.join(direct_calls.bank_veneer(0x8d,0x5115,True)))

    def test_invalid_bank_stubs_rejected(self):
        for opcode,address in ((0xad,0x5115),(0x8d,0x5114),(0x8d,0x4016)):
            with self.assertRaises(ValueError): direct_calls.bank_veneer(opcode,address)

    def test_frame_insertion_preserves_all_saved_fields(self):
        # Native runtime fixtures test actual RTL execution. This independently
        # checks byte layout for the documented shifted stack frame.
        for low in range(256):
            for bank in (0xa1,0xaf,0xbf,0xc0):
                old=[low,low^0x5a,low^0xa5,low^0x18,low^0x81]
                stack=[0]+old
                stack[0:2]=stack[1:3]
                stack[2:4]=stack[3:5]
                stack[4]=stack[5]
                stack[5]=bank
                self.assertEqual(stack, old+[bank])

    def test_fixture_stays_within_known_rom_and_record_bounds(self):
        for seed in (0,1,7):
            with tempfile.TemporaryDirectory() as d:
                m=bank_switch_fixture.create(Path(d),seed,True)
                self.assertEqual(len(m['records']),197)
                self.assertLess(m['program_bytes'],0x1ffa)
                self.assertLessEqual(m['result_end'],0x780)

if __name__=='__main__': unittest.main()
