#!/usr/bin/env python3
"""Install fixture-only elapsed-cycle request stimulus in pinned FCEUmm.

No original execution or interrupt dispatch is replaced. NOT gameplay validation
instrumentation: requests are asserted after instructions, not sampled at pins.
"""
from pathlib import Path
import argparse

HEADER=Path(__file__).with_name('timeline_probe.h')
BEGIN='\t\tb1 = RdMem(_PC);'
END='\t\tswitch (b1) {\n\t\t\t#include "ops.h"\n\t\t}'
MARKER='NES2SNES_TIMELINE_STIMULUS_V1'
PRE='tl_before((uint16_t)_PC,_A,_X,_Y,_P,_S,timestampbase+(uint64_t)timestamp,_IRQlow,RAM);'
POST='tl_after(b1,timestampbase+(uint64_t)timestamp);'

def instrument(source: Path, *, ram_bytes: int=512) -> bool:
    if type(ram_bytes) is not int or ram_bytes not in (512,2048):
        raise ValueError('Unsupported timeline capture size')
    header=(b'#define TL_RAM_BYTES 2048\n' if ram_bytes==2048 else b'')+HEADER.read_bytes()
    path=source/'src/x6502.c';text=path.read_text();dest=path.parent/'n2s_timeline_probe.h'
    include='#include "n2s_timeline_probe.h"'
    if MARKER in text:
        if any(text.count(v)!=1 for v in (MARKER,PRE,POST,include)) or not dest.is_file() or dest.read_bytes()!=header:
            raise ValueError('Partial or altered timeline stimulus harness')
        return False
    if include in text or any(text.count(v)!=1 for v in (BEGIN,END,'#include "sound.h"')):
        raise ValueError('Unexpected pinned dispatch anchors')
    text=text.replace('#include "sound.h"','#include "sound.h"\n#include "cart.h"\n'+include)
    text=text.replace(BEGIN,'        /* '+MARKER+' */\n        '+PRE+'\n'+BEGIN)
    text=text.replace(END,END+'\n        '+POST)
    dest.write_bytes(header);path.write_text(text);return True

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--ram-bytes',type=int,choices=(512,2048),default=512)
    args=p.parse_args()
    print('installed' if instrument(args.source,ram_bytes=args.ram_bytes) else 'already installed')
