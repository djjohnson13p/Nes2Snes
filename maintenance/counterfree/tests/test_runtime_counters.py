"""Assembly and coverage contract for the optional debug-access counters."""
import inspect
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from build_native import build
from direct_calls import bank_veneer
from verify_runtime_counters import configurations, fault_fixture


class RuntimeCounterTests(unittest.TestCase):
    def test_default_build_keeps_diagnostic_evidence(self):
        self.assertIs(inspect.signature(build).parameters['runtime_counters'].default, True)

    def test_generated_bank_veneers_use_shared_macro(self):
        for op in (0x8d, 0x8e, 0x8c):
            for addr in (0x5115, 0x5116, 0x5117):
                text = '\n'.join(bank_veneer(op, addr))
                self.assertEqual(text.count('CountRuntime $0988'), 1)
                self.assertNotIn('inc $0988', text)

    def test_macro_contains_only_counter_increment(self):
        source = (ROOT/'snes/src/native_counters.inc').read_text()
        instructions = [line.strip() for line in source.splitlines()
                        if line.startswith('        ')]
        self.assertEqual(instructions, ['inc address', 'bne :+', 'inc address+2'])

    @unittest.skipUnless(shutil.which('ca65'), 'ca65 required for encoded-byte test')
    def test_counted_assembly_is_the_original_eight_bytes(self):
        self.assertEqual(self.assemble(1), bytes.fromhex('ee6009d003ee6209'))

    @unittest.skipUnless(shutil.which('ca65'), 'ca65 required for encoded-byte test')
    def test_uncounted_assembly_emits_no_counter_bytes(self):
        self.assertEqual(self.assemble(0), b'')

    def assemble(self, enabled):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d/'test.s').write_text('.setcpu "65816"\n'
                f'USE_RUNTIME_COUNTERS={enabled}\n'
                '.include "native_counters.inc"\n.segment "CODE"\n'
                '.a16\n.i16\n.byte $42\nCountRuntime $0960\n.byte $43\n')
            (d/'test.cfg').write_text('MEMORY { M: start=$8000,size=$8000,file=%O; }\n'
                                     'SEGMENTS { CODE: load=M,type=ro; }\n')
            subprocess.run(['ca65','-I',str(ROOT/'snes/src'),'-o',str(d/'test.o'),str(d/'test.s')], check=True)
            subprocess.run(['ld65','-C',str(d/'test.cfg'),'-o',str(d/'test.bin'),str(d/'test.o')], check=True)
            data=(d/'test.bin').read_bytes()
            self.assertEqual(data[0],0x42);self.assertEqual(data[-1],0x43)
            return data[1:-1]

    def test_only_access_counters_use_macro(self):
        allowed={'$0960','$0964','$0968','$096C','$0970','$0980','$0984',
                 '$0994','$0998','QUICK_INDEXED_CALLS'}
        seen=[]
        for name in ('native.s','native_direct.inc','native_indexed.inc'):
            for line in (ROOT/'snes/src'/name).read_text().splitlines():
                if line.strip().startswith('CountRuntime '):
                    seen.append(line.strip().split()[1])
        self.assertEqual(len(seen), 17)
        self.assertEqual(set(seen), allowed)

    def test_frame_and_fault_signals_not_gated(self):
        text=(ROOT/'snes/src/native.s').read_text()
        for name in ('inc GFRAMES','sta f:HFRAMES','sta f:FAULTCODE'):
            self.assertIn(name,text)
        self.assertNotIn('.if USE_RUNTIME_COUNTERS', text)
        self.assertNotIn('CountRuntime', (ROOT/'snes/src/native_apu.inc').read_text())
        self.assertNotIn('CountRuntime', (ROOT/'snes/src/native_video.inc').read_text())

    def test_guard_input_contains_real_but_unclassified_code(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);meta=fault_fixture(d)
            raw=(d/'fixture.nes').read_bytes()
            self.assertEqual(raw[16+0x3f800:16+0x3f807], bytes.fromhex('a95a857e4c04f8'))
            self.assertEqual((d/'counts.u32').read_bytes()[0x3f800*4:0x3f807*4], bytes(28))
            self.assertEqual(meta['unclassified_target'], 0xf800)

    def test_guard_input_metadata_matches_the_modified_rom(self):
        import hashlib
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);meta=fault_fixture(d)
            self.assertEqual(meta['rom_sha256'], hashlib.sha256((d/'fixture.nes').read_bytes()).hexdigest())

    def test_independent_matrix_covers_multiple_paths(self):
        cases=configurations();names=[c[0] for c in cases]
        self.assertEqual(len(cases),len(set(names)))
        self.assertTrue({'cpu','indexed-c0','indexed-fallback','dummy-reads','bank-interrupts',
                         'audio-lengths','audio-c0','oam-ram','oam-rom'} <= set(names))


if __name__ == '__main__': unittest.main()
