#!/usr/bin/env python3
"""Original procedural APU-register sequence for the experimental SPC preview."""
import argparse,json
from pathlib import Path
from native_fixture import Program,write_program

def create(out:Path)->dict:
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('STA','zp',0x40)
    for a in (0x2000,0x2001,0x4015):p.op('STA','abs',a)
    p.op('LDA','imm',2);p.op('STA','abs',0x5100)
    p.op('LDA','imm',0x80);p.op('STA','abs',0x5115)
    p.op('LDA','imm',0x9e);p.op('STA','abs',0x5116)
    # Program frequencies chosen to have unambiguous spectral fundamentals.
    for addr,value in [(0x4000,0xBF),(0x4001,0),(0x4002,253),(0x4003,0),
                       (0x4004,0x7F),(0x4005,0),(0x4006,126),(0x4007,0),
                       (0x4008,0xFF),(0x400A,253),(0x400B,0),
                       (0x400C,0x3F),(0x400E,4),(0x400F,0)]:
        p.op('LDA','imm',value);p.op('STA','abs',addr)
    p.op('LDA','imm',0x80);p.op('STA','abs',0x2000)
    p.label('loop');p.op('JMP','abs','loop')
    p.label('nmi');p.op('PHA');p.op('INC','zp',0x40)
    for n,(at,value) in enumerate([(30,1),(70,0),(80,2),(120,0),(130,4),(170,0),(180,8),(220,0)]):
        p.op('LDA','zp',0x40);p.op('CMP','imm',at);p.op('BNE','rel',f'next{n}')
        p.op('LDA','imm',value);p.op('STA','abs',0x4015);p.label(f'next{n}')
    p.op('PLA');p.op('RTI')
    result=write_program(out,p)
    result.update(audio_segments=[dict(name=n,first=a,last=b,timer=t,triangle=tri) for n,a,b,t,tri in
                   [('pulse1',36,64,253,False),('pulse2',86,114,126,False),
                    ('triangle',136,164,253,True),('noise',186,214,None,False),('silence',225,235,None,False)]])
    (out/'audio-fixture.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True)
    print(json.dumps(create(a.parse_args().out),indent=2))
