"""Authored input streams; no expected OAM bytes or intermediate states."""
from native_fixture import Program
from ppu_blank_fixture import put, address
from palette_timeline_fixture import seal as previous_seal
from oam_ports import PROFILE, validate


def seal(p, name):
    return validate(dict(previous_seal(p, name), memory_model=PROFILE))


def address_case(index, value, mirror=False):
    p=Program(0xE100);p.op('SED')
    addr, data=(0x3FFB,0x3FFC) if mirror else (0x2003,0x2004)
    put(p,addr,index);put(p,data,value)
    # Observe the full write latch BEFORE any later PPU write can replace it.
    p.op('LDA','abs',addr);p.op('STA','abs',0x680)
    put(p,data,value ^ 0xFF)
    put(p,addr,index)
    for destination in (0x681,0x682):
        p.op('LDA','abs',data);p.op('STA','abs',destination)
    p.op('PHP');p.op('PLA');p.op('STA','abs',0x683)
    return seal(p,f'oam-address-{index:02x}-{value:02x}-{int(mirror)}')


def interleave_case(kind):
    p=Program(0xE100)
    put(p,0x2003,0xFE);put(p,0x2004,0xFF)
    if kind=='chr':
        put(p,0x5130,3);put(p,0x5127,0xA5)
        address(p,0x1FFF);p.op('LDA','abs',0x2007)
    elif kind=='palette':
        address(p,0x3F14);put(p,0x2007,0xED)
        address(p,0x3F04);p.op('LDA','abs',0x2007)
    elif kind=='scroll':
        put(p,0x2005,0xAD);put(p,0x2004,0x37);put(p,0x2005,0xD6)
    else:raise ValueError('Unknown interleave case')
    put(p,0x2004,0x59);put(p,0x2004,0xA6)
    put(p,0x2003,0xFE);p.op('LDA','abs',0x2004);p.op('STA','abs',0x684)
    return seal(p,'oam-interleave-'+kind)


def cases():
    rows=[address_case(i,(i*73+19)&255,bool(i&1)) for i in range(256)]
    # A second independent sweep covers every stored attribute value at byte 2.
    rows += [address_case(2,v) for v in range(256) if v!=((2*73+19)&255)]
    rows += [interleave_case(k) for k in ('chr','palette','scroll')]
    return rows


def guard_cases():
    rows=[]
    for name,opcode,port,value in [('status','LDA',0x2002,0),('render','STA',0x2001,0x18),
                                  ('nmi','STA',0x2000,0x80),('chr-live','STA',0x5101,0)]:
        p=Program(0xE100);put(p,0x2003,2);put(p,0x2004,0xFF)
        if opcode=='STA':p.op('LDA','imm',value)
        stop=p.pc;retired=len(p.starts);p.op(opcode,'abs',port)
        rows.append((seal(p,'oam-guard-'+name),stop,retired))
    return rows
