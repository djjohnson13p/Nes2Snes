#!/usr/bin/env python3
"""Authored inline-table dispatch fixture; code and tables contain no game data."""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path
from native_fixture import Program, write_program


def create(out: Path, selectors: list[int] | None = None, outside_nmi: bool = False,
           c0: bool = False, primary: int = 0, cbank: int = 30, stack_depth: int = 0) -> dict:
    selectors = [0,1,63,126,127,128,254,255] if selectors is None else list(selectors)
    if not selectors or len(selectors)>8 or any(type(v) is not int or not 0<=v<256 for v in selectors):
        raise ValueError('Require 1..8 byte selectors')
    if not 0<=primary<16 or cbank not in (7,30) or not 0<=stack_depth<=96:
        raise ValueError('Unsupported fixture map or stack depth')
    if c0:primary,cbank=15,7
    p=Program()
    for name,mode,value in [('SEI','imp',0),('CLD','imp',0),('LDX','imm',255),('TXS','imp',0),('LDA','imm',0),('LDX','imm',0)]:
        p.op(name,mode,value)
    p.label('clear')
    for a in range(0,0x800,256):p.op('STA','absx',a)
    p.op('INX');p.op('BNE','rel','clear')
    for a,v in ((0x5100,2),(0x5115,0x80+2*primary),(0x5116,0x80|cbank)):
        p.op('LDA','imm',v);p.op('STA','abs',a)
    for label in ('vblank1','vblank2'):
        p.label(label);p.op('BIT','abs',0x2002);p.op('BPL','rel',label)
    if outside_nmi:
        p.op('JSR','abs','checks')
    else:
        p.op('LDA','imm',0x80);p.op('STA','abs',0x2000)
    p.label('idle');p.op('JMP','abs','idle')
    p.label('nmi');p.op('PHA');p.op('INC','zp',0x70);p.op('LDA','zp',0x70)
    p.op('CMP','imm',4);p.op('BNE','rel','nmi_end')
    p.op('LDA','imm',0);p.op('STA','abs',0x2000);p.op('JSR','abs','checks')
    p.label('nmi_end');p.op('PLA');p.op('RTI')
    p.label('checks')
    for _ in range(stack_depth):p.op('PHA')
    extras={}
    case_info=[]
    for i, selector in enumerate(selectors):
        y=(0,1,127,128,255,0,128,255)[i]
        x=(i*37+selector)&255
        p.op('TSX');p.op('STX','zp',0x61)
        p.op('LDA','imm',0x40 if i&1 else 0);p.op('STA','zp',0x60);p.op('BIT','zp',0x60)
        p.op('SEC' if i&2 else 'CLC');p.op('LDX','imm',x);p.op('LDY','imm',y)
        p.op('LDA','imm',selector)
        call=p.pc;p.op('JSR','abs',0xF700)
        target=0xF780+i*4
        p.data.extend(struct.pack('<H',target)*128)  # deliberately unclassified data
        continuation=p.pc
        p.record(f'selector{selector}_registers')
        for a in range(4):
            p.op('LDA','zp',a);p.record(f'selector{selector}_scratch{a}')
        # Native RTI saves a bank byte absent from NES interrupts. Compare
        # the net stack change across the call, not absolute cross-CPU SP.
        p.op('TSX');p.op('TXA');p.op('SEC');p.op('SBC','zp',0x61)
        p.op('LDX','imm',0);p.record(f'selector{selector}_stack_delta')
        entry=Program(target);entry.op('JMP','abs',continuation)
        extras[0x3E000+target-0xE000]=entry
        case_info.append(dict(selector=selector,x=x,y=y,call=call,table_target=target))
    for _ in range(stack_depth):p.op('PLA')
    p.op('LDA','imm',0x5A);p.op('STA','zp',0x7E);p.op('RTS')
    if p.pc>=0xF700:raise ValueError('Fixture overlaps dispatch')
    d=Program(0xF700)
    # Standalone 6502 algorithm. Do not generate it from the recognizer pattern.
    d.op('ASL','acc');d.op('STY','zp',3);d.op('TAY');d.op('INY')
    d.op('PLA');d.op('STA','zp',0);d.op('PLA');d.op('STA','zp',1)
    d.op('LDA','iy',0);d.op('STA','zp',2);d.op('INY');d.op('LDA','iy',0)
    d.op('LDY','zp',3);d.op('STA','zp',3);d.op('JMP','ind',2)
    extras[0x3F700]=d
    for physical, extra in sorted(extras.items()):
        offset=physical-0x3E000
        data=extra.finish()
        if offset<len(p.data):raise ValueError("Extra code overlaps fixture")
        p.data.extend(bytes(offset-len(p.data)))
        p.data.extend(data)
        p.starts.extend(extra.starts)
    meta=write_program(out,p)
    meta.update(dispatch_fixture=True,cases=case_info,expected_native_calls=0 if outside_nmi or (primary==15 and cbank==7) else len(selectors),
                outside_nmi=outside_nmi,c0=c0,primary=primary,cbank=cbank,stack_depth=stack_depth)
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

def boundary_fixture(out: Path, return_address: int = 0xFF00) -> dict:
    """Move the call to the last ROM page without overwriting NES vectors.

    An absolute JMP replaces the former call, so there is no extra return
    address. Only the new high-page call pushes the inline-table base.
    """
    if return_address not in (0xFEFF,0xFF00,0xFF01,0xFFF7):
        raise ValueError('Unsupported boundary fixture address')
    meta=create(out,selectors=[0])
    raw=bytearray((out/'fixture.nes').read_bytes())
    counts=bytearray((out/'counts.u32').read_bytes())
    pcs=bytearray((out/'cpu-address.u16').read_bytes())
    caller=return_address-2
    physical=0x3E000+caller-0xE000
    original=meta['cases'][0]['call']
    original_physical=0x3E000+original-0xE000
    raw[16+original_physical:16+original_physical+3]=bytes((0x4C,caller&255,caller>>8))
    target=meta['cases'][0]['table_target']
    raw[16+physical:16+physical+5]=bytes((0x20,0x00,0xF7,target&255,target>>8))
    struct.pack_into('<I',counts,4*physical,1)
    struct.pack_into('<H',pcs,2*physical,caller)
    (out/'fixture.nes').write_bytes(raw)
    (out/'counts.u32').write_bytes(counts);(out/'cpu-address.u16').write_bytes(pcs)
    import hashlib
    meta['rom_sha256']=hashlib.sha256(raw).hexdigest()
    meta['expected_native_calls']=int(return_address<=0xFF00)
    meta['return_address']=return_address
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--outside-nmi',action='store_true');p.add_argument('--c0',action='store_true')
    a=p.parse_args();create(a.out,outside_nmi=a.outside_nmi,c0=a.c0)
