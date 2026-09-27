"""Authored PPU nametable programs; no expected results enter native execution."""
from itertools import product
from native_fixture import Program
from mmc5_ppu_blank import PROFILE,validate


def put(p,a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
def address(p,a,mirror=0x2006):put(p,mirror,(a>>8)&255);put(p,mirror,a&255)


def seal(p,name,events=None):
    p.label('hold');p.op('JMP','abs','hold')
    p.label('irq');p.op('PHA');p.op('INC','abs',0x6E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA');p.op('INC','abs',0x6E1);p.op('PLA');p.op('RTI')
    return validate(dict(name=name,origin=p.origin,code=p.finish().hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=0xFD,a=0x81,x=3,y=3,
        seed=0x53,counter=7,events=events or [],memory_model=PROFILE,prg_banks=32,bank_code=[],bank_data=[]))


def transfer(a=0x23FF,increment=1,mapping=0x44,mirror=False):
    p=Program(0xE100);p.op('SED')
    put(p,0x5105,mapping);put(p,0x2000,4 if increment==32 else 0)
    port=0x3FFE if mirror else 0x2006;data=0x3FFF if mirror else 0x2007
    address(p,a,port);put(p,data,0x91);put(p,data,0x62)
    address(p,a,port)
    for i in range(3):p.op('LDA','abs',data);p.op('STA','abs',0x680+i)
    return seal(p,f'pv-transfer-{a:04x}-{increment}-{mapping:02x}-{int(mirror)}')


def mapping_case(mapping):
    p=Program(0xE100);put(p,0x5105,mapping)
    for i in range(4):
        address(p,0x23C0+i*0x400)
        p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    return seal(p,f'pv-map-{mapping:02x}')


def fill_case(tile,attr):
    p=Program(0xE100);put(p,0x5105,0xFF);put(p,0x5106,tile);put(p,0x5107,attr)
    address(p,0x23BF);put(p,0x2007,0xA7);put(p,0x2007,0x18)
    address(p,0x23BF)
    for i in range(3):p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    return seal(p,f'pv-fill-{tile:02x}-{attr:02x}')


def latches(x,y,mirror=False):
    p=Program(0xE100)
    scroll=0x3FFD if mirror else 0x2005;addr=0x3FFE if mirror else 0x2006
    put(p,scroll,x);put(p,scroll,y);put(p,0x2000,(x&0x3F))
    put(p,addr,x);put(p,scroll,y)  # shared w: scroll now writes vertical bits
    put(p,scroll,y);put(p,addr,x)  # address now commits low byte
    put(p,0x2001,0xE1);put(p,0x2002,0xA5)
    for i,a in enumerate((0x2000,0x2001,scroll,addr)):
        p.op('LDA','abs',a);p.op('STA','abs',0x680+i)
    return seal(p,f'pv-latch-{x:02x}-{y:02x}-{int(mirror)}')


def buffer_case():
    p=Program(0xE100);address(p,0x2400)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    address(p,0x2000);put(p,0x2007,0x42)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x681)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x682)
    return seal(p,'pv-buffer-write-retains')


def cases():
    rows=[mapping_case(sum(v<<(i*2) for i,v in enumerate(values))) for values in product((0,1,3),repeat=4)]
    rows += [transfer(a,inc) for a in (0x2000,0x23DF,0x23FF,0x27FF,0x2FFF,0x3000,0x3EBF) for inc in (1,32)]
    rows += [transfer(a,1,mirror=True) for a in (0x2000,0x2FFF,0x3E00)]
    rows += [fill_case(tile,attr) for tile in (0,1,0x7F,0x80,0xFF) for attr in range(4)]
    values=(0,1,7,8,0x7F,0x80,0xF8,0xFF)
    rows += [latches(x,y,(x+y)%2==1) for x in values for y in values]
    rows += [buffer_case()]
    event=transfer();event['name']='pv-guest-nmi';event['events']=[dict(cycle=18,irq=False,nmi=True)]
    rows.append(validate(event))
    return rows


def fault_cases():
    rows=[]
    for a,v in ((0x2000,0x80),(0x2000,0x40),(0x2001,8),(0x2001,16),(0x5105,2),(0x5105,0x80),(0x5107,4)):
        p=Program(0xE100);p.op('NOP');put(p,a,v);rows.append(seal(p,f'pv-guard-{a:04x}-{v:02x}'))
    for a in (0x1FFF,0x3F00):
        p=Program(0xE100);address(p,a);p.op('LDA','abs',0x2007);rows.append(seal(p,f'pv-guard-data-{a:04x}'))
    for a in (0x2002,0x2004):
        p=Program(0xE100);p.op('NOP');p.op('LDA','abs',a);rows.append(seal(p,f'pv-guard-read-{a:04x}'))
    return rows
