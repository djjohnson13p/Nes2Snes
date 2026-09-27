#!/usr/bin/env python3
"""Read-only MMC5 PRG-RAM observation beside the fixture request harness.

CPU, mapper, RAM writes and interrupt dispatch remain original. Captured physical
bank identities come from live mapped pointers, not the native address formula.
Full cartridge RAM is saved at the first and last recorded instruction boundaries;
post-window execution must not be mistaken for that last endpoint snapshot.
"""
from pathlib import Path
import argparse
from instrument_timeline_probe import instrument as base, HEADER, PRE, POST, MARKER as BASE_MARKER

MARKER='NES2SNES_WRAM_TIMELINE_V1'
GETTER='''\n/* NES2SNES_WRAM_TIMELINE_V1: observation only; no mapper state write. */
void n2s_m5_wram_metadata(uint8_t *out) {
    out[0]=(uint8_t)((WRAMMaskEnable[0]&3)|((WRAMMaskEnable[1]&3)<<2));
    out[1]=(uint8_t)(WRAMPage&7);
}
'''
HELPER=r'''
extern void n2s_m5_wram_metadata(uint8_t *out);
static uint8_t tl_wram_initial[32768],tl_wram_final[32768];
TL_EXPORT unsigned retro_n2s_wram_size(void){return 32768;}
TL_EXPORT const uint8_t *retro_n2s_wram_data(unsigned final){
    return final ? tl_wram_final : tl_wram_initial;
}
static uint8_t tl_wram_bank(uint16_t address) {
    uintptr_t p,start;
    if(address<0x6000 || !Page[address>>11])return 255;
    p=(uintptr_t)Page[address>>11]+address;
    start=(uintptr_t)PRGptr[0];
    if(PRGptr[0] && p>=start && p-start<PRGsize[0])return (uint8_t)((p-start)/8192);
    start=(uintptr_t)PRGptr[0x10];
    if(PRGptr[0x10] && p>=start && p-start<32768)return (uint8_t)(128+(p-start)/8192);
    return 255;
}
'''
CAPTURE=r'''
    /* NES2SNES_WRAM_TIMELINE_V1 */
    {
        unsigned slot; uint8_t metadata[2];
        if(!PRGptr[0x10] || PRGsize[0x10]!=32768){tl_error=8;tl_active=0;return;}
        for(slot=0;slot<4;slot++)r->reserved[slot]=tl_wram_bank((uint16_t)(0x8000+slot*8192));
        r->reserved[4]=tl_wram_bank(pc);
        r->reserved[5]=tl_wram_bank(0x6000);
        n2s_m5_wram_metadata(metadata);
        r->reserved[6]=metadata[0];r->reserved[7]=metadata[1];
        if(!tl_count)memcpy(tl_wram_initial,PRGptr[0x10],32768);
        if(tl_count+1==tl_limit)memcpy(tl_wram_final,PRGptr[0x10],32768);
    }
'''


def instrument(source: Path) -> bool:
    dest=source/'src/n2s_timeline_probe.h';board=source/'src/boards/mmc5.c';cpu=source/'src/x6502.c'
    expected=b'#define TL_RAM_BYTES 2048\n'+HEADER.read_bytes()
    new=expected.decode().replace('static void tl_before(',HELPER+'\nstatic void tl_before(',1)
    anchor='    memcpy(r->ram,ram,TL_RAM_BYTES);'
    if new.count(anchor)!=1:raise ValueError('Cartridge capture anchor changed')
    new=new.replace(anchor,CAPTURE+anchor)
    # Strict unchanged board anchor; the getter only reads declared static state.
    content=board.read_text()
    for token in ('static uint8_t WRAMMaskEnable[2];','static uint8_t WRAMPage;'):
        if content.count(token)!=1:raise ValueError('Unexpected pinned MMC5 state declarations')
    if MARKER in content or (dest.is_file() and MARKER in dest.read_text()):
        text=cpu.read_text()
        if not content.endswith(GETTER) or content.count(MARKER)!=1 or not dest.is_file() or dest.read_text()!=new or any(text.count(v)!=1 for v in (PRE,POST,BASE_MARKER)):
            raise ValueError('Partial or altered cartridge observer')
        return False
    base(source,ram_bytes=2048)
    if dest.read_bytes()!=expected:raise ValueError('Unexpected base observer')
    board.write_text(content+GETTER);dest.write_text(new);cpu.touch();return True

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
