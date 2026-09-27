"""Compiled observer bounds and pinned-source installation tests."""
from pathlib import Path
import ctypes
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from instrument_cycle_observer import instrument,HEADER,BEGIN,END


class CycleObserverTests(unittest.TestCase):
    def test_compiled_observer_records_real_passed_timestamps_and_refuses_overflow(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'cart.h').write_text('extern uint8_t *Page[32];\n')
            (root/'observer.h').write_bytes(HEADER.read_bytes())
            (root/'test.c').write_text(r'''
#include <assert.h>
#include "observer.h"
uint8_t *Page[32];
int main(void){
 uint8_t image[65536]={0},ram[2048]={0};uint16_t pcs[2]={0x8100,0x8100};unsigned i;
 for(i=0;i<32;i++)Page[i]=image;
 assert(sizeof(n2s_cycle_row)==32);
 image[0x8101]=0xff;image[0x8102]=0x55;ram[255]=0xab;ram[0]=0xcd;
 assert(retro_n2s_cycle_configure(pcs,1,1));
 n2s_cycle_begin(0x8100,0xb1,0x34,3,4,5,6,100,ram);n2s_cycle_end(0x8102,106);
 assert(n2s_cycle_rows[0].operand==0x55ff && n2s_cycle_rows[0].pointer==0xcdab);
 assert(n2s_cycle_rows[0].start==100 && n2s_cycle_rows[0].end==106);
 assert(n2s_cycle_rows[0].x==3 && n2s_cycle_rows[0].y==4 && n2s_cycle_rows[0].a==5);
 n2s_cycle_begin(0x8100,0xb1,0x34,3,4,5,6,110,ram);
 assert(retro_n2s_cycle_status(0)==1 && retro_n2s_cycle_status(1)==2 && !retro_n2s_cycle_status(4));
 assert(!retro_n2s_cycle_configure(pcs,2,4));
 assert(!retro_n2s_cycle_status(4) && !retro_n2s_cycle_status(0));
 assert(retro_n2s_cycle_configure(pcs,1,2));
 n2s_cycle_begin(0x8100,0xea,0,0,0,0,0,100,ram);n2s_cycle_end(0x8101,99);
 assert(retro_n2s_cycle_status(1)==4);
 assert(retro_n2s_cycle_configure(pcs,1,2));
 n2s_cycle_begin(0x8100,0xea,0,0,0,0,0,100,ram);retro_n2s_cycle_disable();
 assert(retro_n2s_cycle_status(3)==1);
 assert(!retro_n2s_cycle_configure(NULL,1,1));assert(!retro_n2s_cycle_status(3));
 return 0;
}
''')
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

    def seed(self,root):
        (root/'src').mkdir();(root/'src/x6502.c').write_text('#include "sound.h"\n'+BEGIN+'\n'+END)

    def test_exact_hooks_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            text=(root/'src/x6502.c').read_text()
            self.assertEqual(text.count('n2s_cycle_begin('),1);self.assertEqual(text.count('n2s_cycle_end('),1)

    def test_changed_anchor_rejected_without_partial_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/x6502.c';before=p.read_text().replace(END,'different');p.write_text(before)
            with self.assertRaises(ValueError):instrument(root)
            self.assertEqual(p.read_text(),before);self.assertFalse((root/'src/n2s_cycle_observer.h').exists())

    def test_changed_installed_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);instrument(root);(root/'src/n2s_cycle_observer.h').write_text('changed')
            with self.assertRaises(ValueError):instrument(root)

    def test_duplicate_hook_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/x6502.c';p.write_text(p.read_text()+'\n'+BEGIN)
            with self.assertRaises(ValueError):instrument(root)

    def test_changed_installed_timestamp_hook_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);instrument(root);p=root/'src/x6502.c'
            p.write_text(p.read_text().replace('timestampbase+(uint64_t)timestamp','timestamp'))
            with self.assertRaises(ValueError):instrument(root)
