#!/usr/bin/env python3
"""Original indexed-address, ALU-flag and I/O-fallback regression input.

No game bytes are used. Run the generated program independently on NES and
SNES; mode/index arithmetic crosses RAM mirrors, 16-bit wrap and ROM banks.
"""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
from native_fixture import Program, write_program

READS = ('LDA', 'AND', 'ORA', 'EOR', 'ADC', 'SBC', 'CMP')
RAM_TARGETS = (0x0000, 0x0021, 0x07FF, 0x0802, 0x0FFF, 0x1002, 0x17FF, 0x1FFF)
ROM_TARGETS = (0x8000, 0x8100, 0xBFFF, 0xC000, 0xE000, 0xFF00, 0xFFFF)


def create(out: Path, seed: int = 0, c0: bool = False) -> dict:
    rng = random.Random(seed)
    p = Program()
    for name in ('SEI', 'CLD'): p.op(name)
    p.op('LDX', 'imm', 255); p.op('TXS')
    p.op('LDA', 'imm', 0); p.op('STA', 'zp', 0x7E)
    p.op('LDX', 'imm', 0); p.label('fill_oam')
    p.op('TXA'); p.op('EOR', 'imm', seed & 255); p.op('STA', 'absx', 0x0200)
    p.op('INX'); p.op('BNE', 'rel', 'fill_oam')
    for address, value in ((0x5100, 2), (0x5115, 0x9E if c0 else 0x80),
                           (0x5116, 0x87 if c0 else 0x9E), (0x5105, 0x44), (0x4017, 0x40), (0x4015, 0)):
        p.op('LDA', 'imm', value); p.op('STA', 'abs', address)
    for i in range(80):
        operation = (READS + ('STA',))[i % 8]
        mode = ('absx', 'absy')[(i // 8) % 2]
        index = (0, 1, 127, 255)[(i // 16 + seed) % 4]
        choices = RAM_TARGETS if operation == 'STA' or i % 3 else ROM_TARGETS
        target = choices[rng.randrange(len(choices))]
        if target < 0x2000:
            p.op('LDA', 'imm', (0, 1, 0x7F, 0x80, 0xFF)[(i + seed) % 5])
            p.op('STA', 'abs', target & 0x7FF)
        p.op('LDA', 'imm', 0x7F); p.op('CLC'); p.op('ADC', 'imm', (i + seed) & 1)
        p.op('LDA', 'imm', rng.randrange(256))
        p.op('LDX', 'imm', index if mode == 'absx' else rng.randrange(256))
        p.op('LDY', 'imm', index if mode == 'absy' else rng.randrange(256))
        p.op('SEC' if (i + seed) & 2 else 'CLC')
        base = (target - index) & 0xFFFF
        p.op(operation, mode, base)
        p.record(f'{i}_{operation}_{mode}_base{base:04x}_index{index}')
        if operation == 'STA':
            p.op('LDA', 'abs', target & 0x7FF)
            p.record(f'{i}_stored_value')
    # Explicit wrap across $FFFF and raw ROM reads in all mapping combinations.
    for cb in (30, 7):
        for bank in (0, 1, 15):
            for address, value in ((0x5115, 0x80 + 2*bank), (0x5116, 0x80 + cb)):
                p.op('LDA', 'imm', value); p.op('LDY', 'imm', 1)
                p.op('STA', 'absy', address - 1)
            p.op('LDA', 'imm', 0x6D); p.op('STA', 'zp', 0)
            p.op('LDX', 'imm', 1); p.op('LDA', 'absx', 0xFFFF)
            p.record(f'wrap_{bank}_{cb}')
            p.op('LDY', 'imm', 255); p.op('LDA', 'absy', 0x7F01)
            p.record(f'raw_rom_{bank}_{cb}')
            p.op('LDA', 'imm', 0xFE); p.op('STA', 'absy', 0x7F01)
            p.op('LDA', 'absy', 0x7F01); p.record(f'rom_store_fallback_{bank}_{cb}')
    if c0:
        for address,value in ((0x5115,0x9E),(0x5116,0x87)):
            p.op('LDA','imm',value);p.op('STA','abs',address)
    # Allow real NES power-on PPU write suppression to expire.
    for label in ('warmup1', 'warmup2'):
        p.label(label); p.op('LDA', 'abs', 0x2002); p.op('BPL', 'rel', label)
    # Hardware writes through indexed aliases, including buffered PPU data.
    def store(address: int, value: int, mode: str = 'absx') -> None:
        p.op('LDA', 'imm', value)
        p.op('LDX' if mode == 'absx' else 'LDY', 'imm', 7)
        p.op('STA', mode, address - 7)
    store(0x2001, 0); store(0x2000, 0)
    p.op('LDA', 'abs', 0x2002)
    store(0x2006, 0x20); store(0x2006, 0x00)
    store(0x2007, 0x91); store(0x200F, 0x42, 'absy')
    store(0x2006, 0x20); store(0x2006, 0x00)
    p.op('LDX', 'imm', 7); p.op('LDA', 'absx', 0x2000)  # buffered dummy read
    for i in range(2):
        p.op('LDA', 'absx', 0x2000); p.record(f'ppu_buffered_fallback_{i}')
    # APU register writes reload state, including repeated identical values.
    store(0x4017, 0x40); store(0x4015, 0x0F)
    for reg in (0, 4, 12): store(0x4000 + reg, 0x3F)
    store(0x4008, 0xFF)
    for reg in (3, 7, 11, 15):
        for repeat in range(2):
            store(0x4000 + reg, 0xF8, 'absy')
            p.op('LDA', 'abs', 0x4015); p.op('AND', 'imm', 15)
            p.record(f'apu_reload_{reg}_{repeat}')
    store(0x4015, 0); p.op('LDA', 'abs', 0x4015); p.op('AND', 'imm', 15)
    p.record('apu_disable')
    # Controller/OAM stay on their own fallback; do not lose bus side effects.
    store(0x4016, 1); store(0x4016, 0, 'absy')
    for i in range(10):
        p.op('LDA', 'absx', 0x400F); p.record(f'joy_fallback_{i}')
    store(0x4014, 2)
    p.op('LDA', 'imm', 0x5A); p.op('STA', 'zp', 0x7E)
    p.label('done'); p.op('JMP', 'abs', 'done'); p.label('nmi'); p.op('RTI')
    meta = write_program(out, p)
    meta.update(indexed_memory_fixture=True, seed=seed, c0_start=c0,
                expected_oam_source_page=2)
    (out/'trace-summary.json').write_text(json.dumps(meta, indent=2)+'\n')
    return meta

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--c0',action='store_true')
    a=p.parse_args();m=create(a.out,a.seed,a.c0)
    print(f"Created {len(m['records'])} records in {m['program_bytes']} bytes")
