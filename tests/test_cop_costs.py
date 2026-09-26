"""Diagnostic accounting is tested independently of running a commercial game."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from instrument_frame_costs import DECL, instrument

class CopCostTests(unittest.TestCase):
    def test_old_instrumentation_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'cpuexec.cpp'
            p.write_text('// NES2SNES_FRAME_COSTS_V1\n')
            before=p.read_bytes()
            with self.assertRaises(ValueError):instrument(Path(td))
            self.assertEqual(p.read_bytes(),before)

    @unittest.skipUnless(shutil.which('g++'), 'requires a C++ compiler')
    def test_executed_cpp_accounting_state_machine(self):
        main=r'''
#include <assert.h>
int main() {
    retro_n2s_cost_reset();
    n2s_cop_step(0xA1,0x8123,0x02,0,12);
    n2s_cop_step(0x80,0x8000,0xEA,0x80,6);
    // Short nested interrupt returns to the handler, not the guest.
    n2s_cop_step(0x80,0x9000,0x40,0x80,8);
    assert(retro_n2s_cop_status(1)==1);
    assert(retro_n2s_cop_calls(0)[0x8123]==0);
    n2s_cop_step(0x80,0x8001,0x40,0xA1,10);
    assert(retro_n2s_cop_calls(0)[0x8123]==1);
    assert(retro_n2s_cop_costs(0)[0x8123]==36);
    assert(retro_n2s_cop_status(1)==0);
    // The same CPU address in a different execution mapping is separate.
    n2s_cop_step(0xA2,0x8123,0x02,0,12);
    // A bank-switching instruction may return in another valid mapping.
    n2s_cop_step(0,0x8000,0x40,0xC0,10);
    assert(retro_n2s_cop_costs(1)[0x8123]==22);
    assert(retro_n2s_cop_calls(0)[0x8123]==1);
    assert(retro_n2s_cop_costs(32)==0);
    assert(retro_n2s_cop_calls(32)==0);
    // An incomplete start boundary must not be counted as a whole call.
    n2s_cop_step(0xA1,0x8123,0x02,0,12);
    retro_n2s_cost_reset();
    n2s_cop_step(0,0x8000,0x40,0xA1,10);
    assert(retro_n2s_cop_calls(0)[0x8123]==0);
    // Origins outside the bridge execution region are not guest COPs.
    n2s_cop_step(0x80,0x8123,0x02,0,12);
    n2s_cop_step(0xA1,0x1200,0x02,0,12);
    assert(retro_n2s_cop_status(1)==0);
    // Re-entering without a return is visible, not silently double counted.
    n2s_cop_step(0xA1,0x8123,0x02,0,12);
    n2s_cop_step(0xA1,0x8125,0x02,0,12);
    assert(retro_n2s_cop_status(0)==1);
    assert(retro_n2s_cop_status(2)==12);
    assert(retro_n2s_cop_calls(0)[0x8123]==0);
    retro_n2s_cost_reset();
    assert(retro_n2s_cop_status(0)==0);
    assert(retro_n2s_cop_status(2)==0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);p=r/'test.cpp'
            p.write_text('struct { int Cycles; } CPU;\n'+DECL+main)
            subprocess.run(['g++','-std=c++11','-O2',str(p),'-o',str(r/'test')],check=True,timeout=30,capture_output=True)
            subprocess.run([str(r/'test')],check=True,timeout=10,capture_output=True)

if __name__=='__main__':unittest.main()
