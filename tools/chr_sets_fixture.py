"""Authored CHR-bank writes and PPUDATA reads; no expected result tables."""
from native_fixture import Program
from ppu_blank_fixture import put, address
from palette_timeline_fixture import seal as previous_seal
from chr_sets import PROFILE, validate


def seal(p, name, mode=3, banks=64):
    return validate(dict(previous_seal(p, name), memory_model=PROFILE,
                         chr_mode=mode, chr_banks=banks))


def switching(mode, slot, direction, value=0x59, upper=0, banks=64, offset=0x3FE):
    if direction not in ('ab', 'ba') or type(slot) is not int or not 0 <= slot < 8:
        raise ValueError('Require AB/BA and one of eight slots')
    p = Program(0xE100); p.op('SED')
    group_mask = (1 << (3-mode))-1
    a = 0x5120 + (slot | group_mask)
    b = 0x5128 + ((slot | group_mask) & 3)
    first, second = (a,b) if direction=='ab' else (b,a)
    put(p, 0x5130, upper)
    put(p, first, value)
    put(p, second, value ^ 0xA5)
    # A later upper-latch change must not modify either stored register.
    put(p, 0x5130, upper ^ 3)
    address(p, slot*1024 + offset)
    p.op('LDA', 'abs', 0x2007)  # Fill the delayed buffer from the second set.
    put(p, first, value)       # Switch sets using an actual register write.
    for dest in (0x680, 0x681):
        p.op('LDA', 'abs', 0x2007); p.op('STA', 'abs', dest)
    name = f'cs-{mode}-{slot}-{direction}-{value:02x}-{upper}-{banks}-{offset:x}'
    return seal(p, name, mode, banks)


def inactive(mode, index, is_b):
    p = Program(0xE100)
    put(p, 0x5127, 0x35); put(p, 0x512B, 0xA2)
    # Even an unchanged value in an inactive register selects its set.
    put(p, (0x5128 if is_b else 0x5120)+index, 0)
    address(p, 0x1011)
    for dest in (0x680,0x681):
        p.op('LDA','abs',0x2007);p.op('STA','abs',dest)
    return seal(p, f'cs-inactive-{mode}-{index}-{int(is_b)}', mode)


def interleave(kind):
    p = Program(0xE100)
    put(p,0x2003,0xFE);put(p,0x2004,0xED)
    put(p,0x5130,3);put(p,0x512B,0x41)
    if kind=='palette':
        address(p,0x3F14);put(p,0x2007,0x6D)
        address(p,0x3F04);p.op('LDA','abs',0x2007)
    elif kind=='scroll':
        put(p,0x2005,0x6F);put(p,0x5127,0x37);put(p,0x2005,0xD2)
    else:raise ValueError('Unknown interleaving')
    put(p,0x2004,0xF7);put(p,0x2003,0xFE)
    p.op('LDA','abs',0x2004);p.op('STA','abs',0x680)
    return seal(p,'cs-interleave-'+kind,3,1024)


def cases():
    rows = [switching(m,s,d,v,offset=o) for m in range(4) for s in range(8)
            for d in ('ab','ba') for v,o in ((0,0x10),(0x59,0x3FE))]
    rows += [switching(m,5,d,0xFD,u,1024) for m in range(4) for u in range(4) for d in ('ab','ba')]
    rows += [switching(m,7,d,0xAF,3,1<<b,0x3FF) for m in range(4) for b in range(3,11) for d in ('ab','ba')]
    rows += [inactive(m,i,b) for m in range(4) for b in (False,True) for i in range(4 if b else 8)]
    rows += [interleave(k) for k in ('palette','scroll')]
    # Don't inflate coverage with identical programs under different labels.
    unique = {}
    for p in rows:
        unique.setdefault((p['code'],p['chr_banks'],p['chr_mode']),p)
    return list(unique.values())


def guard_cases():
    rows=[]
    for name,op,port,value in (('sprite8','STA',0x2000,0),('nmi','STA',0x2000,0xA0),
                               ('render','STA',0x2001,0x18),('mode','STA',0x5101,0),
                               ('status','LDA',0x2002,0)):
        p=Program(0xE100);put(p,0x5130,3);put(p,0x512B,0xF1)
        if op=='STA':p.op('LDA','imm',value)
        stop=p.pc;retired=len(p.starts);p.op(op,'abs',port)
        rows.append((seal(p,'cs-guard-'+name,3,1024),stop,retired))
    return rows
