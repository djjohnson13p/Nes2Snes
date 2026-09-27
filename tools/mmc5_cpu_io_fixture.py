"""Authored ExRAM and multiplier programs, with no expected intermediate state."""
from native_fixture import Program
from opcodes6502 import OPS
from timeline_program import REGULAR
from mmc5_cpu_io import PROFILE,validate


def put(p,address,value):p.op('LDA','imm',value);p.op('STA','abs',address)


def seal(p,name,*,index=3,events=False,handler_mode=False):
    p.label('irq');p.op('PHA');p.op('INC','abs',0x6E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA')
    if handler_mode:put(p,0x5104,3)
    p.op('INC','abs',0x6E1);p.op('PLA');p.op('RTI')
    return validate(dict(name=name,origin=p.origin,code=p.finish().hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=0xFD,a=0x81,x=index,y=index,
        seed=0x53,counter=7,events=[dict(cycle=18,irq=False,nmi=True)] if events else [],
        memory_model=PROFILE,prg_banks=32,bank_code=[],bank_data=[]))


def access_case(op,mode=2,index=3,base=0x5CFF):
    name,addressing,_=OPS[op];p=Program(0xE100);p.op('SED');put(p,0x5104,mode)
    operand=base
    if addressing in ('ix','iy'):
        operand=0xFC if addressing=='ix' else 0xFF
        ptr=(operand+index)&255 if addressing=='ix' else operand
        put(p,ptr,base&255);put(p,(ptr+1)&255,base>>8)
    p.label('body');p.op('LDA','imm',0x7F);p.op('SEC')
    p.op(name,addressing,operand);p.op('STA','abs',0x6F0);p.op('JMP','abs','body')
    return seal(p,f'ex-access-{op:02x}-m{mode:02x}-x{index}-{base:04x}',index=index)


def transition_case(first=2,second=3,*,events=False):
    p=Program(0xE100);put(p,0x5104,first);put(p,0x5D00,0x19)
    put(p,0x5104,second);put(p,0x5D00,0x28)
    p.op('LDA','abs',0x5D00);p.op('STA','abs',0x6F0)
    put(p,0x5104,2);put(p,0x5EFF,0xB4)
    put(p,0x5102,0);put(p,0x5103,0);put(p,0x5FFF,0x42)
    p.label('loop');p.op('LDA','abs',0x5FFF);p.op('JMP','abs','loop')
    return seal(p,f'ex-transition-{first:02x}-{second:02x}'+('-nmi' if events else ''),events=events,handler_mode=events)


def multiply_case(pairs,name):
    p=Program(0xE100);p.op('SED')
    for i,(a,b) in enumerate(pairs):
        put(p,0x5205,a);put(p,0x5206,b)
        p.op('LDA','abs',0x5205);p.op('STA','abs',0x680+i*2)
        p.op('LDA','abs',0x5206);p.op('STA','abs',0x681+i*2)
    p.label('hold');p.op('JMP','abs','hold')
    return seal(p,name)


def immediate_case():
    p=Program(0xE100)
    for address,value in ((0x5205,255),(0x5206,129),(0x5205,128),(0x5206,0)):
        put(p,address,value)
        p.op('LDA','abs',0x5205);p.op('STA','abs',0x6F0)
        p.op('LDA','abs',0x5206);p.op('STA','abs',0x6F1)
    p.label('loop');p.op('JMP','abs','loop')
    return seal(p,'ex-mul-immediate')


def jump_case():
    p=Program(0xE100);put(p,0x5104,2)
    put(p,0x5CFF,0);put(p,0x5C00,0xE2);put(p,0x5D00,0x99);p.op('JMP','ind',0x5CFF)
    while p.pc<0xE200:p.op('NOP')
    p.label('target');p.op('INC','abs',0x6F0);p.op('JMP','abs','target')
    return seal(p,'ex-jump-wrap')


def cases():
    forms=[op for op,(n,m,_) in sorted(OPS.items()) if n in REGULAR and m in ('abs','absx','absy','ix','iy')]
    rows=[access_case(op,mode) for op in forms for mode in (2,3)]
    rows += [access_case(op,2,index) for op in (0xB1,0x91,0xA1,0x81,0xBD,0xFE) for index in (0,255)]
    rows += [access_case(op,2,3,0x5FFF) for op in (0xBD,0x9D,0xFE)]
    rows += [transition_case(a,b) for a,b in ((2,3),(3,2),(0xFE,0xFF),(0xFF,0xFE))]
    rows += [transition_case(events=True),jump_case(),immediate_case()]
    pairs=[(i,(i*73+19)&255) for i in range(256)]
    edges=(0,1,2,127,128,129,254,255)
    pairs += [(a,b) for a in edges for b in edges]
    rows += [multiply_case(pairs[i:i+3],f'ex-mul-{i:03d}') for i in range(0,len(pairs),3)]
    return rows


def fault_cases():
    rows=[]
    for mode in (0,1,0xFC,0xFD):
        p=Program(0xE100);put(p,0x5104,mode);p.op('JMP','abs',0xE100)
        rows.append(seal(p,f'ex-guard-mode-{mode:02x}'))
    for address in (0x5BFF,0x5204):
        p=Program(0xE100);p.op('NOP');p.op('LDA','absx',address);p.op('JMP','abs',0xE100)
        rows.append(seal(p,f'ex-guard-preliminary-{address:04x}',index=1))
    return rows
