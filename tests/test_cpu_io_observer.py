"""Compiled snapshots must survive execution after the recorded window."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from instrument_cpu_io_timeline import instrument,GETTER,headers
import instrument_wram_timeline as wram
from instrument_timeline_probe import BEGIN,END


class CPUIOObserverTests(unittest.TestCase):
    def seed(self,root):
        (root/'src/boards').mkdir(parents=True)
        (root/'src/x6502.c').write_text('#include "sound.h"\n'+BEGIN+'\n'+END)
        (root/'src/boards/mmc5.c').write_text('static uint8_t WRAMMaskEnable[2];\nstatic uint8_t WRAMPage;\nstatic uint8_t mul[2];\nstatic uint8_t *ExRAM = NULL;\n')

    def test_mapper_remains_unchanged_except_read_only_getters(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);before=(root/'src/boards/mmc5.c').read_text()
            self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            self.assertEqual((root/'src/boards/mmc5.c').read_text(),before+wram.GETTER+GETTER)
            self.assertEqual((root/'src/n2s_timeline_probe.h').read_text(),headers()[1])

    def test_missing_state_declaration_fails_before_editing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/boards/mmc5.c'
            p.write_text(p.read_text().replace('static uint8_t mul[2];','wrong'))
            with self.assertRaises(ValueError):instrument(root)
            self.assertFalse((root/'src/n2s_timeline_probe.h').exists())

    def test_partial_getter_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/boards/mmc5.c';p.write_text(p.read_text()+GETTER)
            with self.assertRaises(ValueError):instrument(root)

    def test_changed_snapshot_or_hook_is_rejected(self):
        for file,old,new in [('n2s_timeline_probe.h','tl_count+1==tl_limit','tl_count+2==tl_limit'),
                             ('x6502.c','timestampbase+(uint64_t)timestamp','timestamp')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);self.seed(root);instrument(root);p=root/'src'/file;p.write_text(p.read_text().replace(old,new))
                with self.assertRaises(ValueError):instrument(root)

    def test_compiled_exram_and_registers_are_frozen_at_endpoints(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);instrument(root)
            before=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#define FCEU_IQEXT 1
#define FCEU_IQNMI 2
static uint8_t *Page[32],*PRGptr[32];
static uint32_t PRGsize[32];
static uint8_t exram[1024],state[3]={3,17,255};
static void X6502_IRQBegin(unsigned q){(void)q;}
static void X6502_IRQEnd(unsigned q){(void)q;}
static void TriggerNMI(void){}
void n2s_m5_wram_metadata(uint8_t *out){out[0]=6;out[1]=2;}
int n2s_m5_cpu_io(uint8_t *out,uint8_t *memory){
 memcpy(out,state,3);if(memory)memcpy(memory,exram,1024);return 1;
}
'''
            after=r'''
int main(void){
 static uint8_t cpu[2048],prg[32768],cart[32768];unsigned i;
 PRGptr[0]=prg;PRGsize[0]=32768;PRGptr[0x10]=cart;PRGsize[0x10]=32768;
 for(i=16;i<32;i++)Page[i]=(uint8_t*)((uintptr_t)prg-0x8000);
 for(i=12;i<16;i++)Page[i]=(uint8_t*)((uintptr_t)cart-0x6000);
 memset(exram,0xa5,1024);
 assert(retro_n2s_timeline_configure(0xe100,1,0,0));
 tl_before(0xe100,0,0,0,0x24,0xfd,100,0,cpu);
 assert(tl_rows[0].reserved[8]==3 && tl_rows[0].reserved[9]==17 && tl_rows[0].reserved[10]==255);
 assert(retro_n2s_exram_size()==1024 && retro_n2s_exram_data(0)[1023]==0xa5);
 exram[1023]=0x73;state[0]=2;state[1]=128;tl_after(0xea,102);
 tl_before(0xe101,0,0,0,0x24,0xfd,102,0,cpu);
 assert(retro_n2s_timeline_status(0)==2 && !retro_n2s_timeline_status(3));
 memset(exram,0x11,1024);state[1]=0;
 assert(retro_n2s_exram_data(1)[1023]==0x73 && retro_n2s_exram_data(1)[0]==0xa5);
 assert(retro_n2s_exram_data(0)[1023]==0xa5);
 assert(tl_rows[1].reserved[8]==2 && tl_rows[1].reserved[9]==128);
 return 0;
}
'''
            (root/'test.c').write_text(before+headers()[1]+after)
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
