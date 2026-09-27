"""Authored fixed-size CHR banking and buffered CPU transfers, not rendering."""
from native_fixture import Program
from ppu_blank_fixture import put,address
from mmc5_chr_blank import PROFILE,validate


def seal(p,name,banks=512,mode=3,events=None):
    p.label('hold');p.op('JMP','abs','hold')
    p.label('irq');p.op('PHA');p.op('INC','abs',0x6E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA');p.op('INC','abs',0x6E1);p.op('PLA');p.op('RTI')
    return validate(dict(name=name,origin=p.origin,code=p.finish().hex(),starts=p.starts,
        irq=p.labels['irq'],nmi=p.labels['nmi'],steps=31,stack=0xFD,a=0x81,x=3,y=3,
        seed=0x53,counter=7,events=events or [],memory_model=PROFILE,prg_banks=4,
        bank_code=[],bank_data=[],chr_banks=banks,chr_mode=mode))


def read_case(mode,slot,value,banks=512,upper=1,increment=1,edge=0x3FE):
    p=Program(0xE100);p.op('SED')
    register=slot|((1<<(3-mode))-1)
    put(p,0x5130,upper);put(p,0x5120+register,value)
    put(p,0x2000,4 if increment==32 else 0)
    address(p,slot*1024+edge)
    for i in range(3):p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    return seal(p,f'chr-m{mode}-s{slot}-v{value:02x}-b{banks}-u{upper}-i{increment}-e{edge:03x}',banks,mode)


def latch_case(mode):
    p=Program(0xE100)
    register=(1<<(3-mode))-1
    put(p,0x5130,3);put(p,0x5120+register,0x81)
    address(p,0x0011);p.op('LDA','abs',0x2007)
    # Changing upper bits alone cannot remap an already latched register.
    put(p,0x5130,0);p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    put(p,0x5120+register,0x23)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x681)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x682)
    return seal(p,f'chr-latch-m{mode}',1024,mode)


def write_case():
    p=Program(0xE100);address(p,0x3FD)
    p.op('LDA','abs',0x2007);put(p,0x2007,0x91)
    p.op('LDA','abs',0x2007);p.op('STA','abs',0x680)
    address(p,0x3FE)
    p.op('LDA','abs',0x2007);p.op('LDA','abs',0x2007);p.op('STA','abs',0x681)
    return seal(p,'chr-write-ignored',32,3)


def mirror_case():
    p=Program(0xE100);put(p,0x5130,0xFF);put(p,0x5127,0xFE)
    address(p,0x1FFF,0x3FFE)
    for i in range(3):p.op('LDA','abs',0x3FFF);p.op('STA','abs',0x680+i)
    return seal(p,'chr-mirror-to-nametable',1024,3)


def unchanged_mode_case(mode):
    p=Program(0xE100)
    put(p,0x5130,0xFD);put(p,0x5127,0xB7)
    # Only low mode bits matter; this does not change the active bank size.
    put(p,0x5101,0xFC|mode)
    address(p,0x1BFF)
    for i in range(3):p.op('LDA','abs',0x2007);p.op('STA','abs',0x680+i)
    return seal(p,f'chr-same-mode-{mode}',1024,mode)


def cases():
    rows=[read_case(m,s,v) for m in range(4) for s in range(8) for v in (1,0xFF)]
    rows += [read_case(m,0,0x7F,b,u,32) for b,u in ((8,0),(16,1),(32,1),(64,2),(128,3),(256,2),(512,3),(1024,3)) for m in range(4)]
    rows += [latch_case(m) for m in range(4)]+[write_case(),mirror_case()]
    p=read_case(3,4,0x31);p['name']='chr-guest-nmi';p['events']=[dict(cycle=28,irq=False,nmi=True)];rows.append(validate(p))
    rows += [unchanged_mode_case(m) for m in range(4)]
    for banks in (32,128):
        p=latch_case(3);p['prg_banks']=banks;p['name']=f'chr-prg-layout-{banks}';rows.append(validate(p))
    return rows


def fault_cases():
    rows=[]
    for addr,value in ((0x5101,2),(0x5128,1),(0x512B,0xFF),(0x2000,0x20),(0x2001,8)):
        p=Program(0xE100);p.op('NOP');put(p,addr,value);rows.append(seal(p,f'chr-guard-{addr:04x}-{value:02x}'))
    p=Program(0xE100);address(p,0x3F00);p.op('LDA','abs',0x2007);rows.append(seal(p,'chr-guard-palette'))
    return rows
