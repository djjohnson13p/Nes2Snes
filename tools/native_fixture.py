#!/usr/bin/env python3
"""Create original, redistributable CPU/mapper test input for the native bridge.

No bytes are extracted from any commercial game. The tiny assembler below emits
only documented NMOS 6502 instructions and records instruction starts explicitly.
The resulting RAM record can be compared against an independent NES emulator.
"""
from __future__ import annotations
import argparse, hashlib, json, struct
from pathlib import Path
from opcodes6502 import OPS
from build_native import OPERATIONS, MODES

class Program:
    def __init__(self, origin:int=0xE000):
        self.origin=origin; self.data=bytearray(); self.starts=[]
        self.labels={}; self.fixups=[]; self.results=[]; self.cursor=0x0300
        self.reverse={(n,m):(o,s) for o,(n,m,s) in OPS.items()}
    @property
    def pc(self):return self.origin+len(self.data)
    def label(self,name):
        if name in self.labels:raise ValueError(f'Duplicate label {name}')
        self.labels[name]=self.pc
    def op(self,name,mode='imp',value=0):
        opcode,size=self.reverse[name,mode]; self.starts.append(self.pc)
        self.data.append(opcode)
        if isinstance(value,str):self.fixups.append((len(self.data),mode,value));value=0
        if size>1:self.data.extend(int(value).to_bytes(size-1,'little'))
    def record(self,label):
        if self.cursor+4>0x0780:raise ValueError('Too many CPU records')
        self.results.append({'name':label,'address':self.cursor})
        self.op('STA','abs',self.cursor);self.op('STX','abs',self.cursor+1)
        self.op('STY','abs',self.cursor+2);self.op('PHP');self.op('PLA')
        self.op('AND','imm',0xC3);self.op('STA','abs',self.cursor+3);self.cursor+=4
    def finish(self):
        for off,mode,label in self.fixups:
            dest=self.labels[label]
            if mode=='rel':
                delta=dest-(self.origin+off+1)
                if not -128<=delta<=127:raise ValueError('Branch out of range')
                self.data[off]=delta&255
            else:self.data[off:off+2]=struct.pack('<H',dest)
        return bytes(self.data)

def create(out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    p=Program();p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    p.op('LDA','imm',0);p.op('LDX','imm',0);p.label('clear')
    for a in range(0,0x0800,0x100):p.op('STA','absx',a)
    p.op('INX');p.op('BNE','rel','clear')
    p.op('LDA','imm',2);p.label('raw_read_source');p.op('STA','abs',0x5100)
    p.op('LDA','imm',0x80);p.op('STA','abs',0x5115)
    p.op('LDA','imm',0x9e);p.op('STA','abs',0x5116)
    # Each supported operation in each documented addressing mode. All paths
    # start with known A/X/Y/carry/overflow and initialized memory/pointers.
    tests=[]
    for opcode,(name,mode,size) in OPS.items():
        if name in OPERATIONS and mode in MODES and mode!='zp':tests.append((opcode,name,mode))
    for opcode,name,mode in sorted(tests):
        p.op('LDA','imm',0xB7);p.op('STA','zp',1);p.op('STA','abs',0x0200)
        p.op('LDA','imm',0x00);p.op('STA','zp',0xFF);p.op('STA','zp',0xFD)
        p.op('LDA','imm',0x02);p.op('STA','zp',0);p.op('STA','zp',0xFE)
        p.op('LDX','imm',2);p.op('LDY','imm',2)
        # Operand choices deliberately exercise both zero-page pointer wrapping
        # and 2-KiB CPU RAM mirroring.
        operand={'zpx':255,'zpy':255,'abs':0x0A00,'absx':0x09FE,
                 'absy':0x09FE,'ix':0xFD,'iy':0xFD}[mode]
        if mode=='iy':
            p.op('LDA','imm',0xFE);p.op('STA','zp',0xFD)
            p.op('LDA','imm',0x01);p.op('STA','zp',0xFE)
        p.op('LDA','imm',0x45);p.op('CLC');p.op('CLV')
        p.op(name,mode,operand);p.record(f'{name}_{mode}_clear_carry')
        if name in ('STA','STX','STY','ASL','LSR','ROL','ROR','INC','DEC'):
            p.op('LDA','zp',1) if mode in ('zpx','zpy') else p.op('LDA','abs',0x0200)
            p.record(f'{name}_{mode}_stored_value')
    # Separate borrow, overflow and pointer wrapping cases.
    for name,a,b,carry in [('ADC',127,1,0),('ADC',255,0,1),('SBC',128,1,1),
                          ('SBC',0,255,0),('CMP',0,255,1),('ROL',0,128,1),('ROR',0,1,1)]:
        p.op('LDA','imm',b);p.op('STA','abs',0x0200)
        p.op('LDA','imm',a);p.op('SEC' if carry else 'CLC');p.op('CLV')
        p.op(name,'abs',0x0A00);p.record(f'{name}_edge_{a}_{b}_{carry}')
    # 16-bit effective-address wrap must not leak into the next SNES bank.
    p.op('LDA','imm',0x73);p.op('STA','zp',0)
    p.op('LDX','imm',1);p.op('LDA','absx',0xFFFF);p.record('absolute_wrap')
    # Raw data reads see original opcodes, not their COP replacements.
    p.op('LDA','abs','raw_read_source');p.record('raw_original_opcode')
    # Test every supported bank combination while execution stays in fixed ROM.
    for cb in (30,7):
        p.op('LDA','imm',cb|0x80);p.op('STA','abs',0x5116)
        for primary in range(16):
            p.op('LDA','imm',0x80+2*primary);p.op('STA','abs',0x5115)
            p.op('LDA','abs',0x8000);p.record(f'bank_{primary}_{cb}_8000')
            p.op('LDA','abs',0xC000);p.record(f'bank_{primary}_{cb}_c000')
    p.op('LDA','imm',0x5A);p.op('STA','zp',0x7E)
    p.label('done');p.op('JMP','abs','done')
    p.label('nmi');p.op('RTI')
    program=p.finish()
    if len(program)>0x1FFA:raise ValueError(f'Fixture exceeds fixed bank: {len(program)}')
    prg=bytearray(0x40000)
    for bank in range(32):prg[bank*8192]=bank
    prg[0x3E000:0x3E000+len(program)]=program
    struct.pack_into('<HHH',prg,0x3FFFA,p.labels['nmi'],p.origin,p.labels['nmi'])
    chr=bytes(((i//16)^i)&255 for i in range(0x20000))
    data=b'NES\x1a'+bytes([16,16,0x50,0])+bytes(8)+prg+chr
    (out/'fixture.nes').write_bytes(data)
    counts=[0]*0x40000;pcs=[0]*0x40000
    for pc in p.starts:counts[0x3E000+pc-0xE000]=1;pcs[0x3E000+pc-0xE000]=pc
    (out/'counts.u32').write_bytes(struct.pack('<262144I',*counts))
    (out/'cpu-address.u16').write_bytes(struct.pack('<262144H',*pcs))
    (out/'rgb-palette.bin').write_bytes(bytes(c for i in range(64) for c in (i*4,i*4,i*4)))
    meta={'rom_sha256':hashlib.sha256(data).hexdigest(),'procedural_fixture':True,
          'program_bytes':len(program),'records':p.results,'result_start':0x300,'result_end':p.cursor,
          'completion_marker':0x7E,'completion_value':0x5A,'complete_game_port':False}
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',required=True,type=Path)
    v=create(a.parse_args().out);print(f"Created {len(v['records'])} independent-emulator CPU/mapper records, {v['program_bytes']} program bytes")
