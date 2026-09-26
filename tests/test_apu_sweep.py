import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from apu_sweep_model import SweepCounters

class SweepTests(unittest.TestCase):
    def pulse(self, channel=0, period=1000, control=0x89):
        m=SweepCounters();m.write(0x4015,3)
        m.write(0x4000+4*channel,0x3f);m.write(0x4001+4*channel,control)
        m.write(0x4002+4*channel,period&255);m.write(0x4003+4*channel,8|(period>>8))
        return m
    def test_negate_difference(self):
        for c,expected in ((0,499),(1,500)):
            m=self.pulse(c);m.half();self.assertEqual(m.periods[c],expected)
    def test_positive(self):
        m=self.pulse(period=500,control=0x81);m.half();self.assertEqual(m.periods[0],750)
    def test_all_target_periods_and_shifts(self):
        m=SweepCounters()
        for c in (0,1):
            for p in range(2048):
                m.periods[c]=p
                for shift in range(8):
                    m.regs[4*c+1]=shift;self.assertEqual(m.target(c),p+(p>>shift))
                    m.regs[4*c+1]=shift|8;self.assertEqual(m.target(c),(p-(p>>shift)-(1-c))&2047)
    def test_disabled_sweep_still_mutes_target_overflow(self):
        m=self.pulse(period=0x600,control=1);self.assertTrue(m.muted(0));m.half()
        self.assertEqual(m.periods[0],0x600);self.assertEqual(m.volume(0),0)
    def test_shift_zero_no_update_but_mutes(self):
        m=self.pulse(period=0x400,control=0x80);m.half()
        self.assertEqual(m.periods[0],0x400);self.assertTrue(m.muted(0))
    def test_negate_shift_zero_not_overflow_muted(self):
        m=self.pulse(period=0x700,control=0x88);m.half()
        self.assertEqual(m.periods[0],0x700);self.assertFalse(m.muted(0))
    def test_small_period_mute(self):
        for p in range(8):self.assertTrue(self.pulse(period=p).muted(0))
        self.assertFalse(self.pulse(period=8).muted(0))
    def test_divider_period_plus_one(self):
        for divider in range(8):
            m=self.pulse(period=600,control=0x87|(divider<<4));m.half()
            first=m.periods[0]
            for _ in range(divider):m.half();self.assertEqual(m.periods[0],first)
            m.half();self.assertGreater(m.periods[0],first)
    def test_reload_does_not_force_update_when_divider_nonzero(self):
        m=self.pulse(control=0xa9);m.half();p=m.periods[0]
        m.write(0x4001,0xa9);m.half();self.assertEqual(m.periods[0],p)
        self.assertEqual(m.sweep_dividers[0],2);self.assertEqual(m.sweep_reload[0],0)
    def test_reload_at_zero_still_updates(self):
        m=self.pulse();m.half();m.write(0x4001,0x89);m.half()
        self.assertEqual(m.periods[0],249)
    def test_timer_low_write_preserves_swept_high(self):
        m=self.pulse();m.half();m.write(0x4002,0x23);self.assertEqual(m.periods[0],0x123)
    def test_timer_high_write_preserves_swept_low(self):
        m=self.pulse();m.half();m.write(0x4003,0x0a);self.assertEqual(m.periods[0],0x2f3)
    def test_shadow_register_is_not_changed_by_sweep(self):
        m=self.pulse();before=m.regs[:];m.half();self.assertEqual(before,m.regs)
    def test_channel_disable_does_not_stop_sweep(self):
        m=self.pulse();m.write(0x4015,0);m.half();self.assertEqual(m.periods[0],499)
        self.assertEqual(m.volume(0),0)
    def test_frame_clock(self):
        m=self.pulse();m.frame();self.assertEqual(m.periods[0],249)
    def test_immediate_five_step_clock(self):
        m=self.pulse();m.write(0x4017,0xc0);self.assertEqual(m.periods[0],499)
    def test_invalid_channel(self):
        with self.assertRaises(ValueError):SweepCounters().target(2)
    def test_build_option_requires_counters(self):
        from build_native import build
        with self.assertRaisesRegex(ValueError, 'audio-counters'):
            build(Path('unused'),Path('unused'),Path('unused'),audio_sweep=True)
    def test_reject_wrong_oracle_format(self):
        from verify_sweep_oracle import fcs_periods
        for data in (b'',b'BAD'+bytes(80),b'FCS'+bytes(13)):
            with self.assertRaises(ValueError):fcs_periods(data)
    def test_reject_truncated_oracle_section(self):
        from verify_sweep_oracle import fcs_periods
        with self.assertRaises(ValueError):fcs_periods(b'FCS'+bytes(13)+b'\x05'+(100).to_bytes(4,'little'))
if __name__=='__main__':unittest.main()
