#!/usr/bin/env python3
"""Install bounded read-only instruction timestamps in pinned Nestopia.

Retain a separately built unmodified core for same-platform noninterference.
Only the exact instruction-dispatch anchors are supported; partial installs fail.
"""
from pathlib import Path
import argparse

HEADER = Path(__file__).with_name('nestopia_dma_trace.h')
ANCHOR = '\t\t\t(*this.*opcodes[opcode=FetchPc8()])();'
BEFORE = '\t\t\tn2s_dma_begin((uint16_t)pc,GetMonotonicCycles(),GetClock());'
AFTER = '\t\t\tn2s_dma_end((uint16_t)pc,(uint8_t)opcode,GetMonotonicCycles());'
INCLUDE = '#include "n2s_dma_trace.h"'


def instrument(source: Path) -> bool:
    path=source/'source/core/NstCpu.cpp'
    text=path.read_text();target=path.parent/'n2s_dma_trace.h'
    if INCLUDE in text:
        if any(text.count(s)!=1 for s in (INCLUDE,BEFORE,AFTER,ANCHOR)) or not target.is_file() or target.read_bytes()!=HEADER.read_bytes():
            raise ValueError('Partial or changed DMA observer; restore pinned source')
        return False
    if text.count(ANCHOR)!=1 or 'n2s_dma_' in text:
        raise ValueError('Unsupported instruction-dispatch source')
    target.write_bytes(HEADER.read_bytes())
    path.write_text(INCLUDE+'\n'+text.replace(ANCHOR,BEFORE+'\n'+ANCHOR+'\n'+AFTER))
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    print('installed' if instrument(p.parse_args().source) else 'already installed')
