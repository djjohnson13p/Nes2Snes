#!/usr/bin/env python3
"""Install independent before/after timestamp observation in pinned FCEUmm.

Use a preserved plain core for noninterference comparison. Hooks read raw mapped
instruction bytes and zero-page RAM only; no clock, bus or game-state mutation.
"""
from pathlib import Path
import argparse

HEADER = Path(__file__).with_name('cycle_observer.h')
BEGIN = '\t\tb1 = RdMem(_PC);'
END = '\t\tswitch (b1) {\n\t\t\t#include "ops.h"\n\t\t}'
MARKER = 'NES2SNES_CYCLE_OBSERVER_V1'


def instrument(source: Path) -> bool:
    path=source/'src/x6502.c';text=path.read_text();dest=path.parent/'n2s_cycle_observer.h'
    if MARKER in text:
        if (text.count(MARKER)!=1 or text.count('#include "n2s_cycle_observer.h"')!=1
                or text.count('n2s_cycle_begin((uint16_t)_PC,b1,_P,_X,_Y,_A,_S,timestampbase+(uint64_t)timestamp,RAM);')!=1
                or text.count('n2s_cycle_end((uint16_t)_PC,timestampbase+(uint64_t)timestamp);')!=1
                or not dest.is_file() or dest.read_bytes()!=HEADER.read_bytes()):
            raise ValueError('Partial or different cycle observer; restore a clean source')
        return False
    if 'n2s_cycle_observer.h' in text or any(text.count(anchor)!=1 for anchor in (BEGIN,END,'#include "sound.h"')):
        raise ValueError('Source does not match pinned instruction-dispatch anchors')
    text=text.replace('#include "sound.h"','#include "sound.h"\n#include "n2s_cycle_observer.h"')
    text=text.replace(BEGIN,BEGIN+'\n        /* '+MARKER+' */\n        n2s_cycle_begin((uint16_t)_PC,b1,_P,_X,_Y,_A,_S,timestampbase+(uint64_t)timestamp,RAM);')
    text=text.replace(END,END+'\n        n2s_cycle_end((uint16_t)_PC,timestampbase+(uint64_t)timestamp);')
    dest.write_bytes(HEADER.read_bytes());path.write_text(text);return True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
