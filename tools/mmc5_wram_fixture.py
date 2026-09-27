"""Authored EWROM-like RAM programs. Boot and writes establish all test state."""
from native_fixture import Program
from opcodes6502 import OPS
from timeline_program import REGULAR
from mmc5_wram import PROFILE,validate


def put(p,address,value):p.op('LDA','imm',value);p.op('STA','abs',address)


def seal(p,name,*,index=3,events=None,handler_lock=False,extra=None) -> dict:
    p.label('irq');p.op('PHA');p.op('INC','abs',0x6E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA')
    if handler_lock:put(p,0x5102,0)
    p.op('INC','abs',0x6E1);p.op('PLA');p.op('RTI')
    return validate(dict(name=name,origin=p.origin,code=p.finish().hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=0xFD,a=0x81,x=index,y=index,
        seed=0x53,counter=7,events=events or [],memory_model=PROFILE,prg_banks=32,
        bank_code=extra or [],bank_data=[]))


def access_case(op,*,locked=False,index=3):
    name,mode,_=OPS[op];p=Program(0xE100);p.op('CLI');p.op('SED')
    put(p,0x5113,3)
    if not locked:put(p,0x5102,0xFE);put(p,0x5103,0xFD)
    operand=0x60FF if index else 0x6010
    if mode in ('ix','iy'):
        operand=0xFC if mode=='ix' else 0xFF
        pointer=(operand+index)&255 if mode=='ix' else operand
        put(p,pointer,0xFF);put(p,(pointer+1)&255,0x60)
    p.label('body');p.op('LDA','imm',0x7F);p.op('SEC')
    p.op(name,mode,operand);p.op('STA','abs',0x6F0);p.op('JMP','abs','body')
    return seal(p,f'cw-access-{op:02x}-l{int(locked)}-x{index}',index=index)


def protection_case(first,second):
    p=Program(0xE100)
    put(p,0x5102,first);put(p,0x5103,second)
    put(p,0x6000,0x91);p.op('LDA','abs',0x6000);p.op('STA','abs',0x6F0)
    put(p,0x5102,0);put(p,0x6000,0x28);p.op('LDA','abs',0x6000);p.op('STA','abs',0x6F1)
    p.label('hold');p.op('JMP','abs','hold')
    return seal(p,f'cw-lock-{first:02x}-{second:02x}')


def mapping_case(mode,register,bank):
    p=Program(0xE100);put(p,0x5102,2);put(p,0x5103,1)
    put(p,0x5113,bank&3);put(p,0x6100,0x91)
    put(p,register,bank);put(p,0x5100,mode)
    address={0x5114:0x8100,0x5115:0xA100,0x5116:0xC100}[register]
    p.op('LDA','abs',address);p.op('STA','abs',0x6F0)
    put(p,address,0x72);p.op('LDA','abs',0x6100);p.op('STA','abs',0x6F1)
    p.label('loop');p.op('LDA','abs',0x6100);p.op('JMP','abs','loop')
    return seal(p,f'cw-map-m{mode}-{register:04x}-{bank:02x}')


def persistence_case(*,events=False):
    p=Program(0xE100);put(p,0x5102,2);put(p,0x5103,1)
    put(p,0x6000,0x91);put(p,0x5113,3);put(p,0x6000,0x72)
    put(p,0x5113,0);p.op('LDA','abs',0x6000);p.op('STA','abs',0x6F0)
    put(p,0x5102,0);put(p,0x6000,0x37);p.op('LDA','abs',0x6000);p.op('STA','abs',0x6F1)
    p.label('hold');p.op('JMP','abs','hold')
    # Trigger after enabling writes, then the handler relocks them itself.
    req=[dict(cycle=12,irq=False,nmi=True)] if events else []
    return seal(p,'cw-persistence'+('-nmi' if events else ''),events=req,handler_lock=events)


def page_case(value):
    p=Program(0xE100);put(p,0x5113,value)
    p.label('read');p.op('LDA','abs',0x6000);p.op('STA','abs',0x6F0);p.op('JMP','abs','read')
    return seal(p,f'cw-page-{value:02x}')


def jump_case():
    p=Program(0xE100);put(p,0x5102,2);put(p,0x5103,1)
    put(p,0x60FF,0);put(p,0x6000,0xE2);put(p,0x6100,0x99);p.op('JMP','ind',0x60FF)
    while p.pc<0xE200:p.op('NOP')
    p.label('target');p.op('INC','abs',0x6F0);p.op('JMP','abs','target')
    return seal(p,'cw-jump-wrap')


def cross_case(op=0xBD):
    p=Program(0xE100);put(p,0x5102,2);put(p,0x5103,1)
    put(p,0x5113,1);put(p,0x5114,2)
    p.label('body');p.op('LDA','imm',0x91);n,m,_=OPS[op];p.op(n,m,0x7FFF)
    p.op('STA','abs',0x6F0);p.op('JMP','abs','body')
    return seal(p,f'cw-cross-{op:02x}')


def cases():
    forms=[op for op,(n,m,_) in sorted(OPS.items()) if n in REGULAR and m in ('abs','absx','absy','ix','iy')]
    rows=[access_case(op,locked=l) for op in forms for l in (False,True)]
    rows += [protection_case(a,b) for a in range(4) for b in range(4)]
    rows += [protection_case(a,b) for a,b in ((0xFE,0xFD),(0x82,0x81),(0xFF,0xFD),(0xFE,0xFC))]
    rows += [mapping_case(m,r,b) for m,r in ((1,0x5115),(2,0x5115),(2,0x5116),(3,0x5114),(3,0x5115),(3,0x5116)) for b in range(4)]
    rows += [page_case(v) for v in (0,1,2,3,8,9,10,11,0x80,0x81,0xFE&~4,0xFF&~4)]
    rows += [persistence_case(),persistence_case(events=True),jump_case(),cross_case(),cross_case(0x9D),cross_case(0xFE)]
    rows += [access_case(op,index=x) for op in (0xB1,0xA1,0x91,0x81,0xBD,0x9D) for x in (0,255)]
    return rows


def fault_cases():
    rows=[]
    for address,value,name in ((0x5113,4,'absent-chip'),(0x5114,4,'absent-upper-chip'),(0x5100,0,'mode-zero')):
        p=Program(0xE100);put(p,address,value);p.op('JMP','abs',0xE100)
        rows.append(seal(p,'cw-guard-'+name))
    p=Program(0xE100);put(p,0x5114,0);p.op('JMP','abs',0x8000)
    # Static target declared in ROM, never in RAM; execution after mapping RAM faults.
    q=Program(0x8000);q.op('NOP');q.op('JMP','abs',0x8000)
    extra=[dict(bank=0,origin=q.origin,code=q.finish().hex(),starts=q.starts)]
    rows.append(seal(p,'cw-guard-ram-code',extra=extra))
    p=Program(0xE100);put(p,0x9000,0x42);p.op('JMP','abs',0xE100)
    rows.append(seal(p,'cw-guard-rom-write'))
    p=Program(0xE100);p.op('NOP');p.op('LDA','absx',0x1FFF);p.op('JMP','abs',0xE100)
    rows.append(seal(p,'cw-guard-io-cross'))
    return rows
