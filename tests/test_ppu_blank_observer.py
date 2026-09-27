"""Compiled PPU snapshots must freeze at the same recorded CPU boundaries."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from instrument_ppu_blank import instrument,PPU_GETTER,MAPPER_GETTER,fetch_snapshots
import instrument_cpu_io_timeline as base
from instrument_timeline_probe import BEGIN,END


class PPUObserverTests(unittest.TestCase):
    def seed(self,root):
        (root/'src/boards').mkdir(parents=True)
        (root/'src/x6502.c').write_text('#include "sound.h"\n'+BEGIN+'\n'+END)
        (root/'src/boards/mmc5.c').write_text('static uint8_t WRAMMaskEnable[2];\nstatic uint8_t WRAMPage;\nstatic uint8_t mul[2];\nstatic uint8_t *ExRAM = NULL;\n')
        (root/'src/ppu.c').write_text('uint8_t VRAMBuffer = 0, PPUGenLatch = 0;\nuint32_t TempAddr = 0, RefreshAddr = 0;\nuint8_t vtoggle = 0;\n')

    def test_install_does_not_replace_cpu_mapper_or_ppu(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);before=(root/'src/ppu.c').read_text()
            self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            self.assertEqual((root/'src/ppu.c').read_text(),before+PPU_GETTER)
            self.assertTrue((root/'src/boards/mmc5.c').read_text().endswith(base.GETTER+MAPPER_GETTER))

    def test_unknown_source_fails_before_modification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/ppu.c';p.write_text('unknown PPU')
            with self.assertRaises(ValueError):instrument(root)
            self.assertEqual(p.read_text(),'unknown PPU')
            self.assertFalse((root/'src/n2s_timeline_probe.h').exists())

    def test_changed_installed_snapshot_and_hooks_fail(self):
        for file,old,new in (('n2s_timeline_probe.h','tl_count+1==tl_limit','tl_count+2==tl_limit'),
                             ('x6502.c','timestampbase+(uint64_t)timestamp','timestamp'),
                             ('ppu.c','out[9]=PPUGenLatch','out[9]=0')):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);self.seed(root);instrument(root);p=root/'src'/file
                p.write_text(p.read_text().replace(old,new))
                with self.assertRaises(ValueError):instrument(root)

    def test_fetch_bad_count_precedes_core_use(self):
        for count in (True,0,32,-1):
            with self.assertRaises(ValueError):fetch_snapshots(None,count)

    def test_compiled_snapshots_freeze_registers_and_full_ciram(self):
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
static uint8_t PPU[4],vtoggle,XOffset,VRAMBuffer,PPUGenLatch,NTARAM[2048];
static uint32_t TempAddr,RefreshAddr;
static uint8_t NTAMirroring,NTFill,ATFill;
static void X6502_IRQBegin(unsigned q){(void)q;}
static void X6502_IRQEnd(unsigned q){(void)q;}
static void TriggerNMI(void){}
void n2s_m5_wram_metadata(uint8_t *out){out[0]=0;out[1]=0;}
int n2s_m5_cpu_io(uint8_t *out,uint8_t *memory){
 out[0]=3;out[1]=out[2]=0;if(memory)memset(memory,0xa5,1024);return 1;
}
'''
            after=r'''
int main(void){
 static uint8_t cpu[2048],prg[32768],cart[32768];unsigned i;
 PRGptr[0]=prg;PRGsize[0]=32768;PRGptr[0x10]=cart;PRGsize[0x10]=32768;
 for(i=16;i<32;i++)Page[i]=(uint8_t*)((uintptr_t)prg-0x8000);
 for(i=12;i<16;i++)Page[i]=(uint8_t*)((uintptr_t)cart-0x6000);
 memset(NTARAM,0x3c,2048);TempAddr=0x2345;RefreshAddr=0x2789;
 NTAMirroring=0x44;NTFill=0x11;ATFill=2;vtoggle=1;XOffset=7;VRAMBuffer=0x9a;PPUGenLatch=0xb6;
 assert(retro_n2s_timeline_configure(0xe100,1,0,0));
 tl_before(0xe100,0,0,0,0x24,0xfd,100,0,cpu);
 assert(retro_n2s_ppu_blank_size(0)==16 && retro_n2s_ppu_blank_size(1)==2048);
 assert(tl_ppu_rows[0][2]==1 && tl_ppu_rows[0][3]==7);
 assert(tl_ppu_rows[0][4]==0x45 && tl_ppu_rows[0][5]==0x23);
 assert(tl_ppu_rows[0][6]==0x89 && tl_ppu_rows[0][7]==0x27);
 assert(tl_ppu_rows[0][8]==0x9a && tl_ppu_rows[0][9]==0xb6);
 NTARAM[2047]=0x73;RefreshAddr=0x3000;NTFill=0x28;
 tl_after(0xea,102);tl_before(0xe101,0,0,0,0x24,0xfd,102,0,cpu);
 assert(retro_n2s_timeline_status(0)==2 && !retro_n2s_timeline_status(3));
 memset(NTARAM,0,2048);RefreshAddr=0;NTFill=0;
 assert(retro_n2s_ciram_data(0)[2047]==0x3c && retro_n2s_ciram_data(1)[2047]==0x73);
 assert(tl_ppu_rows[1][7]==0x30 && tl_ppu_rows[1][11]==0x28);
 assert(tl_ppu_rows[1][13]==0 && tl_ppu_rows[1][14]==0 && tl_ppu_rows[1][15]==0);
 return 0;
}
'''
            text=before+PPU_GETTER+MAPPER_GETTER+(root/'src/n2s_timeline_probe.h').read_text()+after
            (root/'test.c').write_text(text)
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
