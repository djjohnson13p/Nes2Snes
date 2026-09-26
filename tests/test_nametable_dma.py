"""Transfer boundaries, exact build gates and fill-mode fixture checks."""
import inspect
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_native import build
from native_fixture import create as native_fixture
from fill_mode_fixture import create as fill_fixture
from verify_nametable_dma import expected_runs, expected_vram, cases

class NametableDmaTests(unittest.TestCase):
    def test_options_are_off_by_default(self):
        args=inspect.signature(build).parameters
        self.assertIs(args['coalesced_nt_dma'].default,False)
        self.assertIs(args['fill_cache_fix'].default,False)
    def test_empty_or_disabled_map_never_starts_dma(self):
        self.assertEqual(expected_runs(bytes(160),True),0)
        self.assertEqual(expected_runs(bytes([255])*160,False),0)
    def test_all_single_row_destinations_are_disjoint(self):
        destinations=set()
        source=bytes([213])*0x3000
        for i in range(160):
            flags=bytearray(160);flags[i]=1
            data=expected_vram(bytes(65536),source,flags,True)
            changed={j for j,v in enumerate(data) if v}
            self.assertEqual(len(changed),64)
            self.assertTrue(changed.isdisjoint(destinations))
            destinations.update(changed)
        self.assertEqual(len(destinations),10240)
    def test_all_contiguous_intervals_in_each_region_are_one_run(self):
        for lo,hi in ((0,128),(128,160)):
            for begin in range(lo,hi):
                for end in range(begin+1,hi+1):
                    mask=bytes(begin)+bytes([1])*(end-begin)+bytes(160-end)
                    self.assertEqual(expected_runs(mask,True),1)
    def test_hud_boundary_cannot_coalesce(self):
        mask=bytearray(160);mask[127:129]=b'\x01\x01'
        self.assertEqual(expected_runs(mask,True),2)
    def test_padding_rows_split_actual_tables(self):
        self.assertEqual(expected_runs(bytes([1]*30+[0]*2)*5,True),5)
    def test_nonboolean_dirty_values_count_as_dirty(self):
        self.assertEqual(expected_runs(bytes([0,128,255,0])*40,True),40)
    def test_invalid_shapes_rejected(self):
        with self.assertRaises(ValueError):expected_runs(bytes(159),True)
        with self.assertRaises(ValueError):expected_vram(bytes(65536),bytes(12287),bytes(160),True)
        with self.assertRaises(ValueError):expected_vram(bytes(65535),bytes(12288),bytes(160),True)
    def test_case_matrix_names_unique(self):
        rows=cases()
        self.assertEqual(len(rows),421)
        self.assertEqual(len({r[0] for r in rows}),len(rows))
        self.assertTrue(all(len(r[1])==160 for r in rows))
    def test_fill_rejects_nonbytes(self):
        with tempfile.TemporaryDirectory() as name:
            for value in (-1,256,True):
                with self.assertRaises(ValueError):fill_fixture(Path(name),tile=value)
    def test_fill_uses_fixed_mapping(self):
        with tempfile.TemporaryDirectory() as name:
            meta=fill_fixture(Path(name),117,253)
            self.assertEqual(meta['change_at_nmi'],32)
            self.assertEqual(meta['color'],253)
            self.assertLess(meta['program_bytes'],8192)
    @unittest.skipUnless(shutil.which('ca65') and shutil.which('ld65'),'requires cc65')
    def test_actual_assembly_gates(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);native_fixture(p)
            for i,(coalesce,fix) in enumerate(((False,False),(True,False),(False,True),(True,True))):
                out=p/f'build-{i}'
                result=build(p/'fixture.nes',p,out,coalesced_nt_dma=coalesce,fill_cache_fix=fix)
                labels=(out/'native.lbl').read_text()
                self.assertEqual(' .UploadNametablesCoalesced' in labels,coalesce)
                self.assertEqual(' .UpdateFillCache' in labels,fix)
                self.assertIs(result['coalesced_nametable_dma'],coalesce)
                self.assertIs(result['fill_cache_fix'],fix)
                self.assertFalse(result['complete_game_port'])

if __name__=='__main__':unittest.main()
