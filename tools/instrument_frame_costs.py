#!/usr/bin/env python3
"""Instrument pinned Snes9x with elapsed master-clock attribution.

Diagnostic only, not an independent correctness oracle. Clocks include stalls
serviced inside each instruction (DMA/HDMA/refresh), not just opcode costs.
Only uninterrupted sessions are supported: do not load states while measuring.
"""
from __future__ import annotations
import argparse
from pathlib import Path

MARKER = '// NES2SNES_FRAME_COSTS_V2'
DECL = r'''
// NES2SNES_FRAME_COSTS_V2
#include <stdint.h>
#include <string.h>
static uint64_t n2s_clock_base;
static uint64_t n2s_costs[3][65536]; // host, guest, WRAM veneers
static uint64_t n2s_instructions[3][65536];
static uint64_t n2s_measure_start;
// Completed COP spans, keyed by the original execution bank AND PC. These
// overlap the flat PC costs above and must never be added to that accounting.
static uint64_t n2s_cop_costs[32][65536];
static uint64_t n2s_cop_calls[32][65536];
static bool n2s_in_cop;
static unsigned n2s_cop_bank;
static uint16_t n2s_cop_pc;
static uint64_t n2s_cop_pending, n2s_cop_overlaps;
static void n2s_cop_step(unsigned bank, uint16_t pc, unsigned op,
                         unsigned next_bank, uint64_t clocks) {
    if (bank >= 0xA1 && bank <= 0xC0 && pc >= 0x8000 && op == 0x02) {
        if (n2s_in_cop) ++n2s_cop_overlaps;
        n2s_in_cop = true;
        n2s_cop_bank = bank - 0xA1;
        n2s_cop_pc = pc;
        n2s_cop_pending = 0;
    }
    if (!n2s_in_cop) return;
    n2s_cop_pending += clocks;
    // A nested short NMI returning to host code does not end the COP span.
    // Mapper writes may change the returning guest bank, so do not require
    // it to equal the entry bank. No application stack or RAM is inspected.
    if ((bank == 0 || bank == 0x80) && op == 0x40 &&
        next_bank >= 0xA1 && next_bank <= 0xC0) {
        n2s_cop_costs[n2s_cop_bank][n2s_cop_pc] += n2s_cop_pending;
        ++n2s_cop_calls[n2s_cop_bank][n2s_cop_pc];
        n2s_cop_pending = 0;
        n2s_in_cop = false;
    }
}
extern "C" const uint64_t *retro_n2s_cop_costs(unsigned bank) {
    return bank < 32 ? n2s_cop_costs[bank] : 0;
}
extern "C" const uint64_t *retro_n2s_cop_calls(unsigned bank) {
    return bank < 32 ? n2s_cop_calls[bank] : 0;
}
extern "C" uint64_t retro_n2s_cop_status(unsigned field) {
    if (field == 0) return n2s_cop_overlaps;
    if (field == 1) return n2s_in_cop ? 1 : 0;
    if (field == 2) return n2s_cop_pending;
    return 0;
}
static uint64_t n2s_clock_now() { return n2s_clock_base + (int64_t) CPU.Cycles; }
extern "C" void retro_n2s_cost_reset(void) {
    memset(n2s_costs, 0, sizeof(n2s_costs));
    memset(n2s_instructions, 0, sizeof(n2s_instructions));
    memset(n2s_cop_costs, 0, sizeof(n2s_cop_costs));
    memset(n2s_cop_calls, 0, sizeof(n2s_cop_calls));
    n2s_in_cop = false; // exclude an unknown partial span at the start boundary
    n2s_cop_pending = n2s_cop_overlaps = 0;
    n2s_measure_start = n2s_clock_now();
}
extern "C" uint64_t retro_n2s_cost_elapsed(void) {
    return n2s_clock_now() - n2s_measure_start;
}
extern "C" const uint64_t *retro_n2s_cost_data(unsigned kind) {
    return kind < 3 ? n2s_costs[kind] : 0;
}
extern "C" const uint64_t *retro_n2s_cost_instructions(unsigned kind) {
    return kind < 3 ? n2s_instructions[kind] : 0;
}
'''
BEFORE = r'''
        const uint64_t n2s_start = n2s_clock_now();
        const uint16_t n2s_pc = Registers.PCw;
        const unsigned n2s_bank = Registers.PB;
        const unsigned n2s_kind = (Registers.PB == 0 || Registers.PB == 0x80) ? 0 :
            (Registers.PCw < 0x8000 ? 2 : 1);
'''
AFTER = r'''
        const uint64_t n2s_spent = n2s_clock_now() - n2s_start;
        n2s_costs[n2s_kind][n2s_pc] += n2s_spent;
        n2s_cop_step(n2s_bank, n2s_pc, Op, Registers.PB, n2s_spent);
        ++n2s_instructions[n2s_kind][n2s_pc];
'''

def instrument(source: Path) -> bool:
    path = source / 'cpuexec.cpp'
    text = path.read_text()
    if MARKER in text:
        return False
    if 'NES2SNES_FRAME_COSTS_V1' in text:
        raise ValueError('Restore the clean pinned source before installing V2')
    anchors = ('void S9xMainLoop (void)', '\t\tuint8\t\t\t\tOp;',
               '\t\t(*Opcodes[Op].S9xOpcode)();', '\t\t\tCPU.Cycles -= Timings.H_Max;')
    if any(text.count(s) != 1 for s in anchors):
        raise ValueError('Dispatcher does not match the pinned Snes9x anchors')
    if 'NES2SNES_PROFILE:' in text:
        raise ValueError('Use a clean source tree, not another profiling patch')
    text = text.replace(anchors[0], DECL + '\n' + anchors[0])
    text = text.replace(anchors[1], BEFORE + '\n' + anchors[1])
    text = text.replace(anchors[2], anchors[2] + '\n' + AFTER)
    text = text.replace(anchors[3], '\t\t\tn2s_clock_base += Timings.H_Max;\n' + anchors[3])
    path.write_text(text)
    return True

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    print('patched' if instrument(p.parse_args().source) else 'already patched')
