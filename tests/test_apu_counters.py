"""Explicit edge cases for the frame-quantized audio-counter contract."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from apu_model import Counters,LENGTHS
from apu_counter_fixture import create
from direct_calls import plan
class CounterTests(unittest.TestCase):
    def active(self,control=0):
        m=Counters();m.write(0x4000,control);m.write(0x4015,1);m.write(0x4003,8);return m
    def test_all_length_indices_and_channels(self):
        for index,length in enumerate(LENGTHS):
            for c in range(4):
                m=Counters();m.write(0x4015,1<<c);m.write(0x4003+4*c,index<<3)
                self.assertEqual(m.lengths[c],length)
                for _ in range(length-1):m.half()
                self.assertEqual(m.lengths[c],1);m.half();self.assertEqual(m.lengths[c],0)
    def test_disabled_high_write_does_not_load_length(self):
        m=Counters();m.write(0x4003,8);self.assertEqual(m.lengths[0],0)
        self.assertEqual(m.restart[0],1);m.write(0x4015,1);self.assertEqual(m.lengths[0],0)
    def test_enable_does_not_resurrect(self):
        m=self.active();m.write(0x4015,0);m.write(0x4015,1);self.assertEqual(m.lengths[0],0)
    def test_halt_bits(self):
        for c in range(4):
            m=Counters();m.write(0x4015,1<<c);m.write(0x4000+4*c,128 if c==2 else 32);m.write(0x4003+4*c,24)
            for _ in range(99):m.half()
            self.assertEqual(m.lengths[c],2);m.write(0x4000+4*c,0);m.half();self.assertEqual(m.lengths[c],1)
    def test_zero_period_envelope(self):
        m=self.active();observed=[]
        for _ in range(18):m.quarter();observed.append(m.decay[0])
        self.assertEqual(observed,list(range(15,-1,-1))+[0,0])
    def test_all_envelope_dividers(self):
        for period in range(16):
            m=self.active(period);m.quarter();self.assertEqual(m.decay[0],15)
            for _ in range(period):m.quarter();self.assertEqual(m.decay[0],15)
            m.quarter();self.assertEqual(m.decay[0],14)
    def test_envelope_loop(self):
        m=self.active(32)
        for _ in range(16):m.quarter()
        self.assertEqual(m.decay[0],0);m.quarter();self.assertEqual(m.decay[0],15)
    def test_constant_volume_does_not_stop_envelope(self):
        m=self.active(0x15)
        for _ in range(7):m.quarter()
        self.assertEqual(m.decay[0],14);self.assertEqual(m.volume(0),30)
    def test_same_value_restart(self):
        m=self.active();m.quarter();m.quarter();self.assertEqual(m.decay[0],14)
        m.write(0x4003,8);m.quarter();self.assertEqual(m.decay[0],15)
    def test_volume_write_does_not_restart(self):
        m=self.active();m.quarter();m.write(0x4000,0);m.quarter();self.assertEqual(m.decay[0],14)
    def test_triangle_reload_and_release(self):
        m=Counters();m.write(0x4015,4);m.write(0x4008,0x83);m.write(0x400b,8)
        for _ in range(12):m.quarter();self.assertEqual(m.linear,3)
        m.write(0x4008,3);m.quarter();self.assertEqual((m.linear,m.reload),(3,0))
        for _ in range(3):m.quarter()
        self.assertEqual(m.linear,0);self.assertEqual(m.volume(2),0)
    def test_four_step_frame(self):
        m=Counters();m.write(0x4017,0x40);m.frame()
        self.assertEqual((m.quarters,m.halves,m.phase),(4,2,0))
    def test_five_step_frame(self):
        m=Counters();m.write(0x4017,0xc0)
        self.assertEqual((m.quarters,m.halves),(1,1))
        for _ in range(5):m.frame()
        self.assertEqual((m.quarters,m.halves,m.phase),(17,9,0))
    def test_reset_to_four_step_no_immediate_clock(self):
        m=Counters();m.write(0x4017,0xc0);m.write(0x4017,0x40)
        self.assertEqual((m.quarters,m.halves,m.phase),(1,1,0))
    def test_invalid_registers(self):
        for address,value in ((0x2000,0),(0x4014,0),(0x4016,0),(0x4018,0),(0x4000,256),(0x4000,-1)):
            with self.assertRaises(ValueError):Counters().write(address,value)
    def test_opt_in_direct_writes_are_events(self):
        for op in (0x8d,0x8e,0x8c):
            for addr in (*range(0x4000,0x4014),0x4015,0x4017):
                prg=bytes([op,addr&255,addr>>8]);sites=[dict(prg_offset=0,mode='abs')]
                selected,source=plan(prg,sites,audio_counters=True)
                self.assertEqual(selected[0]['kind'],'apu');self.assertIn('DirectApu',source)
                self.assertNotIn('sta f:$7E40',source)
    def test_old_preview_still_backed(self):
        selected,source=plan(b'\x8d\x03\x40',[dict(prg_offset=0,mode='abs')])
        self.assertEqual(selected[0]['kind'],'backing');self.assertIn('sta f:$7E4003',source)
    def test_counter_fixture_records(self):
        with tempfile.TemporaryDirectory() as td:
            meta=create(Path(td));self.assertTrue(meta['apu_counter_fixture'])
            self.assertEqual(len([r for r in meta['records'] if r['name'].startswith('length_')]),96)
if __name__=='__main__':unittest.main()
