"""Original procedural program with arithmetic, subroutines and IRQ/NMI returns.

There is one initial state, not a table of expected per-step states. External
requests are declared as times in the original-cycle timeline and applied after
instructions on both platforms. This is intentionally not a physical pin model.
"""
from pathlib import Path
import struct
from native_fixture import Program
from timeline_program import decode,validate_events,validate_plan,memory_bytes


def program(origin: int=0x80D0) -> Program:
    p=Program(origin)
    p.op('SED');p.op('CLI');p.label('loop')
    p.op('INC','zp',0x20);p.op('CLC');p.op('LDA','zp',0x20);p.op('ADC','zp',0x21);p.op('STA','zp',0x20)
    p.op('JSR','abs','mix');p.op('LDX','zp',0x21);p.op('DEX');p.op('BNE','rel','skip');p.op('INC','zp',0x23)
    p.label('skip');p.op('INC','zp',0x21);p.op('LDA','zp',0x21);p.op('AND','imm',3);p.op('BEQ','rel','carry')
    p.op('SEC');p.op('BCS','rel','bottom');p.label('carry');p.op('CLC');p.label('bottom');p.op('JMP','abs','loop')
    p.label('mix');p.op('PHP');p.op('PHA');p.op('TXA');p.op('PHA');p.op('TYA');p.op('PHA')
    p.op('LDA','zp',0x20);p.op('EOR','imm',0xA5);p.op('ASL','acc');p.op('STA','zp',0x24)
    p.op('PLA');p.op('TAY');p.op('PLA');p.op('TAX');p.op('PLA');p.op('PLP');p.op('RTS')
    p.label('irq');p.op('PHA');p.op('TXA');p.op('PHA');p.op('TSX');p.op('STX','zp',0x27)
    p.op('INC','zp',0x25);p.op('SEI');p.op('LDA','zp',0x21);p.op('ADC','imm',1);p.op('STA','zp',0x21)
    p.op('PLA');p.op('TAX');p.op('PLA');p.op('RTI')
    p.label('nmi');p.op('PHA');p.op('TYA');p.op('PHA');p.op('INY');p.op('INC','zp',0x26)
    p.op('LDA','zp',0x20);p.op('EOR','imm',0x13);p.op('STA','zp',0x20);p.op('PLA');p.op('TAY');p.op('PLA');p.op('RTI')
    return p


def cases() -> list[dict]:
    schedules={
        'none':[],
        'irq':[(2,1,0),(27,0,0),(123,1,0),(167,0,0)],
        'nmi':[(1,0,1),(29,0,1),(157,0,1)],
        'both':[(2,1,1),(4,1,1),(150,1,1),(320,0,0)],
        'pulse':[(10,1,0),(11,0,0),(37,0,1),(38,0,1),(39,1,0),(80,0,0)],
        'entry-window':[(12,1,1),(15,0,1),(17,1,0),(21,0,0),(110,0,1)],
    }
    rows=[]
    for origin in (0x8000,0x80EC,0x80E2):
        p=program(origin);code=p.finish();decode(code,origin,p.starts)
        for i,(name,events) in enumerate(schedules.items()):
            rows.append(dict(name=f'{origin:04x}-{name}',origin=origin,code=code.hex(),starts=p.starts,
                             irq=p.labels['irq'],nmi=p.labels['nmi'],steps=112,
                             stack=(0,1,2,0x7F,0xFD,0xFF)[i],a=(0,0x7F,0x80,0xFF,0x45,0x69)[i],
                             x=i*7,y=255-i,seed=(i*57+0x53)&255,counter=i,
                             events=[dict(cycle=t,irq=bool(q),nmi=bool(n)) for t,q,n in events]))
    return rows


def create_nes(out: Path,plan: dict) -> Path:
    validate_plan(plan)
    if plan.get('memory_model')=='mmc5-ppu-blank':
        from mmc5_ppu_blank import create_nes as banked
        return banked(out,plan)
    if plan.get('memory_model')=='mmc5-cpu-io':
        from mmc5_cpu_io import create_nes
        return create_nes(out,plan)
    if plan.get('memory_model')=='mmc5-prg-ram32':
        from mmc5_wram import create_nes
        return create_nes(out,plan)
    if plan.get('memory_model')=='mmc5-prg-rom':
        from mmc5_timeline import create_nes as banked
        return banked(out,plan)
    code=bytes.fromhex(plan['code']);decode(code,plan['origin'],plan['starts'],ram=memory_bytes(plan)==2048,rom=plan.get('memory_model')=='nrom-32k');validate_events(plan['events'])
    out.mkdir(parents=True,exist_ok=True)
    boot=Program(0xE000);boot.op('SEI');boot.op('CLD');boot.op('LDX','imm',255);boot.op('TXS')
    boot.op('LDA','imm',0)
    for address in (0x2000,0x2001,0x4010,0x4015):boot.op('STA','abs',address)
    boot.op('LDA','imm',0x40);boot.op('STA','abs',0x4017)
    boot.op('LDA','imm',0);boot.op('LDX','imm',0);boot.label('clear')
    for address in range(0,2048,256):boot.op('STA','absx',address)
    boot.op('INX');boot.op('BNE','rel','clear')
    for address,value in ((0x20,plan['seed']),(0x21,plan['counter'])):
        boot.op('LDA','imm',value);boot.op('STA','zp',address)
    boot.op('LDX','imm',plan['stack']);boot.op('TXS')
    boot.op('LDX','imm',plan['x']);boot.op('LDY','imm',plan['y'])
    boot.op('LDA','imm',0x24);boot.op('PHA');boot.op('LDA','imm',plan['a']);boot.op('PLP')
    boot.op('JMP','abs',plan['origin'])
    memory=bytearray([0xEA])*32768;memory[0x6000:0x6000+len(boot.data)]=boot.finish()
    if plan.get('memory_model')=='nrom-32k':
        for patch in plan['rom_data']:
            begin=patch['address']-0x8000;raw=bytes.fromhex(patch['bytes'])
            memory[begin:begin+len(raw)]=raw
    pos=plan['origin']-0x8000;memory[pos:pos+len(code)]=code
    struct.pack_into('<HHH',memory,0x7FFA,plan['nmi'],0xE000,plan['irq'])
    path=out/'fixture.nes';path.write_bytes(b'NES\x1a\x02\x01'+bytes(10)+memory+bytes(8192));return path


def expected_initial(plan: dict) -> bytes:
    """The declared boot inputs, independently checked against original execution."""
    validate_plan(plan)
    data=bytearray(32+memory_bytes(plan));struct.pack_into('<H',data,4,plan['origin'])
    data[6:11]=bytes((plan['a'],plan['x'],plan['y'],0x24,plan['stack']))
    data[32+0x20]=plan['seed'];data[32+0x21]=plan['counter'];data[32+0x100+plan['stack']]=0x24
    if plan.get('memory_model') in ('mmc5-prg-rom','mmc5-prg-ram32','mmc5-cpu-io','mmc5-ppu-blank'):
        from mmc5_timeline import slots,INITIAL
        data[20:24]=bytes(slots(INITIAL,plan['prg_banks']));data[24]=data[23]
    if plan.get('memory_model') in ('mmc5-prg-ram32','mmc5-cpu-io','mmc5-ppu-blank'):
        data[25]=0x80
    if plan.get('memory_model') in ('mmc5-cpu-io','mmc5-ppu-blank'):
        data[28]=3
    return bytes(data)
