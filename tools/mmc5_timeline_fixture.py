"""Authored mapper-5 programs: register writes change subsequent real execution.

No expected bank result, data byte or intermediate machine state enters the
native sequencer. Bank signatures and the initial program are cartridge inputs.
"""
from native_fixture import Program
from opcodes6502 import OPS
from timeline_program import REGULAR
from timeline_ram import WRITES
from mmc5_timeline import validate


def part(p,bank):return dict(bank=bank,origin=p.origin,code=p.finish().hex(),starts=p.starts)


def seal(p,name,*,banks=32,extra=None,data=None,events=None,index=3,steps=31):
    p.label('irq');p.op('PHA');p.op('INC','abs',0x6E0);p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA');p.op('INC','abs',0x6E1);p.op('PLA');p.op('RTI')
    plan=dict(name=name,origin=p.origin,code=p.finish().hex(),starts=p.starts,
              irq=p.labels['irq'],nmi=p.labels['nmi'],steps=steps,stack=0xFD,
              a=0x81,x=index,y=index,seed=0x53,counter=7,events=events or [],
              memory_model='mmc5-prg-rom',prg_banks=banks,bank_code=extra or [],bank_data=data or [])
    return validate(plan)


def put(p,address,value):p.op('LDA','imm',value);p.op('STA','abs',address)


def read_case(op=0xBD,mode=2,register=0x85,*,banks=32,events=False):
    name,am,_=OPS[op]
    p=Program(0xE100);p.op('CLI');p.op('SED')
    put(p,0x5115,register);put(p,0x5116,0x89);put(p,0x5100,mode)
    address=0x9FFF
    if am in ('ix','iy'):
        address=0xFC if am=='ix' else 0xFF
        put(p,0xFF,0xFF);put(p,0x00,0x9F)
    p.label('body');p.op('LDA','imm',0x7F);p.op('SEC');p.op(name,am,address)
    p.op('STA','abs',0x6F0);p.op('JMP','abs','body')
    request=[dict(cycle=8,irq=True,nmi=False),dict(cycle=34,irq=False,nmi=True)] if events else []
    return seal(p,f'm5-read-{op:02x}-m{mode}-r{register:02x}-b{banks}'+('-irq' if events else ''),banks=banks,events=request)


def register_case(reg,value,mode=3,*,banks=32):
    p=Program(0xE100)
    # Execute from low bank zero so changing the top mapping cannot relocate boot.
    put(p,0x5115,0x81);put(p,0x5100,mode);p.op('JMP','abs',0x8000)
    low=Program(0x8000)
    put(low,reg,value)
    for a in (0x9000,0xB000,0xD000,0xF000):
        low.op('LDA','abs',a);low.op('STA','abs',0x600+(a>>13))
    low.op('JMP','abs',0x8000)
    # These cases only alter the upper group; bank zero remains the execution bank.
    return seal(p,f'm5-upper-m{mode}-r{value:02x}-b{banks}',banks=banks,extra=[part(low,0)])


def execution_case(*,events=False):
    p=Program(0xE100);p.op('CLI')
    put(p,0x5114,0x83);p.op('JSR','abs',0x8000)
    put(p,0x5114,0x84);p.op('JSR','abs',0x8000);p.op('JMP','abs',0xE100)
    a=Program(0x8000);put(a,0x6F0,0x31);a.op('RTS')
    b=Program(0x8000);put(b,0x6F1,0x42);b.op('RTS')
    req=[dict(cycle=27,irq=False,nmi=True)] if events else []
    return seal(p,'m5-code-bank-identity'+('-nmi' if events else ''),extra=[part(a,3),part(b,4)],events=req)


def current_bank_case(*,events=False):
    p=Program(0xE100);put(p,0x5117,0x84);p.op('INC','abs',0x600)
    put(p,0x5117,0xFF);p.op('INC','abs',0x601);p.op('JMP','abs',0xE100)
    q=Program(0xE105);q.op('INC','abs',0x602);put(q,0x5117,0xFF)
    n=Program(0xE200);n.op('INC','abs',0x603);n.op('RTI')
    i=Program(0xE210);i.op('INC','abs',0x604);i.op('RTI')
    vectors=(0xE200).to_bytes(2,'little')+(0xE000).to_bytes(2,'little')+(0xE210).to_bytes(2,'little')
    req=[dict(cycle=6,irq=False,nmi=True)] if events else []
    return seal(p,'m5-self-remap'+('-vector' if events else ''),extra=[part(q,4),part(n,4),part(i,4)],data=[dict(bank=4,offset=0x1FFA,bytes=vectors.hex())],events=req)


def fallthrough_case():
    p=Program(0xE100);put(p,0x5114,0x83);put(p,0x5115,0x85);p.op('JSR','abs',0x9FFC);p.op('JMP','abs',0xE100)
    a=Program(0x9FFC);a.op('LDA','imm',0x6A);a.op('NOP');a.op('NOP')
    b=Program(0xA000);b.op('STA','abs',0x6F0);b.op('RTS')
    return seal(p,'m5-bank-boundary-fallthrough',extra=[part(a,3),part(b,5)])


def cases():
    reads=[op for op,(n,m,_) in sorted(OPS.items()) if n in REGULAR and n not in WRITES and m in ('abs','absx','absy','ix','iy')]
    rows=[read_case(op,mode) for mode in (1,2,3) for op in reads]
    rows += [read_case(0xBD,2,r) for r in range(128,256) if r!=0x85]
    rows += [register_case(0x5117,v,mode) for mode in (1,2,3) for v in (0,1,2,3,7,8,15,16,31,32,63,64,127,128,254,255)]
    rows += [read_case(0xB1,2,events=True),execution_case(),execution_case(events=True),current_bank_case(),current_bank_case(events=True),fallthrough_case()]
    rows += [read_case(0xBD,mode,banks=b) for b in (4,8,16,64,128) for mode in (1,2,3)]
    return rows


def fault_cases():
    rows=[]
    for label,address,value in [('mode-zero',0x5100,0),('ram-bank',0x5115,4)]:
        p=Program(0xE100);p.op('LDA','imm',value);p.op('STA','abs',address);p.op('JMP','abs',0xE100)
        rows.append(seal(p,'m5-guard-'+label))
    p=Program(0xE100);p.op('LDA','imm',0x47);p.op('STA','abs',0x9000);p.op('JMP','abs',0xE100)
    rows.append(seal(p,'m5-guard-rom-write'))
    p=Program(0xE100);put(p,0x5114,0x84);p.op('JMP','abs',0x8000)
    q=Program(0x8000);q.op('NOP');q.op('RTS')
    rows.append(seal(p,'m5-guard-unobserved-bank',extra=[part(q,3)]))
    return rows
