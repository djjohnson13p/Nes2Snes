#!/usr/bin/env python3
"""Original pulse-sweep sequence for quantized state and real DSP checks."""
import argparse, json
from pathlib import Path
from native_fixture import Program, write_program

def pair(period, control, enable=3):
    return [(0x4015,enable),(0x4000,0xbf),(0x4004,0xbf),
            (0x4001,control),(0x4005,control),
            (0x4002,period&255),(0x4006,period&255),
            (0x4003,8|(period>>8)),(0x4007,8|(period>>8))]
EVENTS={
    1:pair(700,0xa2),                 # slow positive sweeps toward overflow
    15:pair(1000,0x99),               # channel-specific negate difference
    30:pair(0x600,1),                 # mute even though sweep enable is off
    40:pair(0x400,0x80),              # zero shift: mute but never update
    50:pair(0x200,0x88),              # zero shift negate: stable audible tone
    60:pair(7,0x89),                  # too-small current period
    70:pair(1000,0xa9),
    71:[(0x4001,0xa9),(0x4005,0xa9)], # repeated control write reloads divider
    73:[(0x4002,0x45),(0x4006,0x45)], # preserve swept high byte
    75:[(0x4003,0x0a),(0x4007,0x0a)], # preserve swept low byte
    80:[(0x4017,0xc0)],               # immediate Q/H and five-step clock
    90:pair(1000,0x9b,enable=0),      # sweep clocks with length disabled
    100:[(0x4015,3)],                 # no resurrection of disabled length
    110:pair(800,0xb2),
    120:[(0x4001,8),(0x4005,8)],      # stop sweeping while preserving period
    130:[(0x4015,0)],
}
SEGMENTS=[('overflow',33,37,'silent'),('zero_shift_overflow',43,47,'silent'),
          ('negate_zero_tone',53,57,'audible'),('period_seven',63,67,'silent'),
          ('disabled',94,98,'silent'),('no_resurrection',104,108,'silent'),
          ('final_silence',133,138,'silent')]

def create(out:Path)->dict:
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    def write(a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
    initial=[(0x4015,0),(0x4017,0x40)]
    for a,v in [(0x2000,0),(0x2001,0),*initial,(0x5100,2),(0x5115,0x80),(0x5116,0x9e)]:write(a,v)
    p.op('LDA','imm',0);p.op('STA','zp',0x40);write(0x2000,0x80)
    p.label('loop');p.op('JMP','abs','loop');p.label('nmi');p.op('PHA');p.op('INC','zp',0x40)
    for frame,events in EVENTS.items():
        p.op('LDA','zp',0x40);p.op('CMP','imm',frame);p.op('BNE','rel',f'next{frame}')
        for a,v in events:write(a,v)
        p.label(f'next{frame}')
    p.op('PLA');p.op('RTI');result=write_program(out,p)
    result.update(events=EVENTS,initial_audio_writes=initial,last_frame=140,segments=SEGMENTS)
    (out/'sweep-fixture.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    print(json.dumps(create(p.parse_args().out),indent=2))
