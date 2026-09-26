#!/usr/bin/env python3
"""Original note/envelope sequence. No commercial game data or music."""
import argparse,json
from pathlib import Path
from native_fixture import Program,write_program
# Each action occurs in the specified guest NMI, before that update's clocks.
EVENTS={
 1:[(0x4017,0x40),(0x4000,0x81),(0x4002,253),(0x4015,1),(0x4003,8)],
 16:[(0x4003,8)],                      # SAME value, actual envelope restart
 28:[(0x4015,0)],
 32:[(0x4000,0x9f),(0x4015,1),(0x4003,0)], # ten half-clocks then silent
 43:[(0x4015,0),(0x4015,1)],           # enable does not resurrect length
 46:[(0x4015,4),(0x4008,0x83),(0x400a,253),(0x400b,8)],
 53:[(0x4008,3)],                     # release triangle linear reload
 60:[(0x4015,8),(0x400c,0),(0x400e,4),(0x400f,8)],
 68:[(0x400c,0x20),(0x400f,8)],        # looping envelope
 76:[(0x4017,0xc0)],                  # five-step mode plus immediate clock
 85:[(0x4015,0)],
 90:[(0x4015,2),(0x4004,0x7f),(0x4006,126),(0x4007,8)],
 100:[(0x4015,0)]
}
SEGMENTS=[('decay_loud',2,3,'audible'),('decay_soft',5,6,'audible'),('expired',10,12,'silent'),
          ('restarted',17,18,'audible'),('disabled',29,30,'silent'),
          ('length_active',33,34,'audible'),('length_expired',39,41,'silent'),
          ('no_resurrection',44,45,'silent'),('triangle_active',48,50,'audible'),
          ('linear_expired',56,58,'silent'),('noise_expired',65,66,'silent'),
          ('final_silence',103,106,'silent')]
def create(out:Path)->dict:
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    def write(address,value):p.op('LDA','imm',value);p.op('STA','abs',address)
    write(0x2000,0);write(0x2001,0);write(0x4015,0);write(0x4017,0x40)
    write(0x5100,2);write(0x5115,0x80);write(0x5116,0x9e)
    p.op('LDA','imm',0);p.op('STA','zp',0x40);write(0x2000,0x80)
    p.label('loop');p.op('JMP','abs','loop')
    p.label('nmi');p.op('PHA');p.op('INC','zp',0x40)
    for frame,events in EVENTS.items():
        p.op('LDA','zp',0x40);p.op('CMP','imm',frame);p.op('BNE','rel',f'next{frame}')
        for address,value in events:write(address,value)
        p.label(f'next{frame}')
    p.op('PLA');p.op('RTI')
    result=write_program(out,p)
    result.update(events=EVENTS,initial_audio_writes=[(0x4015,0),(0x4017,0x40)],
                  last_frame=108,segments=SEGMENTS)
    (out/'envelope-fixture.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    print(json.dumps(create(p.parse_args().out),indent=2))
