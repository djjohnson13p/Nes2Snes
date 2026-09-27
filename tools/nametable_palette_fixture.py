"""Authored fill-color and CPU-only ExRAM nametable reads, never expected results."""
from native_fixture import Program
from ppu_blank_fixture import put, address
from palette_timeline_fixture import seal, shadow_case


def color_case(value):
    p=Program(0xE100);p.op('SED');p.op('SEC')
    put(p,0x5105,0xFF);put(p,0x5106,value ^ 0xA7);put(p,0x5107,value)
    p.op('PHP');p.op('PLA');p.op('STA','abs',0x686)
    address(p,0x23BF)
    for i in range(3):
        p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    return seal(p,f'nt-color-{value:02x}')


def map_case(mapping,quadrant,mode=3,suffix=''):
    p=Program(0xE100)
    put(p,0x5104,mode);put(p,0x5105,mapping)
    put(p,0x5106,0xB6);put(p,0x5107,0xFE)
    address(p,0x23BF+quadrant*0x400)
    for i in range(3):
        p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    p.op('LDA','abs',0x5FBF);p.op('STA','abs',0x684)
    return seal(p,f'nt-map-{mapping:02x}-q{quadrant}-m{mode}{suffix}')


def mode_case(mode,quadrant):
    p=Program(0xE100)
    put(p,0x5104,2);put(p,0x5C00,0x6B);put(p,0x5105,0xAA)
    address(p,0x2000+quadrant*0x400)
    p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    put(p,0x5104,mode)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x681)
    p.op('LDA','abs',0x5C00);p.op('STA','abs',0x682)
    return seal(p,f'nt-mode-{mode}-q{quadrant}')


def cases():
    rows=[color_case(value) for value in range(256)]
    # Every mapping-register value; one selected quadrant in each such program.
    rows += [map_case(v,(v+v//16)%4,2+(v&1)) for v in range(256)]
    # Independently require every (quadrant, source) combination too.
    rows += [map_case((0x55 & ~(3<<(2*q))) | (s<<(2*q)),q,3,'-slot')
             for q in range(4) for s in range(4)]
    rows += [mode_case(mode,q) for mode in (2,3) for q in range(4)]
    for i in (0,0xBF,0xC0,0xFF):
        for step in (1,32):
            p=shadow_case(i,0xAA,step);p['name']='nt-'+p['name'];rows.append(p)
    return rows


def guard_cases():
    rows=[]
    for mode,q in ((2,0),(3,3)):
        p=Program(0xE100);put(p,0x5104,mode);put(p,0x5105,0xAA)
        address(p,0x2000+q*0x400);p.op('LDA','imm',0x77)
        stop=p.pc;retired=len(p.starts);p.op('STA','abs',0x2007)
        rows.append((seal(p,f'nt-guard-zero-write-{mode}-q{q}'),stop,retired))
    for mode in (0,1):
        p=Program(0xE100);put(p,0x5105,0xAA);put(p,0x5107,0xFF)
        p.op('LDA','imm',mode);stop=p.pc;retired=len(p.starts)
        p.op('STA','abs',0x5104)
        rows.append((seal(p,f'nt-guard-render-mode-{mode}'),stop,retired))
    return rows
