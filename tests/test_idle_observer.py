"""Compiled read-only observer, ABI, event counts, overflow and anchor checks."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from idle_observer import Observer, Record, validate_config
from instrument_idle_observer import instrument, HEADER


class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        code='#include "idle_observer.h"\nN2S_EXPORT void test_step(uint16_t pc,uint16_t bank,const uint8_t *ram){n2s_idle_step(pc,bank,ram);}\n'
        (cls.root/'test.c').write_text(code)
        compiler=shutil.which('cc')
        if not compiler:raise unittest.SkipTest('C compiler unavailable')
        subprocess.run([compiler,'-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-I',str(HEADER.parent),str(cls.root/'test.c'),'-o',str(cls.root/'test.so')],check=True)
        cls.lib=C.CDLL(str(cls.root/'test.so'))
        cls.lib.test_step.argtypes=[C.c_uint16,C.c_uint16,C.POINTER(C.c_uint8)]
        cls.lib.test_step.restype=None

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.ram=(C.c_uint8*2048)();self.ram[31]=84
        self.observer=Observer(self.lib,0xe047,0xe059,(31,60),8)

    def step(self,pc=0xe047):self.lib.test_step(pc,0xad,self.ram)

    def test_ticks_snapshots_and_direct_ram_unchanged(self):
        before=bytes(self.ram);self.observer.before_frame(1)
        self.step();self.step();self.step(0xe059)
        self.observer.before_frame(2);self.step();self.step(0xe059)
        r=self.observer.finish();self.assertEqual(bytes(self.ram),before)
        self.assertEqual([x['ticks_since_previous_sample'] for x in r['records']],[2,1])
        self.assertEqual([x['ram']['001f'] for x in r['records']],[84,84])
        self.assertEqual(r['ticks'],3);self.assertTrue(r['complete'])

    def test_overflow_rejected_instead_of_passing_prefix(self):
        self.observer=Observer(self.lib,0xe047,0xe059,(31,),1)
        self.observer.before_frame(1);self.step(0xe059);self.step(0xe059)
        with self.assertRaisesRegex(RuntimeError,'overflow'):self.observer.finish()

    def test_no_samples_rejected(self):
        self.observer.before_frame(1);self.step()
        with self.assertRaisesRegex(RuntimeError,'no matching'):self.observer.finish()

    def test_disabled_observer_does_not_keep_counting(self):
        self.observer.before_frame(1);self.step(0xe059);self.observer.finish();self.step()
        self.assertEqual(self.lib.retro_n2s_idle_status(2),0)

    def test_invalid_reconfiguration_disables_and_clears_old_evidence(self):
        self.observer.before_frame(1);self.step(0xe059)
        addresses=(C.c_uint16*1)(2048)
        self.assertEqual(self.lib.retro_n2s_idle_configure(0xe047,0xe059,addresses,1,8),0)
        self.step(0xe059);self.assertEqual(self.lib.retro_n2s_idle_status(0),0)
        self.assertEqual(self.lib.retro_n2s_idle_status(5),0)

    def test_frames_must_increase(self):
        for n in (True,0,-1,2000001):
            with self.assertRaises(ValueError):self.observer.before_frame(n)
        self.observer.before_frame(5)
        with self.assertRaises(ValueError):self.observer.before_frame(5)

    def test_invalid_python_config_rejected(self):
        for config in [(True,0xe059,(31,),8),(0x7000,0xe059,(31,),8),
                       (0xe047,0xe047,(31,),8),(0xe047,0xe059,(),8),
                       (0xe047,0xe059,(31,31),8),(0xe047,0xe059,(2048,),8),
                       (0xe047,0xe059,(31,),32769),(0xe047,0xe059,(31,),True)]:
            with self.subTest(config=config),self.assertRaises(ValueError):validate_config(*config)

    def test_c_and_cpp_record_abi_match(self):
        compiler=shutil.which('c++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-I',str(HEADER.parent),'-x','c++',str(self.root/'test.c'),'-o',str(self.root/'cpp.so')],check=True)
        lib=C.CDLL(str(self.root/'cpp.so'));lib.retro_n2s_idle_status.restype=C.c_uint64
        self.assertEqual(lib.retro_n2s_idle_status(4),C.sizeof(Record))

    def test_both_dispatch_anchors_and_idempotence(self):
        for platform,text,path in [('nes','#include "sound.h"\n\t\tb1 = RdMem(_PC);\n','src/x6502.c'),
                                   ('snes','#include "memmap.h"\n\t\tuint8\t\t\t\tOp;\n','cpuexec.cpp')]:
            root=self.root/platform;file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text)
            self.assertTrue(instrument(root,platform));self.assertFalse(instrument(root,platform))
            installed=file.read_text();self.assertIn('n2s_idle_step',installed)
            self.assertNotIn('Cycles +=',installed);self.assertNotIn('RdMem(',installed.replace('b1 = RdMem(_PC);',''))
            (file.parent/'n2s_idle_observer.h').write_text('changed')
            with self.assertRaisesRegex(ValueError,'header changed'):instrument(root,platform)

    def test_unknown_and_duplicate_anchors_rejected_without_writes(self):
        root=self.root/'bad';root.mkdir(exist_ok=True);p=root/'cpuexec.cpp';p.write_text('unknown')
        with self.assertRaises(ValueError):instrument(root,'snes')
        self.assertEqual(p.read_text(),'unknown');self.assertFalse((root/'n2s_idle_observer.h').exists())
        with self.assertRaises(ValueError):instrument(root,'other')


if __name__=='__main__':unittest.main()
