"""Authored NROM-256 reads; original cartridge bytes are not expected outputs."""
from native_fixture import Program
from opcodes6502 import OPS
from timeline_program import REGULAR, validate_plan
from timeline_ram import WRITES

READ_MODES = {'abs','absx','absy','ix','iy'}


def seal(p: Program, name: str, patches: list[dict], *, index: int=3, events: bool=False) -> dict:
    p.label('irq');p.op('PHA');p.op('INC','abs',0x16E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA');p.op('INC','abs',0x1EE1);p.op('PLA');p.op('RTI')
    code=p.finish()
    return validate_plan(dict(name=name,origin=p.origin,code=code.hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=0xFD,
        a=0x81,x=index,y=index,seed=0x53,counter=7,
        events=[dict(cycle=17,irq=True,nmi=False),dict(cycle=46,irq=False,nmi=True)] if events else [],
        memory_model='nrom-32k',rom_data=patches))


def read_case(op: int, variant: int, *, events: bool=False, base: int|None=None, index: int|None=None) -> dict:
    name,mode,_=OPS[op]
    if name not in REGULAR or name in WRITES or mode not in READ_MODES:
        raise ValueError('Require a cartridge-data read opcode')
    base=(0x9010 if variant==0 else 0x90FF) if base is None else base
    index=(0 if variant==0 else 3) if index is None else index
    operand=base
    p=Program(0x80C0);p.op('CLI');p.op('SED')
    if mode in ('ix','iy'):
        operand=0xFC if mode=='ix' else 0xFF
        pointer=(operand+index)&255 if mode=='ix' else operand
        for cell,value in ((pointer,base&255),((pointer+1)&255,base>>8)):
            p.op('LDA','imm',value);p.op('STA','zp',cell)
    p.label('body');p.op('LDA','imm',0x7F);p.op('SEC' if variant else 'CLC')
    p.op(name,mode,operand)
    p.op('PHP');p.op('PHA');p.op('PLA');p.op('PLP')
    p.op('STA','abs',0x6F0);p.op('JMP','abs','body')
    data=bytes(((i*73+19)^(i>>2))&255 for i in range(512))
    return seal(p,f'rom-{op:02x}-{variant}-{base:04x}-{index:02x}'+('-events' if events else ''),
                [dict(address=0x9000,bytes=data.hex())],index=index,events=events)


def jump_case(pointer: int) -> dict:
    p=Program(0x80C0);target=0x80E0
    p.op('JMP','ind',pointer)
    while p.pc<target:p.op('NOP')
    p.label('body');p.op('INC','abs',0x6F0);p.op('JMP','abs','body')
    high=(pointer&0xFF00)|((pointer+1)&255)
    patches=[dict(address=pointer,bytes=bytes([target&255]).hex()),
             dict(address=high,bytes=bytes([target>>8]).hex())]
    # A linear instead of NMOS wrapped pointer fetch must select the wrong PC.
    if pointer&255==255:patches.append(dict(address=pointer+1,bytes='99'))
    return seal(p,f'rom-jmp-{pointer:04x}',patches)


def cases() -> list[dict]:
    rows=[read_case(op,v) for op,(n,m,_) in sorted(OPS.items())
          if n in REGULAR and n not in WRITES and m in READ_MODES for v in (0,1)]
    rows.extend(read_case(op,1,events=True) for op in (0xBD,0xB1,0xA1,0xBE))
    # Self-code reads, both ROM halves, vector bytes, and 16-bit ROM-to-RAM wrap.
    rows.extend(read_case(0xBD,1,base=base,index=index)
                for base,index in ((0x80C0,0),(0x9FFF,3),(0xBFFF,3),(0xDFFF,3),
                                   (0xFFF9,6),(0xFFFF,3),(0x90FF,255)))
    rows.extend(jump_case(pointer) for pointer in (0x9201,0x92FF))
    return rows


def fault_cases() -> list[dict]:
    rows=[]
    for name,op,operand,index in (('store-rom',0x8D,0x9000,0),('rmw-rom',0xEE,0x9000,0),
                                  ('indexed-rom-write',0x9D,0x8FFF,1),
                                  ('preliminary-unmapped',0xBD,0x7FFF,1),
                                  ('wrapped-into-ppu',0xBD,0x1FFF,1)):
        p=Program(0x80C0);p.op('LDA','imm',0x47);p.op('STA','abs',0x6F0)
        n,m,_=OPS[op];p.op(n,m,operand);p.op('JMP','abs',0x80C0)
        rows.append(seal(p,'rom-guard-'+name,[],index=index))
    return rows
