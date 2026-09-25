#!/usr/bin/env python3
"""Original all-bank store/flag tests, including execution bank $C0 fallback."""
import argparse,json
from pathlib import Path
from native_fixture import Program,write_program

def create(out:Path)->dict:
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('STA','abs',0x2000);p.op('STA','abs',0x2001)
    p.op('LDA','imm',2);p.op('STA','abs',0x5100)
    for cb in (30,7):
        p.op('LDA','imm',cb|0x80);p.op('STA','abs',0x5116)
        for primary in range(16):
            p.op('LDA','imm',0x80+2*primary);p.op('STA','abs',0x5115)
            for operation in ('STA','STX','STY'):
                for address in (0x2001,0x5128):
                    p.op('LDA','imm',0 if operation=='STA' else 0x63)
                    p.op('LDX','imm',0 if operation=='STX' else 0xB2)
                    p.op('LDY','imm',0 if operation=='STY' else 0xD3)
                    # Seed carry and overflow without altering A/X/Y.
                    p.op('SEC');p.op('BIT','abs','flagbyte')
                    p.op(operation,'abs',address)
                    p.record(f'bank{primary}_{cb}_{operation}_{address:04X}')
    p.op('LDA','imm',0x5A);p.op('STA','zp',0x7E)
    p.label('done');p.op('JMP','abs','done');p.label('nmi');p.op('RTI')
    p.label('flagbyte');p.data.append(0xC0)
    meta=write_program(out,p);meta['direct_fixture']=True
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n');return meta
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True)
    print(json.dumps(create(a.parse_args().out),indent=2))
