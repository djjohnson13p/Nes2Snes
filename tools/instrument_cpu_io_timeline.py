#!/usr/bin/env python3
"""Read-only ExRAM/multiplier observations over the WRAM request harness.

Original CPU and mapper behavior remain unchanged. The inherited after-instruction
request injection is fixture stimulus, not physical interrupt timing. Both full
ExRAM snapshots are copied at recorded endpoints, not read after the window ends.
"""
from pathlib import Path
import argparse
import instrument_wram_timeline as wram
from instrument_timeline_probe import PRE, POST, MARKER as CPU_MARKER

MARKER='NES2SNES_CPU_IO_TIMELINE_V1'
GETTER='''\n/* NES2SNES_CPU_IO_TIMELINE_V1: no state writes or emulated bus reads. */
int n2s_m5_cpu_io(uint8_t *metadata, uint8_t *memory) {
    if (!ExRAM || !metadata) return 0;
    metadata[0]=(uint8_t)(MMC5HackCHRMode&3);
    metadata[1]=mul[0]; metadata[2]=mul[1];
    if (memory) memcpy(memory,ExRAM,1024);
    return 1;
}
'''
HELPER='''
extern int n2s_m5_cpu_io(uint8_t *,uint8_t *);
static uint8_t tl_exram_initial[1024],tl_exram_final[1024];
TL_EXPORT unsigned retro_n2s_exram_size(void){return 1024;}
TL_EXPORT const uint8_t *retro_n2s_exram_data(unsigned final){
    return final ? tl_exram_final : tl_exram_initial;
}
'''
CAPTURE='''
    /* NES2SNES_CPU_IO_TIMELINE_V1 */
    {
        uint8_t metadata[3];
        if(!n2s_m5_cpu_io(metadata, !tl_count ? tl_exram_initial :
                        tl_count+1==tl_limit ? tl_exram_final : NULL)) {
            tl_error=9;tl_active=0;return;
        }
        r->reserved[8]=metadata[0];r->reserved[9]=metadata[1];r->reserved[10]=metadata[2];
    }
'''


def headers() -> tuple[str,str]:
    before=('#define TL_RAM_BYTES 2048\n'+wram.HEADER.read_text()).replace(
        'static void tl_before(',wram.HELPER+'\nstatic void tl_before(',1)
    anchor='    memcpy(r->ram,ram,TL_RAM_BYTES);'
    before=before.replace(anchor,wram.CAPTURE+anchor)
    after=before.replace('static void tl_before(',HELPER+'\nstatic void tl_before(',1).replace(anchor,CAPTURE+anchor)
    return before,after


def instrument(source: Path) -> bool:
    board=source/'src/boards/mmc5.c';header=source/'src/n2s_timeline_probe.h';cpu=source/'src/x6502.c'
    original,expected=headers();text=board.read_text()
    if MARKER in text or (header.is_file() and MARKER in header.read_text()):
        if (not text.endswith(wram.GETTER+GETTER) or text.count(MARKER)!=1 or
                not header.is_file() or header.read_text()!=expected or
                any(cpu.read_text().count(v)!=1 for v in (PRE,POST,CPU_MARKER))):
            raise ValueError('Partial or altered CPU-I/O observation')
        return False
    if any(text.count(v)!=1 for v in ('static uint8_t mul[2];','static uint8_t *ExRAM = NULL;')):
        raise ValueError('Unexpected pinned ExRAM/multiplier declarations')
    wram.instrument(source)
    if header.read_text()!=original:raise ValueError('Unexpected WRAM observation header')
    board.write_text(board.read_text()+GETTER);header.write_text(expected);cpu.touch()
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
