"""Explicit MMC5 PRG-ROM profile for the protected authored timeline.

Modes 1/2/3 and writes to $5100/$5114..$5117 only. PRG-RAM-selecting
writes are refused before mapper mutation. This is not PPU, expansion audio, MMC5 IRQ or
physical bus timing. Every (physical bank, CPU PC) execution entry is declared.
"""
from pathlib import Path
import re
import struct
import subprocess
from build_viewer import ROOT, tool, finalize_rom, validate_sfc
from opcodes6502 import OPS

PROFILE = 'mmc5-prg-rom'
REGISTERS = (0x5100, 0x5114, 0x5115, 0x5116, 0x5117)
INITIAL = (3, 0x80, 0x81, 0x82, 0xFF)


def slots(registers: tuple[int, ...], banks: int) -> tuple[int, ...]:
    """Effective physical 8-KiB ROM slots; 255 denotes selected unsupported RAM."""
    if (type(banks) is not int or not 4 <= banks <= 128 or banks & (banks-1)
            or not isinstance(registers, (tuple, list)) or len(registers) != 5
            or any(type(v) is not int or not 0 <= v <= 255 for v in registers)):
        raise ValueError('Invalid cartridge size or mapper-register image')
    mode, r0, r1, r2, r3 = registers
    mode &= 3
    if mode == 0:
        raise ValueError('Mode zero is outside this independently verified profile')
    def one(r): return r & (banks-1) if r & 128 else 255
    def pair(r):
        b = one(r)
        return (255, 255) if b == 255 else (b & ~1, (b & ~1)+1)
    if mode == 1: return pair(r1) + pair(r3 | 128)
    if mode == 2: return pair(r1) + (one(r2), one(r3 | 128))
    return (one(r0), one(r1), one(r2), one(r3 | 128))


def fragments(plan: dict) -> list[dict]:
    return [dict(bank=plan['prg_banks']-1, origin=plan['origin'], code=plan['code'],
                 starts=plan['starts'])] + plan['bank_code']


