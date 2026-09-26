import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from performance_budget import optimistic_speedup, summarize, validate_profile

class BudgetTests(unittest.TestCase):
    def records(self):
        return [dict(game_frame=n,display_frame=h) for n,h in enumerate((10,11,13,14,17))]
    def test_cadence_and_required_improvement(self):
        r=summarize(self.records(),[('sample',0,4)])[0]
        self.assertEqual(r['display_frames'],7)
        self.assertEqual(r['extra_display_frames'],3)
        self.assertEqual(r['max_display_spacing'],3)
        self.assertEqual(r['spacing_histogram'],{'1':2,'2':1,'3':1})
        self.assertAlmostEqual(r['required_time_reduction_fraction'],3/7)
        self.assertAlmostEqual(r['required_throughput_increase_fraction'],.75)
        self.assertFalse(r['one_to_one_cadence'])
    def test_one_to_one(self):
        r=summarize([dict(game_frame=i,display_frame=i+10) for i in range(3)],[('sample',0,2)])[0]
        self.assertTrue(r['one_to_one_cadence'])
        self.assertEqual(r['required_time_reduction_fraction'],0)
    def test_reject_missing_tag(self):
        with self.assertRaises(ValueError):summarize(self.records()[:2]+self.records()[3:],[('s',0,4)])
    def test_reject_duplicate_tag(self):
        with self.assertRaises(ValueError):summarize(self.records()+[self.records()[-1]],[('s',0,4)])
    def test_reject_nonincreasing_display(self):
        r=self.records();r[2]['display_frame']=11
        with self.assertRaises(ValueError):summarize(r,[('s',0,4)])
    def test_reject_bad_intervals(self):
        for interval in [('s',4,0),('s',0,0),('s',0,7)]:
            with self.subTest(interval=interval),self.assertRaises(ValueError):summarize(self.records(),[interval])
    def test_reject_empty_and_boolean_frame(self):
        with self.assertRaises(ValueError):summarize([])
        with self.assertRaises(ValueError):summarize([dict(game_frame=True,display_frame=2)])
    def test_fixed_workload_projection(self):
        self.assertAlmostEqual(optimistic_speedup(.2,.5),1/.9)
        self.assertEqual(optimistic_speedup(0,1),1)
        self.assertEqual(optimistic_speedup(.2,0),1)
    def test_reject_invalid_projection(self):
        for share,cut in [(1,1),(-.1,.5),(.1,1.1),(math.nan,.2),(.2,math.inf),(True,.2)]:
            with self.subTest(share=share,cut=cut),self.assertRaises(ValueError):optimistic_speedup(share,cut)
    def profile(self):
        return dict(rom_sha256='hash',elapsed_master_clocks=100,
                    regions=[dict(region='host',master_clocks=60),dict(region='guest',master_clocks=35)],
                    unattributed_master_clocks=5,
                    cop_callers=dict(completed_master_clocks=20,overlapping_starts=0))
    def test_overlapping_caller_view_not_added_to_regions(self):
        validate_profile(self.profile(),'hash')
    def test_reject_mixed_roms(self):
        with self.assertRaises(ValueError):validate_profile(self.profile(),'other')
    def test_reject_unbalanced_costs(self):
        p=self.profile();p['regions'][0]['master_clocks']=70
        with self.assertRaises(ValueError):validate_profile(p,'hash')
    def test_reject_duplicate_regions(self):
        p=self.profile();p['regions'][1]['region']='host'
        with self.assertRaises(ValueError):validate_profile(p,'hash')
    def test_reject_negative_clocks_or_overlaps(self):
        for k,v in [('unattributed_master_clocks',-1),('elapsed_master_clocks',0)]:
            p=self.profile();p[k]=v
            with self.assertRaises(ValueError):validate_profile(p,'hash')
        p=self.profile();p['cop_callers']['overlapping_starts']=1
        with self.assertRaises(ValueError):validate_profile(p,'hash')

if __name__=='__main__':unittest.main()
