"""Ordinary authored CPU programs exercising RAM DMA and its phase dependence."""
from native_fixture import Program
from ppu_blank_fixture import put
from chr_mode_rewrite_fixture import seal as previous_seal
from oam_dma_timeline import PROFILE,validate,masked_code


def seal(p,name):
    raw=p.finish();p.data=bytearray(masked_code(raw))
    result=previous_seal(p,name)
    tail=bytes.fromhex(result['code'])[len(raw):]
    return validate(dict(result,memory_model=PROFILE,code=(raw+tail).hex()))


def make_case(page,start,value,odd=False,twice=False):
    p=Program(0xE100)
    base=(page&7)*256
    # Executed writes, not expected snapshots, supply the source bytes.
    for address,byte in ((base,value),(base+1,value^0xA5),(base+254,value^0x3C),(base+255,value^0x59)):
        put(p,address,byte)
    put(p,0x2003,start)
    if odd:p.op('BIT','zp',0x40)  # A real three-cycle instruction changes DMA phase.
    put(p,0x4014,page)
    if twice:put(p,0x4014,(page&0x18)|((page+1)&7))
    p.op('LDA','abs',0x2000);p.op('STA','abs',0x680)
    p.op('LDA','abs',0x2004);p.op('STA','abs',0x681)
    return seal(p,f'dma-{page:02x}-{start:02x}-{value:02x}-{int(odd)}-{int(twice)}')


def cases():
    rows=[make_case(page,0,(page*73+7)&255,odd) for page in range(32) for odd in (False,True)]
    rows += [make_case(2,start,(start*19+7)&255,bool(start&4)) for start in range(256) if start%4!=3]
    rows += [make_case(page,start,0xA9,odd,True) for page in (0,6,7) for start in (0,254) for odd in (False,True)]
    unique={}
    for plan in rows:unique.setdefault(plan['code'],plan)
    return list(unique.values())


def guard_cases():
    rows=[]
    for page,start in ((0x20,0),(0x40,0),(0x60,0),(0x80,0),(0xFF,0),(2,3),(2,255)):
        p=make_case(page,start,0xFF)
        code=bytes.fromhex(p['code']);offset=code.index(b'\x8d\x14\x40')
        stop=p['origin']+offset;retired=p['starts'].index(stop)
        rows.append((p,stop,retired))
    return rows
