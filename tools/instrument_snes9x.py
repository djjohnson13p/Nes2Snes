#!/usr/bin/env python3
"""Add an optional instruction-count probe to the pinned Snes9x source tree.

The probe observes opcode dispatch, does not modify emulated CPU timing, and is
not used as the independent correctness oracle. Rebuild the core after patching.
"""
from pathlib import Path
import argparse

DECL = r'''
// NES2SNES_PROFILE: optional host-PC histogram; no emulated timing changes.
#include <stdint.h>
#include <string.h>
static uint64_t n2s_host_counts[65536];
static uint64_t n2s_guest_counts[256];
static uint64_t n2s_trap_counts[256];
extern "C" void retro_n2s_profile_reset(void)
{
    memset(n2s_host_counts, 0, sizeof(n2s_host_counts));
    memset(n2s_guest_counts, 0, sizeof(n2s_guest_counts));
    memset(n2s_trap_counts, 0, sizeof(n2s_trap_counts));
}
extern "C" const uint64_t *retro_n2s_profile_host(void) { return n2s_host_counts; }
extern "C" const uint64_t *retro_n2s_profile_guest(void) { return n2s_guest_counts; }
extern "C" const uint64_t *retro_n2s_profile_traps(void) { return n2s_trap_counts; }
'''
HOOK = r'''
        if (Registers.PB == 0x00 || Registers.PB == 0x80)
            ++n2s_host_counts[Registers.PCw];
        else
            ++n2s_guest_counts[Registers.PB];
        if (Registers.PB >= 0xa1 && Registers.PB <= 0xc0 && Op == 0x02 && CPU.PCBase)
            ++n2s_trap_counts[CPU.PCBase[(uint16)(Registers.PCw + 1)]];
'''

def instrument(source: Path) -> bool:
    path=source/'cpuexec.cpp'
    text=path.read_text()
    if '// NES2SNES_PROFILE:' in text:
        return False
    start='void S9xMainLoop (void)'
    hook='\t\tRegisters.PCw++;\n\t\t(*Opcodes[Op].S9xOpcode)();'
    if text.count(start)!=1 or text.count(hook)!=1:
        raise ValueError('Snes9x source does not match the pinned dispatch anchors')
    text=text.replace(start,DECL+'\n'+start).replace(hook,HOOK+'\n'+hook)
    path.write_text(text)
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    print('patched' if instrument(p.parse_args().source) else 'already patched')
