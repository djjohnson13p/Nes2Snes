#!/usr/bin/env python3
"""Original APU length/status fixture, checked against the independent NES core.

Every half/quarter clock is explicitly requested with a five-step $4017 reset.
NOPs exceed its real 3/4-cycle write delay. No NMI or guest-frame clock runs, and
successive resets are close enough to prevent automatic sequencer events.
This establishes event semantics, not cycle-accurate periodic audio timing.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from native_fixture import Program,write_program
LENGTHS=(10,254,20,2,40,4,80,6,160,8,60,10,14,12,26,14,
         12,16,24,18,48,20,96,22,192,24,72,26,16,28,32,30)
def create(out:Path,force_c0:bool=False)->dict:
    p=Program()
    def write(address,value,register='A'):
        p.op('LD'+register,'imm',value);p.op('ST'+register,'abs',address)
    def status(name):
        p.op('LDA','abs',0x4015);p.op('AND','imm',15);p.record(name)
    def clock():
        write(0x4017,0xc0)
        for _ in range(8):p.op('NOP')
    def clocks(count,label):
        p.op('LDY','imm',count);p.label(label);clock();p.op('DEY');p.op('BNE','rel',label)
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    write(0x2000,0);write(0x2001,0);write(0x4017,0x40)
    write(0x5100,2);write(0x5115,0x9e if force_c0 else 0x80);write(0x5116,0x87 if force_c0 else 0x9e)
    p.op('LDY','imm',0);p.op('CLC');p.op('CLV')
    for base in (0,4,8,12):write(0x4000+base,0)
    write(0x4015,15)
    for index,length in enumerate(LENGTHS):
        for address in (0x4003,0x4007,0x400b,0x400f):write(address,index<<3)
        status(f'length_{index:02d}_loaded')
        clocks(length-1,f'clocks{index}')
        status(f'length_{index:02d}_last_tick')
        clock();status(f'length_{index:02d}_expired')
    # Disable is destructive; enabling alone does not reload a stopped note.
    for channel in range(4):
        write(0x4015,0);write(0x4003+4*channel,0);write(0x4015,1<<channel)
        status(f'disabled_reload_{channel}')
        write(0x4003+4*channel,0);status(f'enabled_reload_{channel}')
        write(0x4015,0);write(0x4015,1<<channel);status(f'no_resurrection_{channel}')
    # The three store instructions and repeated-value writes must all be seen.
    write(0x4015,15)
    for channel in range(4):
        control=0x80 if channel==2 else 0x20
        write(0x4000+4*channel,control)
        write(0x4003+4*channel,3<<3)
        clocks(5,f'halted{channel}');status(f'halt_{channel}')
        write(0x4000+4*channel,0);clock();status(f'unhalt_last_{channel}')
        clock();status(f'unhalt_expired_{channel}')
    for register in ('A','X','Y'):
        write(0x4015,0);write(0x4015,1)
        for attempt in range(2):
            write(0x4003,0x18,register);status(f'{register}_reload_{attempt}')
            clocks(2,f'{register}_clock{attempt}');status(f'{register}_expiry_{attempt}')
    # Stores must preserve all ordinary 6502 flags and A/X/Y, even when
    # the callback performs loops, clocks, or reloads.
    for register in ('A','X','Y'):
        for address in (0x4000,0x4003,0x400b,0x4015,0x4017):
            for carry in (False,True):
                p.op('LDA','imm',0xc0);p.op('STA','zp',0x60)
                p.op('LDA','imm',0xc0);p.op('LDX','imm',0xc0);p.op('LDY','imm',0xc0)
                p.op('BIT','zp',0x60);p.op('SEC' if carry else 'CLC')
                p.op('ST'+register,'abs',address);p.record(f'flags_{register}_{address:04x}_{int(carry)}')
    p.op('LDA','imm',0x5a);p.op('STA','zp',0x7e)
    p.label('done');p.op('JMP','abs','done');p.label('nmi');p.op('RTI')
    result=write_program(out,p)
    result['apu_counter_fixture']=True
    result['force_c0']=force_c0
    result['scope']='Explicit five-step clocks: all 32 length values, halt, reload and disable; no cycle-timing claim'
    (out/'trace-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--force-c0',action='store_true');a=p.parse_args()
    print(json.dumps(create(a.out,a.force_c0),indent=2))
