"""Read-only mapped-pointer observation and frozen instruction-boundary records."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from instrument_chr_blank import instrument,GETTER,expected_header
from instrument_ppu_blank import PPU_GETTER,MAPPER_GETTER
import test_ppu_blank_observer as fixture


class CHRObserverTests(unittest.TestCase):
    def seed(self,root):
        fixture.PPUObserverTests().seed(root)
        p=root/'src/boards/mmc5.c';p.write_text(p.read_text()+
            'static uint16_t CHRBanksA[8], CHRBanksB[4];\nstatic uint8_t mmc5vsize,MMC50x5130;\n')

    def test_exact_install_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);self.assertTrue(instrument(root));self.assertFalse(instrument(root))
            self.assertTrue((root/'src/boards/mmc5.c').read_text().endswith(GETTER))
            self.assertEqual((root/'src/n2s_timeline_probe.h').read_text(),expected_header())

    def test_unknown_board_is_rejected_before_modification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);p=root/'src/boards/mmc5.c';p.write_text('unknown')
            with self.assertRaises(ValueError):instrument(root)
            self.assertFalse((root/'src/n2s_timeline_probe.h').exists())

    def test_partial_modified_header_and_getter_rejected(self):
        for name in ('boards/mmc5.c','n2s_timeline_probe.h','x6502.c','ppu.c'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);self.seed(root);instrument(root);p=root/'src'/name
                text=p.read_text()
                if name=='x6502.c':text=text.replace('timestampbase+(uint64_t)timestamp','timestamp')
                else:text+='/* changed */'
                p.write_text(text)
                with self.assertRaises(ValueError):instrument(root)

    def test_compiled_actual_pointers_and_endpoint_freeze(self):
        before=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#define FCEU_IQEXT 1
#define FCEU_IQNMI 2
static uint8_t *Page[32],*PRGptr[32],*CHRptr[32],*VPage[8];
static uint32_t PRGsize[32],CHRsize[32];
static uint8_t PPU[4],vtoggle,XOffset,VRAMBuffer,PPUGenLatch,NTARAM[2048];
static uint32_t TempAddr,RefreshAddr;
static uint8_t NTAMirroring,NTFill,ATFill,mmc5vsize,MMC50x5130;
static uint16_t CHRBanksA[8];
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
 static uint8_t cpu[2048],prg[32768],cart[32768],chr[32768],out[48];unsigned i;
 PRGptr[0]=prg;PRGsize[0]=32768;PRGptr[0x10]=cart;PRGsize[0x10]=32768;
 CHRptr[0]=chr;CHRsize[0]=sizeof(chr);
 for(i=16;i<32;i++)Page[i]=(uint8_t*)((uintptr_t)prg-0x8000);
 for(i=12;i<16;i++)Page[i]=(uint8_t*)((uintptr_t)cart-0x6000);
 for(i=0;i<8;i++)VPage[i]=chr;
 mmc5vsize=3;MMC50x5130=0xff;CHRBanksA[7]=0x301;
 assert(retro_n2s_timeline_configure(0xe100,1,0,0));
 tl_before(0xe100,0,0,0,0x24,0xfd,100,0,cpu);
 assert(retro_n2s_chr_record_size()==48 && tl_chr_rows[0][1]==3);
 assert(tl_chr_rows[0][16]==1 && tl_chr_rows[0][17]==3);
 assert(tl_chr_rows[0][32]==7);
 VPage[7]=chr+1024;CHRBanksA[7]=0x111;
 tl_after(0xea,102);tl_before(0xe101,0,0,0,0x24,0xfd,102,0,cpu);
 assert(!retro_n2s_timeline_status(3) && retro_n2s_timeline_status(0)==2);
 VPage[7]=chr;CHRBanksA[7]=0;MMC50x5130=0;
 assert(tl_chr_rows[1][32]==8 && tl_chr_rows[1][16]==0x11);
 assert(tl_chr_rows[1][17]==1 && tl_chr_rows[1][1]==3);
 assert(tl_chr_rows[0][32]==7 && tl_chr_rows[0][16]==1);
 VPage[2]=0;assert(!n2s_chr_blank(out));
 VPage[2]=chr+1;assert(!n2s_chr_blank(out));
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.seed(root);instrument(root)
            text=before+PPU_GETTER+MAPPER_GETTER+GETTER+expected_header()+after
            p=root/'test.c';p.write_text(text)
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(p),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
