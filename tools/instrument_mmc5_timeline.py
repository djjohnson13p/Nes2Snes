#!/usr/bin/env python3
"""Add read-only physical-ROM mapping bytes to the fixture timeline capture.

This changes observation only, not MMC5 dispatch or mapping. The underlying
request harness remains AFTER-instruction stimulus, not physical IRQ sampling.
"""
from pathlib import Path
import argparse
from instrument_timeline_probe import instrument as base, HEADER, PRE, POST, MARKER as BASE_MARKER

HELPER = r'''
/* Physical mapping is read from the ORIGINAL core's Page pointers, not a model. */
static uint8_t tl_mmc5_bank(uint16_t address) {
    uintptr_t p, start;
    if(address < 0x8000 || !Page[address>>11] || !PRGptr[0]) return 255;
    p=(uintptr_t)Page[address>>11]+address; start=(uintptr_t)PRGptr[0];
    if(p<start || p-start>=PRGsize[0]) return 255;
    return (uint8_t)((p-start)/8192);
}
'''
MARKER='NES2SNES_MMC5_MAP_OBSERVATION_V1'

def instrument(source: Path) -> bool:
    dest=source/'src/n2s_timeline_probe.h'
    expected=b'#define TL_RAM_BYTES 2048\n'+HEADER.read_bytes()
    new=expected.decode().replace('static void tl_before(',HELPER+'\nstatic void tl_before(',1)
    anchor='    memcpy(r->ram,ram,TL_RAM_BYTES);'
    capture='    /* '+MARKER+' */\n    { unsigned slot; for(slot=0;slot<4;slot++) r->reserved[slot]=tl_mmc5_bank((uint16_t)(0x8000+slot*8192)); }\n    r->reserved[4]=tl_mmc5_bank(pc);\n'
    if new.count(anchor)!=1:raise ValueError('Mapping capture anchor changed')
    new=new.replace(anchor,capture+anchor)
    if dest.is_file() and MARKER in dest.read_text():
        text=(source/'src/x6502.c').read_text()
        if dest.read_text()!=new or any(text.count(v)!=1 for v in (PRE,POST,BASE_MARKER,'#include \"n2s_timeline_probe.h\"')):
            raise ValueError('Modified mapping capture or dispatch hooks')
        return False
    base(source,ram_bytes=2048)
    if dest.read_bytes()!=expected:raise ValueError('Unexpected base timeline header')
    dest.write_text(new);(source/'src/x6502.c').touch();return True

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
