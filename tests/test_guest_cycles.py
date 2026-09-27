"""Native accountant contract and independent-timing rejection tests."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from guest_cycles import Instruction, metadata, OPS, account_window, tables
from guest_cycle_fixture import cases,create_native,create_nes
from verify_guest_cycles import check_native,check_nes,CycleObserver


class GuestCycleTests(unittest.TestCase):
    def test_every_official_opcode_has_bounded_nonzero_cost(self):
        self.assertEqual(len(OPS),151)
        for op in OPS:
            self.assertTrue(2<=Instruction(op,0x8100,pointer=0).cost()<=7)

    def test_every_unknown_opcode_rejected(self):
        for op in set(range(256))-set(OPS):
            with self.assertRaises(ValueError):metadata(op)

    def test_branch_decision_and_both_directions(self):
        self.assertEqual(Instruction(0xD0,0x80FD,8,p=2).cost(),2)
        self.assertEqual(Instruction(0xD0,0x8100,8,p=0).cost(),3)
        self.assertEqual(Instruction(0xD0,0x80FD,8,p=0).cost(),4)
        self.assertEqual(Instruction(0xD0,0x8102,0xF8,p=0).cost(),4)

    def test_branch_postfetch_wrap(self):
        self.assertEqual(Instruction(0xD0,0xFFFE,0,p=0).cost(),3)
        self.assertEqual(Instruction(0xD0,0xFFFF,0xFE,p=0).cost(),4)

    def test_read_and_store_and_rmw_differ(self):
        for address in (0x200,0x2FF,0xFFFF):
            expected=5 if address&255 else 4
            self.assertEqual(Instruction(0xBD,0x8100,address,x=1).cost(),expected)
            self.assertEqual(Instruction(0x9D,0x8100,address,x=1).cost(),5)
            self.assertEqual(Instruction(0xFE,0x8100,address,x=1).cost(),7)

    def test_indirect_y_requires_snapshot_only_for_dynamic_read(self):
        with self.assertRaises(ValueError):Instruction(0xB1,0x8100,0xFF,y=1).cost()
        self.assertEqual(Instruction(0xB1,0x8100,0xFF,y=1,pointer=0xFFFF).cost(),6)
        self.assertEqual(Instruction(0x91,0x8100,0xFF,y=1).cost(),6)

    def test_all_low_byte_index_combinations(self):
        for lo in range(256):
            for x in range(256):
                self.assertEqual(Instruction(0xBD,0x8000,0x200+lo,x=x).cost(),4+(lo+x>=256))

    def test_decimal_and_unrelated_flags_do_not_add_cycles_on_2a03(self):
        for p in range(256):
            self.assertEqual(Instruction(0x69,0x8100,1,p=p).cost(),2)
            self.assertEqual(Instruction(0xE9,0x8100,1,p=p).cost(),2)

    def test_stack_and_jump_costs(self):
        expected={0x00:7,0x20:6,0x40:6,0x60:6,0x08:3,0x48:3,0x28:4,0x68:4,0x4C:3,0x6C:5}
        for op,cost in expected.items():self.assertEqual(Instruction(op,0x8100).cost(),cost)

    def test_invalid_types_and_ranges_fail_before_encoding(self):
        for key,value in [('opcode',True),('pc',False),('p',256),('x',-1),('y',1.0),('pointer',True),('operand',65536)]:
            with self.subTest(key=key),self.assertRaises(ValueError):Instruction(**dict(opcode=0xEA,pc=0x8100,**{} ) | {key:value}).record()
        with self.assertRaises(ValueError):Instruction(0xD0,0x8100,0x100).record()

    def test_fixture_coverage_and_independent_outputs_not_in_inputs(self):
        rows=cases();self.assertEqual({r['opcode'] for r in rows},set(OPS))
        self.assertEqual(len({r['name'] for r in rows}),len(rows))
        for r in rows:
            self.assertNotIn('cost',r)
            rec=Instruction(**{k:r[k] for k in Instruction.__dataclass_fields__}).record()
            self.assertEqual(rec[11:14],bytes(3));self.assertEqual(len(rec),14)

    def test_native_assembly_and_default_runtime_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            create_native(Path(d),[Instruction(0xBD,0x8100,0x2FF,x=1).record()])
        root=Path(__file__).resolve().parents[1]
        self.assertNotIn('guest_cycles.inc',(root/'snes/src/native.s').read_text())
        self.assertNotIn('guest_cycles',(root/'tools/build_native.py').read_text())

    def test_input_shape_rejected_before_build(self):
        for rows in ([],[bytes(13)],[bytes(14)]*65):
            with self.assertRaises(ValueError):create_native(Path('unused'),rows)

    def test_observer_config_rejects_malformed_inputs_before_core_access(self):
        for pcs in ([],[True],[0x7FFF],[0xFFFE],[0x8000,0x8000]):
            with self.assertRaises(ValueError):CycleObserver(None,pcs)
        for cap in (True,0,1048577):
            with self.assertRaises(ValueError):CycleObserver(None,[0x8000],cap)

    def test_native_acceptance_rejects_one_cost_byte_and_context_byte(self):
        inp=Instruction(0xEA,0x8100).record()
        output=bytearray(inp+bytes.fromhex('34127856cdab55037e4df01f'));output[11]=2
        check_native([inp],[2],dict(records=[output.hex()]))
        for pos in (0,11,12,14,25):
            bad=bytearray(output);bad[pos]^=1
            with self.assertRaises(RuntimeError):check_native([inp],[2],dict(records=[bad.hex()]))

    def test_incomplete_native_records_rejected(self):
        with self.assertRaises(RuntimeError):check_native([bytes(14)],[2],dict(records=[]))

    def test_independent_capture_mutation_rejected(self):
        pre=dict(start=100,end=102,pc=0x8100,operand=0,pointer=0,next_pc=0x8101,opcode=0xEA,p=0x34,x=0,y=0,a=0,s=255,valid=1,reserved=0)
        plain={'results':[{'name':'nop','ram_sha256':'ram','image_sha256':'image','video_callbacks':1,'audio_frames':800}]}
        observed=copy.deepcopy(plain);observed['results'][0]['observed']=[pre]
        plan=[dict(name='nop',pc=0x8100,opcode=0xEA)]
        self.assertEqual(check_nes(plain,observed,plan)[0]['measured_cycles'],2)
        for mutation in ('elapsed','image','count'):
            bad=copy.deepcopy(observed)
            if mutation=='elapsed':bad['results'][0]['observed'][0]['end']+=1
            elif mutation=='image':bad['results'][0]['image_sha256']='changed'
            else:bad['results'][0]['observed']*=2
            with self.assertRaises(RuntimeError):check_nes(plain,bad,plan)


class CycleWindowTests(unittest.TestCase):
    def rows(self):
        return [dict(start=t,end=t+2,pc=pc,operand=0,pointer=0,next_pc=pc+1,opcode=0xEA,p=0x34,x=0,y=0,a=0,s=255,valid=1,reserved=0) for t,pc in [(100,0x8000),(102,0x8001),(111,0x9000),(113,0x9001)]]

    def test_separate_interrupt_entry_cost_closes_window(self):
        result=account_window(self.rows(),{0x9000:'nmi'})
        self.assertEqual(result['instruction_cycles'],8);self.assertEqual(result['interrupt_cycles'],7)
        self.assertEqual(result['span_cycles'],15);self.assertFalse(result['interrupt_delivery_predicted'])

    def test_unexplained_gap_not_treated_as_idle_or_interrupt(self):
        with self.assertRaises(ValueError):account_window(self.rows(),{})
        rows=self.rows();rows[2]['start']+=1;rows[2]['end']+=1
        with self.assertRaises(ValueError):account_window(rows,{0x9000:'nmi'})

    def test_external_stall_not_hidden_inside_opcode(self):
        rows=self.rows();rows[0]['end']+=513
        with self.assertRaisesRegex(ValueError,'unexplained timing'):account_window(rows,{0x9000:'nmi'})

    def test_missing_record_or_wrong_pc_rejected(self):
        rows=self.rows();del rows[1]
        with self.assertRaises(ValueError):account_window(rows,{0x9000:'nmi'})
        rows=self.rows();rows[1]['pc']+=1
        with self.assertRaises(ValueError):account_window(rows,{0x9000:'nmi'})

    def test_empty_boolean_negative_and_unknown_record_rejected(self):
        with self.assertRaises(ValueError):account_window([],{})
        for key,value in [('start',True),('end',-1),('valid',True),('opcode',2),('extra',0)]:
            rows=self.rows();rows[0][key]=value
            with self.assertRaises(ValueError):account_window(rows,{0x9000:'nmi'})
