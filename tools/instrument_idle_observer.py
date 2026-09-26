#!/usr/bin/env python3
"""Install a read-only tick/sample observer into the pinned emulator dispatchers.

Only common 2-KiB RAM is read directly. No bus read API or clock mutation is used.
Use a clean source tree with the revisions in docs/toolchain.md. Preserve a plain
core for independent calibration. The observer does not survive a state reload.
"""
from __future__ import annotations
import argparse
from pathlib import Path

MARKER = 'NES2SNES_IDLE_OBSERVER_V1'
HEADER = Path(__file__).with_name('idle_observer.h')


def instrument(source: Path, platform: str) -> bool:
    if platform == 'nes':
        path = source/'src/x6502.c'
        include = '#include "sound.h"'
        anchor = '\t\tb1 = RdMem(_PC);'
        hook = '''
        /* NES2SNES_IDLE_OBSERVER_V1: direct RAM read, no emulated bus access. */
        if ((uint16_t)_PC >= 0x8000)
            n2s_idle_step((uint16_t)_PC, 0, RAM);
'''
    elif platform == 'snes':
        path = source/'cpuexec.cpp'
        include = '#include "memmap.h"'
        anchor = '\t\tuint8\t\t\t\tOp;'
        hook = '''
        // NES2SNES_IDLE_OBSERVER_V1: guest-bank cartridge instructions only.
        if (Registers.PB >= 0xA1 && Registers.PB <= 0xC0 && Registers.PCw >= 0x8000)
            n2s_idle_step(Registers.PCw, Registers.PB, Memory.RAM);
'''
    else:
        raise ValueError('Platform must be nes or snes')
    text = path.read_text()
    if MARKER in text:
        if text.count(MARKER) != 1 or '#include "n2s_idle_observer.h"' not in text:
            raise ValueError('Partial or duplicate observer installation')
        if (path.parent/'n2s_idle_observer.h').read_bytes() != HEADER.read_bytes():
            raise ValueError('Observer header changed; restore the clean source before reinstalling')
        return False
    if text.count(anchor) != 1 or text.count(include) != 1 or 'n2s_idle_observer.h' in text:
        raise ValueError('Source does not match the pinned instruction-dispatch anchors')
    if 'NES2SNES_FRAME_COSTS' in text or 'NES2SNES_PROFILE:' in text:
        raise ValueError('Use a source tree without other SNES profiling patches')
    text = text.replace(include, include+'\n#include "n2s_idle_observer.h"')
    text = text.replace(anchor, hook+'\n'+anchor)
    (path.parent/'n2s_idle_observer.h').write_bytes(HEADER.read_bytes())
    path.write_text(text)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--platform', choices=('nes', 'snes'), required=True)
    args = parser.parse_args()
    print('installed' if instrument(args.source, args.platform) else 'already installed')
