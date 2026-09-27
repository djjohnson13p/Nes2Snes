#!/usr/bin/env python3
"""Install a bounded external-request test hook, not gameplay instrumentation.

Targets the pinned FCEUmm dispatch. Original interrupt handling is not patched.
Only authored fixtures should configure this harness. No pin-cycle accuracy claim.
"""
from pathlib import Path
import argparse

HEADER = Path(__file__).with_name('interrupt_probe.h')
BEGIN = '\t\tb1 = RdMem(_PC);'
END = '\t\tswitch (b1) {\n\t\t\t#include "ops.h"\n\t\t}'
PRE = 'n2s_ib_before((uint16_t)_PC,_P,_S,_A,_X,_Y,timestampbase+(uint64_t)timestamp,RAM);'
POST = 'n2s_ib_after(b1,(uint16_t)_PC,_P,_S,_A,_X,_Y,timestampbase+(uint64_t)timestamp,RAM);'
MARKER = 'NES2SNES_INTERRUPT_BOUNDARY_TEST_V1'


def instrument(source: Path) -> bool:
    path=source/'src/x6502.c'; text=path.read_text(); dest=path.parent/'n2s_interrupt_probe.h'
    if MARKER in text:
        if any(text.count(value)!=1 for value in (MARKER, PRE, POST, '#include "n2s_interrupt_probe.h"')) or not dest.is_file() or dest.read_bytes()!=HEADER.read_bytes():
            raise ValueError('Partial or altered interrupt test harness')
        return False
    if 'n2s_interrupt_probe.h' in text or any(text.count(v)!=1 for v in (BEGIN,END,'#include "sound.h"')):
        raise ValueError('Unexpected pinned dispatch anchors')
    text=text.replace('#include "sound.h"','#include "sound.h"\n#include "n2s_interrupt_probe.h"')
    text=text.replace(BEGIN,'        /* '+MARKER+' */\n        '+PRE+'\n'+BEGIN)
    text=text.replace(END,END+'\n        '+POST)
    dest.write_bytes(HEADER.read_bytes());path.write_text(text);return True


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path)
    print('installed' if instrument(parser.parse_args().source) else 'already installed')
