"""Fixture generation and dispatch contracts; emulator tests live in the matrix."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_native import QUICK_INDEXED, OPERATIONS, classify_patch
from indexed_memory_fixture import create
from indexed_bus_fixture import create as bus_create
from opcodes6502 import OPS
from rom import Rom


class IndexedFixtureTests(unittest.TestCase):
    def test_every_selected_operation_has_both_absolute_index_modes(self):
        for name in QUICK_INDEXED:
            for mode in ('absx','absy'):
                self.assertIn((name,mode,3),OPS.values())
                self.assertIn(name,OPERATIONS)

    def test_hardware_and_wrap_sites_are_always_intercepted(self):
        for op,(name,mode,size) in OPS.items():
            if name not in QUICK_INDEXED or mode not in ('absx','absy'):continue
            for base in (0x07FF,0x1FFF,0x2000,0x20FF,0x4000,0xFFFF):
                raw=bytes([op,base&255,base>>8])
                actual,meta=classify_patch(raw,[1,0,0])
                self.assertEqual(actual[:2],bytes([2,op]))
                self.assertEqual(len(meta['trap_sites']),1)

    def test_memory_fixture_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a';b=Path(temp)/'b'
            create(a,19,True);create(b,19,True)
            for name in ('fixture.nes','counts.u32','cpu-address.u16','trace-summary.json'):
                self.assertEqual((a/name).read_bytes(),(b/name).read_bytes())

    def test_memory_fixture_records_boundaries_and_io(self):
        with tempfile.TemporaryDirectory() as temp:
            m=create(Path(temp),7,True)
            names={r['name'] for r in m['records']}
            self.assertEqual(len(m['records']),129)
            for name in ('wrap_15_7','rom_store_fallback_0_30','ppu_buffered_fallback_0',
                         'apu_reload_3_1','apu_disable','joy_fallback_9'):
                self.assertIn(name,names)
            self.assertTrue(m['c0_start'])
            self.assertEqual(m['expected_oam_source_page'],2)

    def test_seed_changes_only_original_procedural_input(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a';b=Path(temp)/'b';create(a,0);create(b,1)
            self.assertNotEqual((a/'fixture.nes').read_bytes(),(b/'fixture.nes').read_bytes())
            self.assertEqual(Rom.read(a/'fixture.nes').mapper,5)

    def test_bus_fixture_has_all_required_side_effect_families(self):
        with tempfile.TemporaryDirectory() as temp:
            m=bus_create(Path(temp));names=[r['name'] for r in m['records']]
            self.assertEqual(len(names),131)
            for substring in ('LDA_absx_cross1','LDA_absy_cross1','LDA_iy_cross1','STA_iy_cross0',
                              'STA_absx_cross1','INC_absx_cross0','ROR_absx_cross0','status_dummy_resets_toggle'):
                self.assertTrue(any(substring in n for n in names),substring)

    def test_bus_fixture_stays_within_bank_and_record_ram(self):
        with tempfile.TemporaryDirectory() as temp:
            m=bus_create(Path(temp))
            self.assertLessEqual(m['program_bytes'],0x1FFA)
            self.assertLessEqual(m['result_end'],0x780)
            self.assertTrue(m['indexed_bus_fixture'])

    def test_records_do_not_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            for generator in (create,bus_create):
                m=generator(Path(temp));addresses=[r['address'] for r in m['records']]
                self.assertEqual(addresses,list(range(0x300,m['result_end'],4)))

if __name__=='__main__':unittest.main()
