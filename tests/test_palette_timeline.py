"""Strict palette profile/serialization contracts and real assembler checks."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from palette_state import decode,unpack
from palette_timeline import validate,underlying,create_native,create_nes,boot_code
from palette_timeline_fixture import cases,read_case
from timeline_fixture import expected_initial
from verify_palette_timeline import compare,check_host,compare_endpoint,run as run_matrix
from verify_palette_controls import guard_cases,compare_guard


def chunk(tag,data):return tag+len(data).to_bytes(4,'little')+data

def fixture_state():
    r=bytearray(11);r[3:7]=b'\x00\x21\x00\x21'
    cpu=chunk(b'REG\0',bytes.fromhex('00e1fd5a030334'))+chunk(b'RAM\0',b'\0'+bytes(2048))
    ppu=chunk(b'REG\0',r)+chunk(b'PAL\0',b'\0'+bytes(32))+chunk(b'NMT\0',b'\0'+bytes(2048))
    return chunk(b'NST\x1a',chunk(b'CPU\0',cpu)+chunk(b'PPU\0',ppu))


def sample_capture():
    ref=decode(fixture_state())
    ram=bytearray.fromhex(ref['cpu_ram']);ram[0x7E]=0x5A;ref['cpu_ram']=ram.hex()
    records=[]
    for i in range(31):
        row=bytearray(2080);row[4:11]=bytes.fromhex(ref['cpu_registers'])
        row[18:20]=(i+1).to_bytes(2,'little');row[32:]=ram;records.append(row.hex())
    actual=dict(ref,complete=True,marker=0x5A,status=0,completed_steps=31,
                records=records,ppu_records=[ref['ppu_state']+bytes(6).hex()]*31,
                chr_records=[bytes(48).hex()]*31,cartridge_ram=bytes(32768).hex(),
                exram=bytes(1024).hex(),protected_memory=bytes(132).hex(),ppu_chr_context=bytes(28).hex())
    return ref,actual


class PaletteStateTests(unittest.TestCase):
    def test_complete_observation(self):
        r=decode(fixture_state())
        self.assertEqual(len(bytes.fromhex(r['palette'])),32)
        self.assertEqual(r['cpu_registers'],'00e15a030334fd')
        self.assertEqual(len(bytes.fromhex(r['ppu_state'])),10)

    def test_reference_storage_encoding_retains_raw_high_bits(self):
        raw=fixture_state();old=chunk(b'PAL\0',b'\0'+bytes(32));data=bytearray(32);data[1]=0xFF
        r=decode(raw.replace(old,chunk(b'PAL\0',b'\0'+data)))
        self.assertEqual(bytes.fromhex(r['palette_storage'])[1],255)
        self.assertEqual(bytes.fromhex(r['palette'])[1],63)

    def test_palette_alias_corruption_rejected(self):
        raw=fixture_state();old=chunk(b'PAL\0',b'\0'+bytes(32));bad=bytearray(32);bad[16]=1
        with self.assertRaises(ValueError):decode(raw.replace(old,chunk(b'PAL\0',b'\0'+bad)))

    def test_zlib_and_raw_memory(self):
        raw=bytes(range(32))
        self.assertEqual(unpack(b'\0'+raw,32),raw)
        self.assertEqual(unpack(b'\1'+zlib.compress(raw),32),raw)

    def test_truncated_overlong_and_concatenated_memory_rejected(self):
        for data in (b'',b'\2abc',b'\0'+bytes(31),b'\0'+bytes(33),
                     b'\1'+zlib.compress(bytes(33)),b'\1'+zlib.compress(bytes(32))+b'x',
                     b'\1'+zlib.compress(bytes(32))[:-1],b'\1broken'):
            with self.subTest(data=data[:4]),self.assertRaises(ValueError):unpack(data,32)

    def test_root_and_footer_limits(self):
        raw=fixture_state()
        for data in (b'',b'wrong',raw[:-1],raw+b'\0',raw+b'\0'*13):
            with self.assertRaises(ValueError):decode(data)
        self.assertEqual(decode(raw),decode(raw+bytes(8)))
        self.assertEqual(decode(raw),decode(raw+bytes(12)))

    def test_duplicate_or_missing_chunk_rejected(self):
        raw=fixture_state()
        for data in (chunk(b'NST\x1a',b''),chunk(b'NST\x1a',raw[8:]+raw[8:])):
            with self.assertRaises(ValueError):decode(data)

    def test_rendering_state_refused(self):
        raw=fixture_state();old=bytes.fromhex('0000000021002100000000')
        for position,value in ((0,0x80),(0,0x20),(1,0x18)):
            new=bytearray(old);new[position]=value
            with self.assertRaises(ValueError):decode(raw.replace(old,new))


class PaletteProfileTests(unittest.TestCase):
    def test_all_byte_values_and_all_palette_aliases_in_plan(self):
        rows=cases();self.assertEqual(len(rows),304)
        self.assertEqual(len(set(r['name'] for r in rows)),304)
        # Program naming explicitly identifies the 256 paired inputs, not a
        # claim that all operand/gray/latch combinations are a Cartesian sweep.
        self.assertEqual({int(r['name'].split('-')[1],16) for r in rows[:256]},set(range(256)))
        self.assertEqual({int(r['name'].split('-')[2],16) for r in rows[:256]},set(range(256)))
        self.assertTrue(all(r['events']==[] for r in rows))

    def test_explicit_profile_and_immutable_adapter(self):
        p=read_case(0,255);before=copy.deepcopy(p);n=underlying(p)
        self.assertEqual(p,before);self.assertEqual(n['memory_model'],'mmc5-chr-blank')
        self.assertIs(validate(p),p)
        with self.assertRaises(ValueError):validate(n)

    def test_bad_plan_types_fields_and_values(self):
        p=read_case(0,255)
        for k,v in (('chr_banks',True),('steps',32),('extra',1),('name','../escape')):
            with self.assertRaises(ValueError):validate(dict(p,**{k:v}))

    def test_complete_boot_fits_reserved_region(self):
        for mode in range(4):self.assertLessEqual(len(boot_code(mode)),512)

    def test_actual_native_build_and_original_separation(self):
        p=read_case(16,255)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);n=create_nes(out/'nes',p).read_bytes()
            s=create_native(out/'native',p,expected_initial(underlying(p))).read_bytes()
            self.assertEqual(s[32768:32768+p['prg_banks']*8192],n[16:16+p['prg_banks']*8192])
            self.assertIn('jsr PaletteDataRead',(out/'native/program.inc').read_text())
            self.assertIn('jsr PaletteDataWrite',(out/'native/program.inc').read_text())

    def test_no_production_change_or_new_unprotected_context(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('snes/src/native.s','tools/build_native.py'):
            self.assertNotIn('palette_timeline',(root/name).read_text())
        text=(root/'snes/src/palette_timeline.inc').read_text()
        # No temporary live-v assignment in the shadow-read resolver.
        shadow=text.split('.proc PaletteShadow')[1].split('.endproc')[0]
        self.assertNotIn('sta PV+6',shadow)

    def test_comparison_never_masks_observed_cpu_results(self):
        p=read_case(0,255);ref,actual=sample_capture()
        self.assertTrue(compare(p,ref,actual)['passed'])
        for key,size in (('cpu_ram',2048),('cpu_registers',7),('ppu_state',10),('palette',32),('ciram',2048)):
            bad=dict(actual);value=bytearray.fromhex(bad[key]);value[-1]^=0x80;bad[key]=value.hex()
            with self.assertRaises((RuntimeError,ValueError)):compare(p,ref,bad)
            bad=dict(actual);bad[key]='00'*(size-1)
            with self.assertRaises(ValueError):compare(p,ref,bad)

    def test_fault_missing_budget_and_incomplete_records_rejected(self):
        p=read_case(0,255);ref=decode(fixture_state())
        for key,value in (('complete',False),('status',5),('marker',0xEE),('completed_steps',30)):
            report=dict(ref,complete=True,status=0,marker=0x5A,completed_steps=31)
            report[key]=value
            with self.assertRaises(RuntimeError):compare(p,ref,report)


    def test_boolean_completion_status_or_count_rejected(self):
        ref,actual=sample_capture();p=read_case(0,255)
        for key,value in (('complete',1),('status',False),('completed_steps',True)):
            with self.assertRaises(RuntimeError):compare(p,ref,dict(actual,**{key:value}))

    def test_missing_short_and_whitespace_shortened_records_rejected(self):
        ref,actual=sample_capture();p=read_case(0,255)
        for key,size in (('records',2080),('ppu_records',16),('chr_records',48)):
            for rows in (None,[],actual[key][:-1],['00'*(size-1)+'  ']*31):
                with self.assertRaises(ValueError):compare(p,ref,dict(actual,**{key:rows}))

    def test_final_native_state_must_equal_retired_record(self):
        ref,actual=sample_capture();p=read_case(0,255)
        for byte in (4,9,18,32,2079):
            bad=copy.deepcopy(actual);row=bytearray.fromhex(bad['records'][-1]);row[byte]^=1
            bad['records'][-1]=row.hex()
            with self.assertRaises(ValueError):compare(p,ref,bad)
        bad=copy.deepcopy(actual);row=bytearray.fromhex(bad['ppu_records'][-1]);row[9]^=1
        bad['ppu_records'][-1]=row.hex()
        with self.assertRaises(ValueError):compare(p,ref,bad)

    def test_checkpoint_order_cannot_be_faked_with_duplicate_records(self):
        ref,actual=sample_capture();actual['records'][1]=actual['records'][0]
        with self.assertRaises(ValueError):compare(read_case(0,255),ref,actual)

    def test_guest_request_stimulus_is_not_an_unmodified_reference_test(self):
        p=read_case(0,255);p['events']=[dict(cycle=1,irq=False,nmi=True)]
        with self.assertRaises(ValueError):validate(p)

    def test_reserved_ppu_state_bits_are_rejected_not_masked(self):
        raw=fixture_state();old=bytes.fromhex('0000000021002100000000')
        for i,mask in ((4,128),(6,128),(7,16)):
            changed=bytearray(old);changed[i]|=mask
            with self.assertRaises(ValueError):decode(raw.replace(old,changed))

    def test_guard_requires_exact_prior_state_and_retirement_count(self):
        ref,actual=sample_capture();stop=int.from_bytes(bytes.fromhex(ref['cpu_registers'])[:2],'little')
        actual.update(complete=False,marker=0xEE,status=5,completed_steps=4)
        self.assertTrue(compare_guard(read_case(0,255),ref,actual,stop,4)['rejected'])
        for key,value in (('complete',True),('completed_steps',5),('status',0)):
            with self.assertRaises(RuntimeError):compare_guard(read_case(0,255),ref,dict(actual,**{key:value}),stop,4)
        changed=dict(actual);value=bytearray.fromhex(changed['palette']);value[1]=1;changed['palette']=value.hex()
        with self.assertRaises(RuntimeError):compare_guard(read_case(0,255),ref,changed,stop,4)

    def test_all_guard_programs_remain_admitted_before_runtime_refusal(self):
        rows=guard_cases();self.assertEqual(len(rows),6)
        for plan,stop,count in rows:
            self.assertIs(validate(plan),plan)
            self.assertEqual(plan['starts'][count],stop)

    def test_host_metadata_types_and_target_waits_required(self):
        ref,base=sample_capture()
        for key,size in (('cartridge_ram',32768),('exram',1024),('protected_memory',132),('ppu_chr_context',28)):
            base[key]=bytes(size).hex()
        host=dict(base,host_enabled=True,host=dict(count=31,work=31,fault=0,depth=0,peak=1,
                  min_sp=0x1E92,low_canary=0xA5,high_canary=0x5A,wait_hits=31,nested_wait_hits=0))
        self.assertEqual(check_host(base,host,'cost'),31)
        for key,value in (('count',True),('wait_hits',30),('depth',1),('min_sp',0x1E8F)):
            bad=copy.deepcopy(host);bad['host'][key]=value
            with self.assertRaises((ValueError,RuntimeError)):check_host(base,bad,'cost')

    def test_nested_interrupts_must_really_occur(self):
        ref,base=sample_capture();h=dict(base,host_enabled=True,host=dict(count=62,work=62,
            fault=0,depth=0,peak=2,min_sp=0x1E92,low_canary=0xA5,high_canary=0x5A,
            wait_hits=31,nested_wait_hits=31))
        self.assertEqual(check_host(base,h,'nested'),62)
        h['host']['nested_wait_hits']=0
        with self.assertRaises(RuntimeError):check_host(base,h,'nested')

    def test_invalid_worker_and_smoke_settings_rejected_before_output(self):
        for jobs in (True,0,5,1.5):
            with self.assertRaises(ValueError):run_matrix(None,None,Path('unused'),jobs=jobs)
        for limit in (True,0,305):
            with self.assertRaises(ValueError):run_matrix(None,None,Path('unused'),limit=limit)


    def test_both_missing_external_host_snapshots_do_not_pass(self):
        ref,base=sample_capture();host=dict(base,host_enabled=True,host=dict(count=31,work=31,
            fault=0,depth=0,peak=1,min_sp=0x1E92,low_canary=0xA5,high_canary=0x5A,
            wait_hits=0,nested_wait_hits=0))
        for key in ('cartridge_ram','exram','protected_memory','ppu_chr_context'):
            a=dict(base);b=dict(host);del a[key];del b[key]
            with self.assertRaises(ValueError):check_host(a,b,'free')


if __name__=='__main__':unittest.main()
