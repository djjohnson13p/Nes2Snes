#!/usr/bin/env python3
"""Install optional runtime probe into an existing FCEUmm source checkout.

Tested upstream revision is recorded in docs/toolchain.md. Refuses unknown hook
locations and does not download anything. The resulting core is GPL-2.0-or-later.
"""
from pathlib import Path
import argparse


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    args=p.parse_args()
    f=args.source/'src/x6502.c'
    text=f.read_text()
    if '#include "n2s_probe.inc"' in text:
        print('Probe already installed.');return
    changes=[('#include "sound.h"', '#include "sound.h"\n#include "n2s_probe.inc"'),
             ('\t\tb1 = RdMem(_PC);','\t\tn2s_instruction((uint16_t)_PC);\n\t\tb1 = RdMem(_PC);'),
             ('return(_DB = ARead[A](A));', 'n2s_io(A, 0, 0);\n\treturn(_DB = ARead[A](A));'),
             ('static INLINE void WrMemNorm(uint32_t A, uint8_t V) {',
              'static INLINE void WrMemNorm(uint32_t A, uint8_t V) {\n\tn2s_io(A, 1, V);')]
    for old,new in changes:
        if text.count(old) != 1:raise SystemExit(f'Unexpected upstream source at hook: {old!r}')
        text=text.replace(old,new)
    f.write_text(text)
    (f.parent/'n2s_probe.inc').write_bytes(Path(__file__).with_name('fceumm_probe.inc').read_bytes())
    print('Probe installed; rebuild using make -f Makefile.libretro.')

if __name__=='__main__':main()
