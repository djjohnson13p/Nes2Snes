#!/usr/bin/env python3
"""Read-only actual CHR register/physical-map observations beside PPU snapshots.

No mapper/PPU/CPU behavior or bus-read callback is replaced. Registers describe
pinned FCEUmm's index representation; admitted bank size is fixed after boot.
"""
from pathlib import Path
import argparse
import ctypes as C
import instrument_ppu_blank as base
from mmc5_chr_blank import RECORD_BYTES

MARKER='NES2SNES_CHR_BLANK_V1'
GETTER='''\n/* NES2SNES_CHR_BLANK_V1: observe actual registers and mapped pointers. */
int n2s_chr_blank(uint8_t *out) {
    unsigned i; uintptr_t first=(uintptr_t)CHRptr[0];
    if(!out || !first || !CHRsize[0])return 0;
    memset(out,0,48);out[0]=mmc5vsize&3;out[1]=MMC50x5130&3;
    for(i=0;i<8;i++) {
        uintptr_t mapped=(uintptr_t)VPage[i]+i*1024;
        uint32_t bank;
        if(!VPage[i] || mapped<first || mapped-first >= CHRsize[0] || ((mapped-first)&1023))return 0;
        bank=(uint32_t)((mapped-first)>>10);
        out[2+2*i]=(uint8_t)CHRBanksA[i];out[3+2*i]=(uint8_t)(CHRBanksA[i]>>8);
        out[18+2*i]=(uint8_t)bank;out[19+2*i]=(uint8_t)(bank>>8);
    }
    return 1;
}
'''
HELPER='''
extern int n2s_chr_blank(uint8_t *);
static uint8_t tl_chr_rows[TL_MAX_ROWS][48];
TL_EXPORT unsigned retro_n2s_chr_record_size(void){return 48;}
TL_EXPORT const uint8_t *retro_n2s_chr_records(void){return &tl_chr_rows[0][0];}
'''
CAPTURE='''
    /* NES2SNES_CHR_BLANK_V1 */
    if(!n2s_chr_blank(tl_chr_rows[tl_count])){tl_error=10;tl_active=0;return;}
'''


def expected_header():
    text=base.base.headers()[1].replace('static void tl_before(',base.HELPER+'\nstatic void tl_before(',1)
    text=text.replace('    memcpy(r->ram,ram,TL_RAM_BYTES);',base.CAPTURE+'    memcpy(r->ram,ram,TL_RAM_BYTES);',1)
    return text.replace('static void tl_before(',HELPER+'\nstatic void tl_before(',1).replace(
        '    memcpy(r->ram,ram,TL_RAM_BYTES);',CAPTURE+'    memcpy(r->ram,ram,TL_RAM_BYTES);',1)


def instrument(source):
    board=source/'src/boards/mmc5.c';header=source/'src/n2s_timeline_probe.h';cpu=source/'src/x6502.c'
    text=board.read_text()
    if MARKER in text or (header.is_file() and MARKER in header.read_text()):
        if not text.endswith(GETTER) or header.read_text()!=expected_header():raise ValueError('Partial/changed CHR observer')
        if not (source/'src/ppu.c').read_text().endswith(base.PPU_GETTER):raise ValueError('Changed PPU observation')
        if any(cpu.read_text().count(a)!=1 for a in (base.base.PRE,base.base.POST,base.base.CPU_MARKER)):
            raise ValueError('Changed CPU observation')
        return False
    for token in ('static uint16_t CHRBanksA[8], CHRBanksB[4];','mmc5vsize','MMC50x5130'):
        if token not in text:raise ValueError('Unexpected pinned CHR declarations')
    base.instrument(source)
    board.write_text(board.read_text()+GETTER);header.write_text(expected_header());cpu.touch();return True


def fetch_snapshots(lib,steps):
    if type(steps) is not int or not 1<=steps<=31:raise ValueError('Invalid CHR record count')
    lib.retro_n2s_chr_record_size.restype=C.c_uint
    lib.retro_n2s_chr_records.restype=C.c_void_p
    if lib.retro_n2s_chr_record_size()!=RECORD_BYTES:raise RuntimeError('CHR observer ABI mismatch')
    ptr=lib.retro_n2s_chr_records()
    if not ptr:raise RuntimeError('Missing CHR observations')
    raw=C.string_at(ptr,(steps+1)*RECORD_BYTES)
    return {'chr_records':[raw[i*48:(i+1)*48].hex() for i in range(steps+1)]}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
