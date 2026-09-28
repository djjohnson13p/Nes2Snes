"""Rewrite provenance is an explicit admission guard, never a timing tolerance."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from chr_mode_rewrite import PROFILE,validate,underlying,initial,create_nes,create_native
from chr_mode_rewrite_fixture import active,cases,transition,no_change,guard_cases
from verify_chr_mode_rewrite import native_registers,compare_registers,run
from test_chr_sets import native_state,snapshot
from chr_sets_state import decode_sets


def live_state():
    s=native_state();s['chr_rewrite_policy']='03ff0f'
    r=bytearray.fromhex(s['chr_records'][0]);r[43:46]=bytes.fromhex('03ff0f')
    s['chr_records']=[r.hex()];return s


class LiveModeStateTests(unittest.TestCase):
    def test_independent_registers_still_match(self):
        compare_registers(decode_sets(snapshot()),live_state())

    def test_policy_is_not_counted_as_independent_hardware_bytes(self):
        from verify_chr_mode_rewrite import ENDPOINT_BYTES
        self.assertEqual(ENDPOINT_BYTES,5457)
        self.assertEqual(len(native_registers(live_state())),27)

    def test_final_policy_bound_to_retired_record(self):
        for policy in ('02ff0f','03fe0f','03ff07'):
            s=live_state();s['chr_rewrite_policy']=policy
            with self.assertRaises(ValueError):native_registers(s)

    def test_mode_tag_must_match_capture_mode(self):
        s=live_state();r=bytearray.fromhex(s['chr_records'][0]);r[0]=1;s['chr_records']=[r.hex()]
        with self.assertRaises(ValueError):native_registers(s)

    def test_impossible_policy_values_rejected(self):
        for policy in ('04ff0f','030010','03ff1f','ff0000'):
            with self.assertRaises(ValueError):native_registers(dict(live_state(),chr_rewrite_policy=policy))

    def test_missing_short_whitespace_or_long_policy_rejected(self):
        for policy in (None,'','03ff','03ff  ','03ff0f00'):
            with self.assertRaises(ValueError):native_registers(dict(live_state(),chr_rewrite_policy=policy))

    def test_bad_retired_count_and_padding_rejected(self):
        for count in (True,0,2,-1):
            with self.assertRaises(ValueError):native_registers(dict(live_state(),completed_steps=count))
        for pos in (46,47):
            s=live_state();r=bytearray.fromhex(s['chr_records'][0]);r[pos]=1;s['chr_records']=[r.hex()]
            with self.assertRaises(ValueError):native_registers(s)

    def test_old_decoder_still_rejects_live_padding(self):
        from chr_sets_state import native_registers as old
        with self.assertRaises(ValueError):old(live_state())

    def test_register_corruption_is_not_tolerated(self):
        s=live_state();b=bytearray.fromhex(s['chr_set_b']);b[0]^=1;s['chr_set_b']=b.hex()
        with self.assertRaises(ValueError):native_registers(s)


class LiveModeProfileTests(unittest.TestCase):
    def plan(self):return transition(3,0,'b',5,1024,3)

    def test_explicit_profile_does_not_mutate_input(self):
        p=self.plan();before=copy.deepcopy(p)
        self.assertIs(validate(p),p);self.assertEqual(underlying(p)['memory_model'],'mmc5-chr-sets-blank')
        self.assertEqual(p,before)
        with self.assertRaises(ValueError):validate(underlying(p))

    def test_invalid_options_rejected(self):
        for k,v in (('chr_mode',True),('chr_banks',12),('steps',32),('extra',1),('name','../bad')):
            with self.assertRaises(ValueError):validate(dict(self.plan(),**{k:v}))

    def test_all_directed_transitions_and_both_sets_are_covered(self):
        plans=cases();triples={tuple(p['name'].split('-')[1:4]) for p in plans if p['name'].split('-')[1].isdigit()}
        self.assertEqual(triples,{(str(a),str(b),s) for a in range(4) for b in range(4) if a!=b for s in ('a','b')})
        self.assertEqual(len(plans),len({p['name'] for p in plans}))
        self.assertEqual(len(plans),len({(p['code'],p['chr_mode'],p['chr_banks']) for p in plans}))

    def test_active_register_masks(self):
        self.assertEqual([active(m,'a') for m in range(4)],[[0x5127],[0x5123,0x5127],[0x5121,0x5123,0x5125,0x5127],list(range(0x5120,0x5128))])
        self.assertEqual([active(m,'b') for m in range(4)],[[0x512B],[0x512B],[0x5129,0x512B],list(range(0x5128,0x512C))])
        for m,s in ((True,'a'),(4,'b'),(-1,'a'),(0,'c')):
            with self.assertRaises(ValueError):active(m,s)

    def test_original_input_has_real_mode_and_bank_writes(self):
        p=self.plan();code=bytes.fromhex(p['code'])
        self.assertIn(bytes.fromhex('a9a08d0151'),code)
        self.assertIn(bytes.fromhex('8d2b51'),code)
        self.assertEqual(p['events'],[])

    def test_original_program_bank_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);p=self.plan();nes=create_nes(r/'nes',p).read_bytes()
            snes=create_native(r/'native',p,initial(p)).read_bytes();n=p['prg_banks']*8192
            self.assertEqual(snes[32768:32768+n],nes[16:16+n])
            self.assertIn('jsr ChrLiveReadCheck',(r/'native/mmc5_chr_blank.inc').read_text())
            self.assertIn('ora #$0800',(r/'native/program.inc').read_text())

    def test_nested_host_envelope_is_unchanged(self):
        import chr_sets
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);p=self.plan()
            create_native(r/'new',p,initial(p),host_mode='nested')
            chr_sets.create_native(r/'old',underlying(p),initial(p),host_mode='nested')
            self.assertEqual((r/'new/timeline_host_nmi.inc').read_bytes(),(r/'old/timeline_host_nmi.inc').read_bytes())

    def test_guards_are_actual_before_access_prefixes(self):
        rows=guard_cases();self.assertEqual(len(rows),8)
        for p,pc,count in rows:
            self.assertIs(validate(p),p);self.assertGreater(count,0)
            self.assertEqual(p['starts'][count],pc)

    def test_initial_and_no_change_mode_are_explicit(self):
        for m in range(4):
            for s in ('a','b'):
                p=no_change(m,s);self.assertEqual(p['chr_mode'],m)
                self.assertIn(bytes((0xA9,m|0xFC,0x8D,1,0x51)),bytes.fromhex(p['code']))

    def test_same_mode_does_not_invalidate_but_real_change_does(self):
        text=(Path(__file__).resolve().parents[1]/'snes/src/chr_mode_rewrite.inc').read_text()
        self.assertIn('cmp f:CL_MODE\n    beq done\n    sta f:CL_MODE',text)
        self.assertIn('lda #0\n    sta f:CL_VALID',text)
        self.assertIn('and f:CL_VALID\n    cmp MR_INDEX',text)

    def test_invalid_worker_and_smoke_limit_rejected(self):
        for jobs in (True,0,5):
            with self.assertRaises(ValueError):run(None,None,Path('unused'),jobs=jobs)
        for limit in (True,0,len(cases())+1):
            with self.assertRaises(ValueError):run(None,None,Path('unused'),limit=limit)

    def test_production_game_is_not_linked_to_new_profile(self):
        root=Path(__file__).resolve().parents[1]
        for path in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('chr_mode_rewrite',(root/path).read_text())


if __name__=='__main__':unittest.main()