def validate(plan: dict) -> dict:
    from timeline_program import validate_events, decode
    keys = {'name','origin','code','starts','irq','nmi','steps','stack','a','x','y',
            'seed','counter','events','memory_model','prg_banks','bank_code','bank_data'}
    if not isinstance(plan, dict) or set(plan) != keys or plan['memory_model'] != PROFILE:
        raise ValueError('Unknown or missing banked timeline fields')
    if not isinstance(plan['name'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', plan['name']):
        raise ValueError('Unsafe fixture name')
    slots(INITIAL, plan['prg_banks'])
    if plan['origin'] != 0xE100:
        raise ValueError('Authored entry must follow boot in the final bank')
    if not isinstance(plan['bank_code'], list) or len(plan['bank_code']) > 32:
        raise ValueError('Require a bounded banked-code list')
    for key in ('stack','a','x','y','seed','counter'):
        if type(plan[key]) is not int or not 0 <= plan[key] <= 255:
            raise ValueError('Invalid boot byte')
    if type(plan['steps']) is not int or not 1 <= plan['steps'] <= 31:
        raise ValueError('Banked captures require 1..31 instructions')
    validate_events(plan['events'])
    occupied=set(); entries=set(); total=0
    for part in fragments(plan):
        if not isinstance(part,dict) or set(part) != {'bank','origin','code','starts'}:
            raise ValueError('Malformed banked-code record')
        bank,pc,text,starts = (part[k] for k in ('bank','origin','code','starts'))
        if type(bank) is not int or not 0 <= bank < plan['prg_banks'] or type(pc) is not int or not 0x8000 <= pc < 0xFFFA:
            raise ValueError('Invalid physical bank or original PC')
        if not isinstance(text,str) or not 0 < len(text) <= 2048:
            raise ValueError('Invalid banked code encoding')
        code=bytes.fromhex(text)
        if not code or (pc & 8191)+len(code)>8192 or pc+len(code)>0xFFFA:
            raise ValueError('Code crosses a bank or vector boundary')
        if bank == plan['prg_banks']-1 and (pc & 8191)<256:
            raise ValueError('Code overlaps the authored boot region')
        if not isinstance(starts,list) or any(type(v) is not int for v in starts) or starts!=sorted(set(starts)):
            raise ValueError('Require ordered original instruction entries')
        cells={(bank,i) for i in range(pc & 8191,(pc & 8191)+len(code))}
        if cells & occupied: raise ValueError('Overlapping physical code bytes')
        occupied |= cells; total += len(code)
        entries |= {(bank, v) for v in starts}
    if total > 2048: raise ValueError('Banked authored program is too large')
    targets={pc for _,pc in entries}
    for part in fragments(plan):
        decode(bytes.fromhex(part['code']),part['origin'],part['starts'],ram=True,rom=True,
               mapper=True,static_targets=targets)
    for k in ('irq','nmi'):
        if type(plan[k]) is not int or (plan['prg_banks']-1,plan[k]) not in entries:
            raise ValueError('Initial vectors must identify declared final-bank code')
    if plan['irq']==plan['nmi']: raise ValueError('Distinct vectors required')
    if not isinstance(plan['bank_data'],list) or len(plan['bank_data'])>128:
        raise ValueError('Invalid bank data list')
    count=0
    for row in plan['bank_data']:
        if not isinstance(row,dict) or set(row)!={'bank','offset','bytes'}:
            raise ValueError('Invalid bank-data fields')
        b,o,t=row['bank'],row['offset'],row['bytes']
        if type(b) is not int or not 0<=b<plan['prg_banks'] or type(o) is not int or not 0<=o<8192 or not isinstance(t,str) or not 0<len(t)<=8192:
            raise ValueError('Invalid bank-data range')
        data=bytes.fromhex(t);count+=len(data)
        if not data or o+len(data)>8192 or count>8192: raise ValueError('Bank-data budget exceeded')
        cells={(b,i) for i in range(o,o+len(data))}
        reserved={(plan['prg_banks']-1,i) for i in range(256)}
        # Default IRQ/NMI/reset vectors are immutable in the physical last bank.
        reserved |= {(plan['prg_banks']-1,i) for i in range(0x1FFA,0x2000)}
        if cells & (occupied|reserved): raise ValueError('Bank data overlaps code, boot or final vectors')
        occupied |= cells
    return plan


def write_code(address: int) -> str:
    index=REGISTERS.index(address)
    text='    sep #$20\n.a8\n    lda GT+6\n'
    if index==0:
        text+='''    and #3
    bne :+
    lda #5
    sta GT+14
    jmp fault
:
    lda GT+6
'''
    if 1 <= index <= 3:
        text+='''    bmi :+
    lda #5
    sta GT+14
    jmp fault
:
    lda GT+6
'''
    return text+f'    sta MB_REG+{index}\n    jsr MapperRemap\n'


def access(name: str, mode: str, operand: int) -> str:
    from timeline_rom import access as rom_access
    return rom_access(name,mode,operand).replace('TimelineResolveROM','TimelineResolveMMC5')


def jump(operand: int) -> str:
    from timeline_rom import jump as rom_jump
    return rom_jump(operand).replace('TimelineReadMapped','MapperRead')


def create_nes(out: Path, plan: dict) -> Path:
    from native_fixture import Program
    validate(plan);out.mkdir(parents=True,exist_ok=True)
    banks=plan['prg_banks']
    # Independent per-bank signatures; original authored data, not expected state.
    raw=bytearray(((b*37+i*13+(i>>8)*7)^0x5A)&255 for b in range(banks) for i in range(8192))
    boot=Program(0xE000);boot.op('SEI');boot.op('CLD');boot.op('LDX','imm',255);boot.op('TXS')
    def store(a,v): boot.op('LDA','imm',v);boot.op('STA','abs',a)
    for a in (0x2000,0x2001,0x4010,0x4015):store(a,0)
    store(0x4017,0x40)
    for a,v in zip(REGISTERS,INITIAL):store(a,v)
    boot.op('LDA','imm',0);boot.op('LDX','imm',0);boot.label('clear')
    for a in range(0,2048,256):boot.op('STA','absx',a)
    boot.op('INX');boot.op('BNE','rel','clear')
    for a,v in ((0x20,plan['seed']),(0x21,plan['counter'])):store(a,v)
    boot.op('LDX','imm',plan['stack']);boot.op('TXS');boot.op('LDX','imm',plan['x']);boot.op('LDY','imm',plan['y'])
    boot.op('LDA','imm',0x24);boot.op('PHA');boot.op('LDA','imm',plan['a']);boot.op('PLP');boot.op('JMP','abs',plan['origin'])
    data=boot.finish()
    if len(data)>256:raise ValueError('Boot grew beyond reserved region')
    start=(banks-1)*8192;raw[start:start+len(data)]=data
    for part in fragments(plan):
        start=part['bank']*8192+(part['origin'] & 8191);code=bytes.fromhex(part['code']);raw[start:start+len(code)]=code
    for patch in plan['bank_data']:
        start=patch['bank']*8192+patch['offset'];data=bytes.fromhex(patch['bytes']);raw[start:start+len(data)]=data
    struct.pack_into('<HHH',raw,len(raw)-6,plan['nmi'],0xE000,plan['irq'])
    path=out/'fixture.nes';path.write_bytes(b'NES\x1a'+bytes((banks//2,1,0x50,0))+bytes(8)+raw+bytes(8192))
    return path


def create_native(out: Path, plan: dict, initial: bytes, *, retirement=None, program_text=None, host_mode=None) -> Path:
    from timeline_program import DRIVER, generate
    from timeline_fixture import expected_initial
    from guest_cycles import tables
    from interrupt_boundary import native_tables
    validate(plan)
    if not isinstance(initial,bytes) or initial != expected_initial(plan):raise ValueError('Only the declared authored boot state is accepted')
    if retirement is not None or program_text is not None:raise ValueError('Use explicit generated-source mutations for this profile')
    out.mkdir(parents=True,exist_ok=True)
    raw=create_nes(out/'original',plan).read_bytes()[16:16+plan['prg_banks']*8192]
    (out/'original-prg.bin').write_bytes(raw)
    (out/'initial-ram.bin').write_bytes(initial[32:]);(out/'initial-registers.bin').write_bytes(initial[4:11])
    (out/'events.bin').write_bytes(b''.join(struct.pack('<IBBBB',e['cycle'],e['irq'],e['nmi'],0,0) for e in plan['events']))
    (out/'tables.inc').write_text(tables()+native_tables())
    targets={pc for p in fragments(plan) for pc in p['starts']};program=[];entries=[]
    for part in fragments(plan):
        text=generate(bytes.fromhex(part['code']),part['origin'],part['starts'],ram=True,rom=True,mapper=True,static_targets=targets)
        text=text.split('PCs:\n')[0]
        text=re.sub(r'(ins_|taken_)([0-9a-f]{4})',lambda m:f'{m[1]}b{part["bank"]}_{m[2]}',text)
        program.append(text);entries += [(part['bank'],pc) for pc in part['starts']]
    program += ['PCs:\n    .word '+','.join(f'${pc:04X}' for _,pc in entries),
                'Banks:\n    .word '+','.join(str(b) for b,_ in entries),
                'Entries:\n    .word '+','.join(f'ins_b{b}_{pc:04x}' for b,pc in entries)]
    (out/'program.inc').write_text('\n'.join(program)+'\n')
    for name in ('guest_cycles.inc','guest_interrupt.inc','guest_timeline.inc','mmc5_prg.inc'):
        (out/name).write_bytes((ROOT/'snes/src'/name).read_bytes())
    retire=(out/'guest_timeline.inc').read_text()
    old='    lda #TimelineIRQ\n    sta GI+12\n    lda #TimelineNMI\n    sta GI+14'
    code=[]
    for address,target in ((0xFFFE,12),(0xFFFF,13),(0xFFFA,14),(0xFFFB,15)):
        code.append(f'    rep #$20\n.a16\n    lda #${address:04X}\n    jsr MapperRead\n.a8\n    sta GI+{target}')
    assert retire.count(old)==1;retire=retire.replace(old,'\n'.join(code));(out/'guest_timeline.inc').write_text(retire)
    driver=DRIVER.replace('cpx #512','cpx #2048').replace('cpy #512','cpy #2048')
    driver=driver.replace('.include "guest_cycles.inc"','.include "mmc5_prg.inc"\n.include "guest_cycles.inc"')
    driver=driver.replace('    stz $1B02\nnext_instruction:',
        '    jsr MapperInit\n    rep #$30\n.a16\n.i16\n    stz $1B02\nnext_instruction:')
    driver=driver.replace('dispatch:\n    ldx #0', '''dispatch:
    lda GT+4
    jsr MapperBank
    sep #$20
.a8
    sta MB_CURRENT
    lda GT+14
    beq :+
    jmp fault
:
    rep #$30
.a16
.i16
    ldx #0''')
    driver=driver.replace('    beq found\n    inx', '''    bne next_entry
    lda MB_CURRENT
    and #$00FF
    cmp f:Banks,x
    beq found
next_entry:
    inx''')
    driver=driver.replace('    ldx $1B02\n    ldy #0\nwrite_header:', '''    ldx #0
copy_mapper:
    lda MB_SLOTS,x
    sta $1C14,x
    inx
    cpx #4
    bne copy_mapper
    rep #$20
.a16
    lda GT+4
    jsr MapperBank
.a8
    sta $1C18
    ldx $1B02
    ldy #0
write_header:''')
    if host_mode is not None:
        from timeline_host import prepare
        driver=prepare(out,driver,host_mode)
    prefix=f"MapperBankMask={plan['prg_banks']-1}\nTimelineSteps={plan['steps']}\nTimelineInstructions={len(entries)}\nTimelineEventCount={len(plan['events'])}\nTimelineIRQ=${plan['irq']:04X}\nTimelineNMI=${plan['nmi']:04X}\n"
    (out/'fixture.s').write_text(prefix+driver)
    return reassemble(out)


def reassemble(out: Path) -> Path:
    subprocess.run([tool('ca65'),'-g','-I',str(out),'--bin-include-dir',str(out),'-o',str(out/'fixture.o'),str(out/'fixture.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),'-o',str(out/'fixture.bin'),str(out/'fixture.o')],check=True)
    data=finalize_rom((out/'fixture.bin').read_bytes(),(out/'original-prg.bin').read_bytes());validate_sfc(data)
    path=out/'fixture.sfc';path.write_bytes(data);return path
