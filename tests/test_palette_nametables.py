"""Nametable eligibility, strict independent snapshots, and old-profile isolation."""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from palette_state import decode_mmc5
from nametable_palette_fixture import cases,color_case,map_case,guard_cases
from palette_nametables import prepare_native
from palette_timeline import create_native,underlying
from timeline_fixture import expected_initial
from verify_nametable_palette import compare_extra,run
from mmc5_chr_blank import create_native as chr_native
from chr_blank_fixture import cases as chr_cases


def chunk(name,data):return name+struct.pack('<I',len(data))+data


def snapshot(mode=3,reg_override=None,exram=None,duplicate=False):
    cpu=chunk(b'REG\0',bytes(7))+chunk(b'RAM\0',bytes(2049))
    ppu=(chunk(b'REG\0',bytes(11))+chunk(b'PAL\0',bytes(33))+chunk(b'NMT\0',bytes(2049)))
    r=bytearray(32);r[0]=(mode<<4)|0x0F;r[6]=0xAA;r[23]=0x8F;r[24]=0xA3
    regs=bytes(r) if reg_override is None else reg_override
    mem=bytes([0])+bytes([0xA5])*1024 if exram is None else exram
    mm5=chunk(b'REG\0',regs)+chunk(b'RAM\0',mem)
    mapper=chunk(b'MM5\0',mm5)*(2 if duplicate else 1)
    root=chunk(b'CPU\0',cpu)+chunk(b'PPU\0',ppu)+chunk(b'IMG\0',chunk(b'MPR\0',mapper))
    return b'NST\x1a'+struct.pack('<I',len(root))+root


class PaletteNametableTests(unittest.TestCase):
    def test_all_written_color_bytes_and_map_register_values(self):
        rows=cases()
        self.assertEqual(len(rows),544)
        self.assertEqual(len({p['name'] for p in rows}),len(rows))
        self.assertEqual({int(p['name'].split('-')[2],16) for p in rows if p['name'].startswith('nt-color-')},set(range(256)))
        self.assertEqual({int(p['name'].split('-')[2],16) for p in rows if p['name'].startswith('nt-map-')},set(range(256)))

    def test_every_quadrant_source_pair_is_explicitly_exercised(self):
        pairs=set()
        for p in cases():
            if p['name'].endswith('-slot'):
                fields=p['name'].split('-');mapping=int(fields[2],16);q=int(fields[3][1:])
                pairs.add((q,(mapping>>(2*q))&3))
        self.assertEqual(pairs,{(q,s) for q in range(4) for s in range(4)})

    def test_programs_remain_valid_and_no_expected_endpoints_in_inputs(self):
        for plan in cases():
            self.assertEqual(underlying(plan)['memory_model'],'mmc5-chr-blank')
            self.assertEqual(plan['steps'],31)
            self.assertFalse(plan['events'])
            self.assertFalse({'expected','result','expected_state'} & set(plan))

    def test_guards_cover_both_cpu_modes_and_both_rendering_modes(self):
        rows=guard_cases();self.assertEqual(len(rows),4)
        for p,pc,retired in rows:
            underlying(p);self.assertEqual(p['starts'][retired],pc)

    def test_decode_actual_serialization_fields(self):
        d=decode_mmc5(snapshot())
        self.assertEqual(d['nametable_registers'],'03aa8f03')
        self.assertEqual(bytes.fromhex(d['exram']),bytes([0xA5])*1024)

    def test_cpu_mode_two_is_valid(self):
        self.assertEqual(decode_mmc5(snapshot(2))['nametable_registers'][:2],'02')

    def test_rendering_exram_modes_are_not_accepted(self):
        for mode in (0,1):
            with self.assertRaises(ValueError):decode_mmc5(snapshot(mode))

    def test_missing_truncated_and_oversized_mapper_registers_rejected(self):
        for reg in (b'',bytes(31),bytes(33),bytes([0xF0])+bytes(31)):
            with self.assertRaises(ValueError):decode_mmc5(snapshot(reg_override=reg))

    def test_missing_short_and_long_exram_rejected(self):
        for mem in (b'',bytes(1024),bytes(1026),b'\x02'+bytes(1024)):
            with self.assertRaises(ValueError):decode_mmc5(snapshot(exram=mem))

    def test_duplicate_mapper_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):decode_mmc5(snapshot(duplicate=True))

    def test_final_registers_must_match_retired_record(self):
        ref={'nametable_registers':'03aaff01','exram':bytes(1024).hex()}
        cpu=bytearray(2080);cpu[28]=3
        ppu=bytearray(16);ppu[10:13]=bytes.fromhex('aaff01')
        n=dict(ref,completed_steps=1,records=[cpu.hex()],ppu_records=[ppu.hex()])
        compare_extra(ref,n)
        n['nametable_registers']='03aaff02'
        with self.assertRaises(ValueError):compare_extra(dict(ref,nametable_registers=n['nametable_registers']),n)

    def test_independent_exram_difference_rejected(self):
        ref={'nametable_registers':'03aaff01','exram':bytes(1024).hex()}
        with self.assertRaises(RuntimeError):compare_extra(ref,dict(ref,exram=('01'+ref['exram'][2:])))

    def test_whitespace_shortened_extra_snapshots_rejected(self):
        ref={'nametable_registers':'03aaff01','exram':bytes(1024).hex()}
        with self.assertRaises(ValueError):compare_extra(ref,dict(ref,exram=' '*2048))

    def test_invalid_worker_counts_and_limits_fail_before_outputs(self):
        for jobs in (True,0,5,1.5):
            with self.assertRaises(ValueError):run(None,None,Path('unused'),jobs=jobs)
        for limit in (True,0,545):
            with self.assertRaises(ValueError):run(None,None,Path('unused'),limit=limit)

    def test_failed_integration_anchor_does_not_partially_mutate_source(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            before=(root/'snes/src/mmc5_ppu_blank.inc').read_text()
            (out/'mmc5_ppu_blank.inc').write_text(before)
            (out/'palette_timeline.inc').write_text('wrong source')
            with self.assertRaises(ValueError):prepare_native(out)
            self.assertEqual((out/'mmc5_ppu_blank.inc').read_text(),before)

    def test_real_assembler_and_reused_directory_does_not_change_old_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=map_case(0xAA,3,2)
            result=create_native(root/'reused',p,expected_initial(underlying(p)))
            self.assertTrue(result.is_file())
            old=chr_cases()[0]
            a=chr_native(root/'reused',old,expected_initial(old)).read_bytes()
            b=chr_native(root/'clean',old,expected_initial(old)).read_bytes()
            self.assertEqual(a,b)


if __name__=='__main__':unittest.main()
