"""Fail-closed recognition, unchanged original code, and opt-in build checks."""
import inspect
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import native_dispatch as dispatch
from dispatch_fixture import create, boundary_fixture
from build_native import build

class NativeDispatchTests(unittest.TestCase):
    def fixture(self, root):
        create(root,selectors=[0,127,128,255])
        prg=(root/'fixture.nes').read_bytes()[16:16+0x40000]
        counts=list(struct.unpack('<262144I',(root/'counts.u32').read_bytes()))
        return prg,counts
    def test_option_disabled_by_default(self):
        self.assertIs(inspect.signature(build).parameters['native_inline_dispatch'].default,False)
    def test_exact_recognition_and_original_body_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            prg,counts=self.fixture(Path(d));sites,source=dispatch.plan(prg,counts)
            self.assertEqual(len(sites),4)
            symbols={s['label']:0x1700 for s in sites}
            changed=dispatch.apply(prg,sites,symbols)
            self.assertEqual(changed[0x3F700:0x3F719],prg[0x3F700:0x3F719])
            allowed={s['prg_offset']+n for s in sites for n in (1,2)}
            self.assertTrue({i for i,(a,b) in enumerate(zip(prg,changed)) if a!=b}<=allowed)
            self.assertIn('OriginalDispatch = $F700',source)
    def test_missing_classification_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            prg,counts=self.fixture(Path(d))
            for i in range(0x3F700,0x3F719):
                if counts[i]:
                    copy=counts[:];copy[i]=0
                    self.assertFalse(dispatch.matches(prg,copy,0x3F700))
    def test_any_changed_body_byte_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            prg,counts=self.fixture(Path(d))
            for i in range(0x3F700,0x3F719):
                copy=bytearray(prg);copy[i]^=1
                self.assertFalse(dispatch.matches(bytes(copy),counts,0x3F700),hex(i))
    def test_overlapping_classification_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            prg,counts=self.fixture(Path(d));counts[0x3F702]=1
            self.assertFalse(dispatch.matches(prg,counts,0x3F700))
    def test_unclassified_call_is_not_patched(self):
        with tempfile.TemporaryDirectory() as d:
            prg,counts=self.fixture(Path(d));sites,_=dispatch.plan(prg,counts)
            for s in sites:counts[s['prg_offset']]=0
            self.assertEqual(dispatch.plan(prg,counts)[0],[])
    def test_apply_checks_original_and_reserved_range(self):
        with tempfile.TemporaryDirectory() as d:
            prg,counts=self.fixture(Path(d));sites,_=dispatch.plan(prg,counts)
            for address in (0xFFF,0x1800):
                with self.assertRaises(ValueError):dispatch.apply(prg,sites,{s['label']:address for s in sites})
            corrupt=bytearray(prg);corrupt[sites[0]['prg_offset']]=0xEA
            with self.assertRaises(ValueError):dispatch.apply(bytes(corrupt),sites,{s['label']:0x1700 for s in sites})
    def test_invalid_fixture_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for values in ([],[256],[-1],[True],list(range(9))):
                with self.assertRaises(ValueError):create(Path(d),selectors=values)
    def test_c0_map_without_alias_flag_uses_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            meta=create(Path(d),primary=15,cbank=7)
            self.assertEqual(meta['expected_native_calls'],0)
    def test_boundary_calls_leave_vectors_intact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);create(root,selectors=[0])
            vectors=(root/'fixture.nes').read_bytes()[16+0x3FFFA:16+0x40000]
            for address in (0xFEFF,0xFF00,0xFF01,0xFFF7):
                meta=boundary_fixture(root,address)
                self.assertEqual((root/'fixture.nes').read_bytes()[16+0x3FFFA:16+0x40000],vectors)
                self.assertEqual(meta['expected_native_calls'],int(address<=0xFF00))
    @unittest.skipUnless(shutil.which('ca65') and shutil.which('ld65'),'requires cc65')
    def test_assembler_default_and_no_direct_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);create(root,selectors=[127])
            for name,options,enabled in (
                ('default',{},False),('enabled',{'native_inline_dispatch':True},True),
                ('no-direct',{'native_inline_dispatch':True,'direct':False},False)):
                info=build(root/'fixture.nes',root,root/name,**options)
                self.assertIs(info['native_inline_dispatch'],enabled)
                self.assertEqual(len(info['native_dispatch_sites']),int(enabled))
                self.assertFalse(info['complete_game_port'])

if __name__=='__main__':unittest.main()
