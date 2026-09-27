#!/usr/bin/env python3
"""Read-only PPU state/CIRAM endpoints beside the existing request harness.

No PPU, mapper, CPU or bus callback behavior is replaced. Extra per-instruction
PPU rows and first/final CIRAM copies are separate from the existing CPU ABI.
"""
from pathlib import Path
import argparse
import ctypes as C
import instrument_cpu_io_timeline as base
from mmc5_ppu_blank import PPU_BYTES,CIRAM_BYTES

MARKER='NES2SNES_PPU_BLANK_V1'
PPU_GETTER='''\n/* NES2SNES_PPU_BLANK_V1: observation only. v/t retain their hardware 15 bits. */
void n2s_ppu_blank(uint8_t *out,uint8_t *memory) {
    memset(out,0,16);
    out[0]=PPU[0];out[1]=PPU[1];out[2]=vtoggle;out[3]=XOffset;
    out[4]=(uint8_t)TempAddr;out[5]=(uint8_t)((TempAddr>>8)&0x7f);
    out[6]=(uint8_t)RefreshAddr;out[7]=(uint8_t)((RefreshAddr>>8)&0x7f);
    out[8]=VRAMBuffer;out[9]=PPUGenLatch;
    if(memory)memcpy(memory,NTARAM,2048);
}
'''
MAPPER_GETTER='''\n/* NES2SNES_PPU_BLANK_V1: read actual nametable/fill register state. */
void n2s_m5_blank(uint8_t *out) {
    out[0]=NTAMirroring;out[1]=NTFill;out[2]=ATFill;
}
'''
HELPER='''
extern void n2s_ppu_blank(uint8_t *,uint8_t *);
extern void n2s_m5_blank(uint8_t *);
static uint8_t tl_ppu_rows[TL_MAX_ROWS][16];
static uint8_t tl_ciram_initial[2048],tl_ciram_final[2048];
TL_EXPORT unsigned retro_n2s_ppu_blank_size(unsigned kind) {return kind ? 2048 : 16;}
TL_EXPORT const uint8_t *retro_n2s_ppu_blank_rows(void) {return &tl_ppu_rows[0][0];}
TL_EXPORT const uint8_t *retro_n2s_ciram_data(unsigned final) {
    return final ? tl_ciram_final : tl_ciram_initial;
}
'''
CAPTURE='''
    /* NES2SNES_PPU_BLANK_V1 */
    n2s_ppu_blank(tl_ppu_rows[tl_count], !tl_count ? tl_ciram_initial :
                  tl_count+1==tl_limit ? tl_ciram_final : NULL);
    n2s_m5_blank(tl_ppu_rows[tl_count]+10);
'''


def instrument(source:Path)->bool:
    ppu=source/'src/ppu.c';board=source/'src/boards/mmc5.c';header=source/'src/n2s_timeline_probe.h'
    cpu=source/'src/x6502.c';original=base.headers()[1]
    expected=original.replace('static void tl_before(',HELPER+'\nstatic void tl_before(',1)
    expected=expected.replace('    memcpy(r->ram,ram,TL_RAM_BYTES);',CAPTURE+'    memcpy(r->ram,ram,TL_RAM_BYTES);',1)
    if MARKER in ppu.read_text() or MARKER in board.read_text() or (header.exists() and MARKER in header.read_text()):
        if not ppu.read_text().endswith(PPU_GETTER) or not board.read_text().endswith(MAPPER_GETTER) or header.read_text()!=expected:
            raise ValueError('Partial or changed blank-PPU observation')
        for anchor in (base.PRE,base.POST,base.CPU_MARKER):
            if cpu.read_text().count(anchor)!=1:raise ValueError('Changed CPU observation')
        return False
    for token in ('uint8_t VRAMBuffer = 0, PPUGenLatch = 0;', 'uint32_t TempAddr = 0, RefreshAddr = 0;', 'uint8_t vtoggle = 0;'):
        if ppu.read_text().count(token)!=1:raise ValueError('Unexpected pinned PPU declarations')
    base.instrument(source)
    if header.read_text()!=original:raise ValueError('Unexpected CPU-I/O observation')
    ppu.write_text(ppu.read_text()+PPU_GETTER);board.write_text(board.read_text()+MAPPER_GETTER)
    header.write_text(expected);cpu.touch();return True


def fetch_snapshots(lib,steps:int)->dict:
    if type(steps) is not int or not 1<=steps<=31:raise ValueError('Invalid PPU record count')
    lib.retro_n2s_ppu_blank_size.argtypes=[C.c_uint];lib.retro_n2s_ppu_blank_size.restype=C.c_uint
    lib.retro_n2s_ppu_blank_rows.argtypes=[];lib.retro_n2s_ppu_blank_rows.restype=C.c_void_p
    lib.retro_n2s_ciram_data.argtypes=[C.c_uint];lib.retro_n2s_ciram_data.restype=C.c_void_p
    if lib.retro_n2s_ppu_blank_size(0)!=PPU_BYTES or lib.retro_n2s_ppu_blank_size(1)!=CIRAM_BYTES:
        raise RuntimeError('Blank PPU capture ABI mismatch')
    ptr=lib.retro_n2s_ppu_blank_rows()
    if not ptr:raise RuntimeError('Missing blank PPU records')
    raw=C.string_at(ptr,(steps+1)*PPU_BYTES)
    result={'ppu_records':[raw[i*16:(i+1)*16].hex() for i in range(steps+1)]}
    for key,final in (('initial_ciram',0),('ciram',1)):
        ptr=lib.retro_n2s_ciram_data(final)
        if not ptr:raise RuntimeError('Missing CIRAM snapshot')
        result[key]=C.string_at(ptr,CIRAM_BYTES).hex()
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
