"""Malformed or modified captures must not certify observer calibration."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from observe_route_idle import timeline
from verify_idle_observer import check_capture
from verify_reference_route import verify as verify_reference


class IdleEvidenceTests(unittest.TestCase):
    def captures(self):
        a=dict(frames=40,video_callbacks=40,audio_frames=1000,frame_sequence_sha256='x',
               ram_sha256='y',logged_seed=list(range(32)),logged_ticks=list(range(32)),final_samples=32)
        records=[dict(sample=i+1,ticks=i,ram={'0040':i,'0041':i,'0042':i,'0043':0,'0044':0}) for i in range(32)]
        b=dict(copy.deepcopy(a),observation=dict(complete=True,overflow=False,samples=32,records=records))
        return a,b

    def test_matching_calibration_captures(self):check_capture(*self.captures())

    def test_changed_ram_pixels_audio_frame_or_log_rejected(self):
        for key in ('ram_sha256','frame_sequence_sha256','audio_frames','video_callbacks','frames','logged_seed','logged_ticks'):
            a,b=self.captures();b[key]='changed'
            with self.subTest(key=key),self.assertRaises(RuntimeError):check_capture(a,b)

    def test_one_miscounted_instruction_is_rejected(self):
        a,b=self.captures();b['observation']['records'][4]['ticks']+=1
        with self.assertRaisesRegex(RuntimeError,'Instruction counts'):check_capture(a,b)

    def test_full_counter_not_just_low_word_is_checked(self):
        a,b=self.captures();b['observation']['records'][4]['ticks']+=65536
        with self.assertRaisesRegex(RuntimeError,'Instruction counts'):check_capture(a,b)

    def test_one_changed_sampled_byte_is_rejected(self):
        a,b=self.captures();b['observation']['records'][4]['ram']['0040']+=1
        with self.assertRaisesRegex(RuntimeError,'Sampled RAM'):check_capture(a,b)

    def test_overflow_missing_record_and_wrong_sequence_rejected(self):
        for change in ('overflow','missing','sequence'):
            a,b=self.captures();o=b['observation']
            if change=='overflow':o['overflow']=True
            elif change=='missing':o['records'].pop()
            else:o['records'][4]['sample']=1
            with self.subTest(change=change),self.assertRaises(RuntimeError):check_capture(a,b)

    def test_timeline_rejects_changed_total_outside_marker_and_buttons(self):
        d=dict(input_segments=[dict(frames=10,buttons=[])],total_emulator_calls=10,
               tail_records=[dict(emulator_calls=10,name='end')])
        self.assertEqual(timeline(d),d['input_segments'])
        for change in ('total','marker','buttons','empty','bool'):
            x=copy.deepcopy(d)
            if change=='total':x['total_emulator_calls']=11
            elif change=='marker':x['tail_records'][0]['emulator_calls']=11
            elif change=='buttons':x['input_segments'][0]['buttons']=['left','right']
            elif change=='empty':x['input_segments']=[]
            else:x['input_segments'][0]['frames']=True
            with self.subTest(change=change),self.assertRaises(ValueError):timeline(x)

    def test_reference_replay_rejects_fault_before_loading_any_core(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'route-report.json').write_text(json.dumps(dict(platform='nes',status='completed_budget',fault={})))
            with self.assertRaisesRegex(ValueError,'fault-free'):
                verify_reference(root/'absent-core',root/'absent-rom',root,root/'out')


if __name__=='__main__':unittest.main()
