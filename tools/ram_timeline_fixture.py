"""Authored dependent programs for all supported internal-RAM addressing forms.

The ROM establishes operands and pointers through normal instructions. Native
execution starts only from declared boot inputs, never from later reference rows.
"""
from opcodes6502 import OPS
from native_fixture import Program
from timeline_program import REGULAR, validate_plan

MEMORY_MODES = {'zp','zpx','zpy','abs','absx','absy','ix','iy'}


def finish(p: Program, name: str, *, index: int=3, events: bool=False, stack: int=0xFD) -> dict:
    p.label('irq');p.op('PHA');p.op('INC','abs',0x16E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA');p.op('INC','abs',0x1EE1);p.op('PLA');p.op('RTI')
    code=p.finish()
    return validate_plan(dict(name=name,origin=p.origin,code=code.hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=stack,
        a=0x81,x=index,y=index,seed=0x53,counter=7,
        events=[dict(cycle=17,irq=True,nmi=False),dict(cycle=46,irq=False,nmi=True)] if events else [],
        memory_model='internal-2k'))


def memory_case(op: int, variant: int, *, events: bool=False, index_override: int|None=None) -> dict:
    name,mode,_=OPS[op]
    index=0 if variant==0 else 3
    if index_override is not None:
        if type(index_override) is not int or not 0<=index_override<=255:
            raise ValueError('Index must be a byte integer')
        index=index_override
    operand=0x70 if variant==0 else 0xFF
    base=0x470 if variant==0 else 0x17FF
    if mode=='abs':operand=0x470 if variant==0 else 0x1CC0
    elif mode in ('absx','absy'):operand=base
    elif mode=='ix':operand=0x80 if variant==0 else 0xFC;base=0x470 if variant==0 else 0x1858
    elif mode=='iy':operand=0x80 if variant==0 else 0xFF
    address=(operand+index)&255 if mode in ('zpx','zpy') else operand if mode in ('zp','abs') else (base+index)&65535 if mode in ('absx','absy','iy') else base
    p=Program(0x80C0);p.op('CLI');p.op('SED')
    p.op('LDA','imm',0x96);p.op('STA','abs',address&0x7FF)
    if mode in ('ix','iy'):
        ptr=(operand+index)&255 if mode=='ix' else operand
        for cell,value in ((ptr,base&255),((ptr+1)&255,base>>8)):
            p.op('LDA','imm',value);p.op('STA','zp',cell)
    p.label('body');p.op('LDA','imm',0x7F);p.op('SEC' if variant else 'CLC')
    p.op(name,mode,operand)
    p.op('PHP');p.op('PHA');p.op('PLA');p.op('PLP')
    p.op('LDA','abs',address&0x7FF);p.op('EOR','imm',0x5A);p.op('STA','abs',0x6F0)
    p.op('JMP','abs','body')
    return finish(p,f'ram-{op:02x}-{variant}'+('-events' if events else '')+(f'-index-{index:02x}' if index_override is not None else ''),index=index,events=events,
                  stack=(0 if events else 0xFD))


def jump_case(pointer: int) -> dict:
    p=Program(0x80E0);target=0x8100
    for cell,value in ((pointer&0x7FF,target&255),
                       (((pointer&0xFF00)|((pointer+1)&255))&0x7FF,target>>8)):
        p.op('LDA','imm',value);p.op('STA','abs',cell)
    p.op('JMP','ind',pointer)
    while p.pc<target:p.op('NOP')
    p.label('body');p.op('INC','abs',0x16F0);p.op('JMP','abs','body')
    return finish(p,f'ram-jmp-{pointer:04x}')


def cases() -> list[dict]:
    rows=[memory_case(op,v) for op,(n,m,_) in sorted(OPS.items())
          if n in REGULAR and m in MEMORY_MODES for v in (0,1)]
    rows.extend(memory_case(op,1,events=True) for op in (0xBD,0xBE,0xB9,0xB6,0xA1,0xB1,0x81,0x91,0xFE,0xDE,0x7E,0xF1))
    rows.extend(jump_case(pointer) for pointer in (0x02FF,0x1FFF))
    return rows


def fault_cases() -> list[dict]:
    rows=[]
    # The ROM can describe an unsupported address, but execution must fault
    # before that access. Final RAM after 16-bit wrap does not authorize ROM
    # preliminary reads; guest scratch aliases, by contrast, are valid mirrors.
    for name,op,operand,target in [('cross-ppu',0x9D,0x1FFF,None),
                                   ('wrapped-read',0xB9,0xFFFF,None),
                                   ('indirect-ppu',0xB1,0x80,0x2000),
                                   ('indirect-rom',0x81,0x7F,0x8000)]:
        p=Program(0x8000)
        if target is not None:
            for cell,value in ((0x80,target&255),(0x81,target>>8)):
                p.op('LDA','imm',value);p.op('STA','zp',cell)
        p.op('LDA','imm',0x47);p.op('STA','abs',0x6F0)
        n,m,_=OPS[op];p.op(n,m,operand);p.op('JMP','abs',0x8000)
        rows.append(finish(p,'guard-'+name,index=1))
    return rows


def edge_cases() -> list[dict]:
    """High index bits and large zero-page/page-cross additions, not just +3."""
    return [memory_case(op,1,index_override=index)
            for op in (0xB5,0xB6,0xA1,0xB1,0x9D,0xFE)
            for index in (1,0x7F,0x80,0xFE,0xFF)]
