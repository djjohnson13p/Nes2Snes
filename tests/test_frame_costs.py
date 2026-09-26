"""Diagnostic instrumentation must reject unknown source and be idempotent."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from instrument_frame_costs import instrument,MARKER
from profile_frame_costs import labels

class FrameCostTests(unittest.TestCase):
    ANCHORS='void S9xMainLoop (void)\n\t\tuint8\t\t\t\tOp;\n\t\t(*Opcodes[Op].S9xOpcode)();\n\t\t\tCPU.Cycles -= Timings.H_Max;\n'
    def test_exact_anchor_patch_and_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'cpuexec.cpp';p.write_text(self.ANCHORS)
            self.assertTrue(instrument(root));first=p.read_bytes()
            self.assertFalse(instrument(root));self.assertEqual(first,p.read_bytes())
            self.assertIn(MARKER,p.read_text());self.assertIn('n2s_clock_base += Timings.H_Max;',p.read_text())
    def test_rejects_missing_anchor_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'cpuexec.cpp';p.write_text('unknown source')
            with self.assertRaises(ValueError):instrument(root)
            self.assertEqual(p.read_text(),'unknown source')
    def test_rejects_duplicate_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'cpuexec.cpp').write_text(self.ANCHORS*2)
            with self.assertRaises(ValueError):instrument(root)
    def test_rejects_other_instrumentation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'cpuexec.cpp').write_text('// NES2SNES_PROFILE:\n'+self.ANCHORS)
            with self.assertRaises(ValueError):instrument(root)
    def test_symbol_map_ignores_local_and_linker_labels(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'symbols';p.write_text('al 008020 .Beta\nal 008010 .Alpha\nal 008011 .@loop\nal 001000 .__STUBS_RUN__\n')
            self.assertEqual(labels(p),[(0x8010,'Alpha'),(0x8020,'Beta')])

if __name__=='__main__':unittest.main()
