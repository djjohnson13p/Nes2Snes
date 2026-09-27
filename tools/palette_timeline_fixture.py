"""Ordinary-controller-free authored programs; no expected results in execution.

A completion byte followed by a direct self-jump makes final register and memory
state stable while an unmodified reference completes its video frame. No guest
interrupt requests, DMC, rendering or status polling are claimed in this matrix.
"""
from native_fixture import Program
from ppu_blank_fixture import put,address
from palette_timeline import PROFILE,validate


def seal(p,name):
    if len(p.starts)+2>30:raise ValueError('Program does not reach completion within budget')
    put(p,0x7E,0x5A)
    p.label('hold');p.op('JMP','abs','hold')
    p.label('irq');p.op('RTI');p.label('nmi');p.op('RTI')
    return validate(dict(name=name,origin=p.origin,code=p.finish().hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=0xFD,a=0x81,x=3,y=3,
        seed=0x53,counter=7,events=[],memory_model=PROFILE,prg_banks=4,
        bank_code=[],bank_data=[],chr_banks=8,chr_mode=3))


def read_case(index,value,gray=0,high=0xC0,increment=1,mapping=0x44,mirror=False):
    p=Program(0xE100);p.op('SED')
    port=0x3FFF if mirror else 0x2007;addr=port-1
    put(p,0x5105,mapping)
    address(p,0x3F00+index,addr);put(p,port,value)
    # Read via a mirror of the address just written, including backdrop aliases.
    target=(index&31)^0x10 if index%4==0 else index&31
    address(p,0x3F00+target,addr)
    put(p,0x2000,4 if increment==32 else 0);put(p,0x2001,gray)
    put(p,0x2002,high|0x15)
    p.op('LDA','abs',port);p.op('STA','abs',0x680)
    p.op('PHP');p.op('PLA');p.op('STA','abs',0x681)
    p.op('LDA','abs',0x2000);p.op('STA','abs',0x682)
    return seal(p,f'pal-{index:02x}-{value:02x}-g{gray}-h{high:02x}-i{increment}-m{mapping:02x}-{int(mirror)}')


def shadow_case(index,mapping,increment=1):
    p=Program(0xE100)
    put(p,0x5105,mapping)
    put(p,0x2000,4 if increment==32 else 0)
    address(p,0x3F00+index);put(p,0x2007,0x7F)
    address(p,0x3F00+index)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    address(p,0x2100)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x681)
    return seal(p,f'pal-shadow-{index:02x}-m{mapping:02x}-i{increment}')


def boundary_case(addr,increment):
    p=Program(0xE100);put(p,0x2000,4 if increment==32 else 0)
    address(p,addr)
    for value in (0xFF,0x56,0xA9):put(p,0x2007,value)
    address(p,addr)
    for i in range(3):p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    return seal(p,f'pal-boundary-{addr:04x}-{increment}')


def cases():
    # All 256 aliases and byte values, not a Cartesian product of every option.
    rows=[read_case(i,(i*73+19)&255,i&1,(i&3)<<6,32 if i%5==0 else 1,
                    (0x00,0x44,0xFF)[i%3],bool(i&4)) for i in range(256)]
    rows += [read_case(i,v,g,h) for i in (0,4,8,12,16,20,24,28)
             for v,g,h in ((0,0,0),(0xFF,1,0x80))]
    rows += [shadow_case(i,m,n) for i in (0,0xBF,0xC0,0xFF) for m in (0,0x44,0xFF) for n in (1,32)]
    rows += [boundary_case(a,n) for a in (0x3EFF,0x3F00,0x3FFF,0x3FE0) for n in (1,32)]
    return rows
