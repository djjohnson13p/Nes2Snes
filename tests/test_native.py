"""Source-only native bridge build guards and procedural fixture tests."""
import hashlib, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_native import classify_patch
from native_cfg import expand
from native_fixture import create
from rom import Rom

class NativeTests(unittest.TestCase):
    def patch(self,data,starts):
        counts=[int(i in starts) for i in range(len(data))]
        return classify_patch(bytes(data),counts)
    def test_ordinary_instructions_remain_native(self):
        code,meta=self.patch([0xA9,0x41,0x85,0x20,0x60],{0,2,4})
        self.assertEqual(code,bytes([0xA9,0x41,0x85,0x20,0x60]))
        self.assertEqual(meta['trap_sites'],[])
    def test_unknown_bytes_fail_closed(self):
        code,_=self.patch([0xA9,0x41,0xDE,0xAD],{0})
        self.assertEqual(code,b'\xA9\x41\x00\x00')
    def test_mmio_is_intercepted_without_relocation(self):
        code,meta=self.patch([0xAD,0x02,0x20,0x8D,0x15,0x51],{0,3})
        self.assertEqual(code,b'\x02\xAD\x20\x02\x8D\x51')
        self.assertEqual(len(meta['trap_sites']),2)
    def test_cpu_ram_mirrors_are_intercepted(self):
        code,_=self.patch([0xAD,0x00,0x08],{0})
        self.assertEqual(code[:2],b'\x02\xAD')
    def test_indirect_and_zero_page_wrapping_intercepted(self):
        code,_=self.patch([0xB1,0xFF,0xB5,0xFF],{0,2})
        self.assertEqual(code,b'\x02\xB1\x02\xB5')
    def test_operand_bytes_cannot_be_instruction_starts(self):
        with self.assertRaises(ValueError):self.patch([0xA9,0xEA],{0,1})
    def test_nonreset_stack_replacement_rejected(self):
        with self.assertRaises(ValueError):self.patch([0x9A],{0})
    def test_reset_stack_is_explicitly_handled(self):
        code,meta=self.patch([0xA2,0xFF,0x9A],{0,2})
        self.assertEqual(code[-1],0xEA)
        self.assertEqual(meta['reset_txs_nop_offsets'],[2])
    def test_decimal_and_nmos_jump_corner_fail_explicitly(self):
        for data in ([0xF8],[0x6C,0xFF,0x00]):
            with self.assertRaises(ValueError):self.patch(data,{0})
    def test_cfg_distinguishes_inference_from_observation(self):
        prg=bytearray(0x40000);prg[0x3E000:0x3E006]=bytes([0xD0,2,0xA9,1,0x60,0])
        counts=[0]*len(prg);pcs=[0]*len(prg);counts[0x3E000]=1;pcs[0x3E000]=0xE000
        result,meta=expand(bytes(prg),counts,pcs)
        self.assertEqual(result[0x3E000],1)
        self.assertEqual(result[0x3E002],-1)
        self.assertEqual(result[0x3E004],-1)
        self.assertEqual(result[0x3E005],0)
        self.assertEqual(meta['statically_inferred_instruction_sites'],2)
    def test_procedural_fixture_is_reproducible_and_self_contained(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a';b=Path(d)/'b';m=create(a);create(b)
            self.assertEqual((a/'fixture.nes').read_bytes(),(b/'fixture.nes').read_bytes())
            self.assertEqual(Rom.read(a/'fixture.nes').mapper,5)
            self.assertEqual(len(m['records']),180)
            self.assertEqual(m['rom_sha256'],hashlib.sha256((a/'fixture.nes').read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
