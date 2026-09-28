"""Authored safe size changes and deliberately refused stale-register accesses."""
from native_fixture import Program
from ppu_blank_fixture import put, address
from chr_sets_fixture import seal as previous_seal
from chr_mode_rewrite import PROFILE, validate


def active(mode, bank_set):
    if type(mode) is not int or not 0 <= mode <= 3 or bank_set not in ('a','b'):
        raise ValueError('Require bank mode and A/B set')
    size = 1 << (3-mode)
    return list(range((0x5120 if bank_set=='a' else 0x5128)+size-1,
                      0x5128 if bank_set=='a' else 0x512C, size)) if mode else [0x5127 if bank_set=='a' else 0x512B]


def seal(p, name, mode=3, banks=64):
    return validate(dict(previous_seal(p,name,mode,banks),memory_model=PROFILE))


def transition(before, after, bank_set, slot, banks=64, upper=0, value=0x59):
    if type(slot) is not int or not 0 <= slot < 8:
        raise ValueError('Invalid pattern slot')
    active(before,bank_set); registers=active(after,bank_set)
    p=Program(0xE100)
    put(p,0x5130,upper)
    put(p,active(before,bank_set)[-1],value ^ 0xA5)
    address(p,slot*1024+0x11)
    p.op('LDA','abs',0x2007)
    put(p,0x5101,after | 0xA0)
    if len(registers)==8:
        p.op('LDA','imm',value)
        for reg in registers:p.op('STA','abs',reg)
        put(p,registers[slot],value ^ 0x33)
    else:
        for i,reg in enumerate(registers):put(p,reg,(value+29*i)&255)
    for dst in (0x680,0x681):p.op('LDA','abs',0x2007);p.op('STA','abs',dst)
    return seal(p,f'cm-{before}-{after}-{bank_set}-{slot}-{banks}-{upper}-{value:02x}',before,banks)


def no_change(mode, bank_set):
    p=Program(0xE100)
    put(p,active(mode,bank_set)[-1],0x59)
    put(p,0x5101,mode | 0xFC)
    address(p,0x1C11)
    for dst in (0x680,0x681):p.op('LDA','abs',0x2007);p.op('STA','abs',dst)
    return seal(p,f'cm-same-{mode}-{bank_set}',mode)


def interleave(kind):
    p=Program(0xE100)
    put(p,0x2003,0xFE);put(p,0x2004,0xED)
    put(p,0x5101,0)
    if kind=='palette':
        address(p,0x3F14);put(p,0x2007,0x6D);p.op('LDA','abs',0x2007)
    elif kind=='scroll':put(p,0x2005,0x6F);put(p,0x2005,0xD2)
    else:raise ValueError('Unknown interleave')
    put(p,0x512B,0x59);address(p,0x1411)
    p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    put(p,0x2004,0xF7)
    return seal(p,'cm-interleave-'+kind,3,1024)


def cases():
    rows=[transition(a,b,s,slot) for a in range(4) for b in range(4) if a!=b
          for s in ('a','b') for slot in (0,3,4,7)]
    rows += [transition(3,b,s,5,1<<n,upper=3,value=0xFD)
             for b in range(3) for s in ('a','b') for n in (3,7,10)]
    rows += [no_change(m,s) for m in range(4) for s in ('a','b')]
    rows += [interleave(k) for k in ('palette','scroll')]
    return rows


def guard_cases():
    rows=[]
    for kind in ('stale','partial-a','partial-b','other-set','status','render','nmi','sprite8'):
        p=Program(0xE100)
        if kind in ('stale','partial-a','partial-b','other-set'):
            put(p,0x5127,0x59);put(p,0x5101,1)
            if kind=='partial-a':put(p,0x5127,0x77)
            elif kind=='partial-b':put(p,0x5128,0x77)
            elif kind=='other-set':put(p,0x512B,0x77);put(p,0x5120,0x11)
            address(p,0x11)
            port=0x2007;op='LDA'
        else:
            put(p,0x5130,3)
            port,op,val={'status':(0x2002,'LDA',0),'render':(0x2001,'STA',0x18),
                         'nmi':(0x2000,'STA',0xA0),'sprite8':(0x2000,'STA',0)}[kind]
            if op=='STA':p.op('LDA','imm',val)
        stop=p.pc;retired=len(p.starts);p.op(op,'abs',port)
        rows.append((seal(p,'cm-guard-'+kind,3,1024),stop,retired))
    return rows
