"""Authored native timeline prototype: execute, charge, interrupt, return, repeat.

This deliberately small static translator is for procedural integration tests,
not arbitrary game conversion. Every byte and instruction boundary is supplied;
only straight native 8-bit ALU/RAM operations and explicit software control/stack
operations below are accepted. Original guest bytes never become a data-derived
code guess. Unknown targets fault rather than run unclassified data.
"""
from pathlib import Path
import json
import struct
import subprocess
from opcodes6502 import OPS
from guest_cycles import tables
from interrupt_boundary import native_tables
from build_viewer import ROOT,tool,finalize_rom,validate_sfc

BRANCHES={'BPL','BMI','BVC','BVS','BCC','BCS','BNE','BEQ'}
CONTROL={'JMP','JSR','RTS','RTI','PHA','PHP','PLA','PLP','TSX','TXS','CLI','SEI','CLD','SED'}
REGULAR={'LDA','LDX','LDY','STA','STX','STY','ADC','SBC','CMP','CPX','CPY',
         'AND','ORA','EOR','BIT','ASL','LSR','ROL','ROR','INC','DEC','CLC','SEC',
         'CLV','TAX','TAY','TXA','TYA','INX','INY','DEX','DEY','NOP'}

def validate_events(events: object) -> list[dict]:
    if not isinstance(events,list) or len(events)>64:raise ValueError('Require at most 64 authored events')
    previous=0
    for e in events:
        if not isinstance(e,dict) or set(e)!={'cycle','irq','nmi'}:raise ValueError('Unknown event fields')
        if type(e['cycle']) is not int or not previous<e['cycle']<=0xFFFFFF00:raise ValueError('Events must be strictly increasing positive cycles')
        if type(e['irq']) is not bool or type(e['nmi']) is not bool:raise ValueError('Request stimuli must be booleans')
        previous=e['cycle']
    return events


def memory_bytes(plan: dict) -> int:
    """Explicit ABI selection; the omitted profile preserves the prior prototype."""
    if 'memory_model' not in plan:
        return 512
    if plan['memory_model'] != 'internal-2k':
        raise ValueError('Unknown timeline memory model')
    return 2048


def decode(code: bytes,origin: int,starts: list[int], *, ram: bool=False) -> list[tuple]:
    if type(ram) is not bool:
        raise ValueError('RAM extension gate must be boolean')
    if not isinstance(code,bytes) or not 1<=len(code)<=2048 or type(origin) is not int or not 0x8000<=origin<=0xFFF0 or origin+len(code)>0xFFFA:
        raise ValueError('Require a bounded immutable cartridge program')
    if not isinstance(starts,list) or any(type(p) is not int for p in starts) or starts!=sorted(set(starts)):
        raise ValueError('Require unique ordered original instruction entries')
    pos=0;rows=[]
    while pos<len(code):
        if code[pos] not in OPS:raise ValueError('Unsupported original opcode')
        name,mode,size=OPS[code[pos]];raw=code[pos:pos+size]
        if len(raw)!=size:raise ValueError('Truncated original instruction')
        operand=int.from_bytes(raw[1:],'little');pc=origin+pos
        allowed=(name in REGULAR and mode in ('imp','imm','acc','zp'))
        allowed|=name in REGULAR and mode=='abs' and operand<512
        allowed|=name in CONTROL and mode=='imp'
        allowed|=name in ('JMP','JSR') and mode=='abs'
        allowed|=name in BRANCHES and mode=='rel'
        if ram:
            allowed |= name in REGULAR and mode in ('zpx','zpy','absx','absy','ix','iy')
            allowed |= name in REGULAR and mode == 'abs' and operand < 0x2000
            allowed |= name == 'JMP' and mode == 'ind' and operand < 0x2000
        if not allowed:raise ValueError('Instruction is outside the procedural translator contract')
        rows.append((pc,name,mode,raw,operand));pos+=size
    if [r[0] for r in rows]!=starts:raise ValueError('Missing or overlapping original instruction entries')
    for pc,name,mode,raw,operand in rows:
        target=operand if name in ('JMP','JSR') and mode=='abs' else (pc+2+(operand if operand<128 else operand-256))&65535 if mode=='rel' else None
        if target is not None and target not in starts:raise ValueError('Static control target is not an observed entry')
    return rows



def validate_plan(plan: object) -> dict:
    keys={'name','origin','code','starts','irq','nmi','steps','stack','a','x','y','seed','counter','events'}
    if not isinstance(plan,dict) or set(plan)-{'memory_model'}!=keys:
        raise ValueError('Unknown or missing timeline plan fields')
    import re
    if not isinstance(plan['name'],str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',plan['name']):
        raise ValueError('Unsafe fixture name')
    if not isinstance(plan['code'],str) or len(plan['code'])>4096:
        raise ValueError('Invalid immutable program encoding')
    size=memory_bytes(plan)
    code=bytes.fromhex(plan['code']);decode(code,plan['origin'],plan['starts'],ram=size==2048)
    for key in ('stack','a','x','y','seed','counter'):
        if type(plan[key]) is not int or not 0<=plan[key]<=255:
            raise ValueError('Declared boot inputs must be byte integers')
    if type(plan['steps']) is not int or not 1<=plan['steps']<=(31 if size==2048 else 112):
        raise ValueError('Step count exceeds the selected capture ABI capacity')
    if any(type(plan[k]) is not int or plan[k] not in plan['starts'] for k in ('irq','nmi')) or plan['irq']==plan['nmi']:
        raise ValueError('Distinct observed vector entries required')
    validate_events(plan['events'])
    return plan


def generate(code: bytes,origin: int,starts: list[int], *, ram: bool=False) -> str:
    rows=decode(code,origin,starts,ram=ram);out=[]
    for pc,name,mode,raw,operand in rows:
        out.append(f'''.a16
.i16
ins_{pc:04x}:
    sep #$20
.a8
    lda #${raw[0]:02X}
    sta GC_INPUT
    lda GT+9
    sta GC_INPUT+1
    lda GT+7
    sta GC_INPUT+2
    lda GT+8
    sta GC_INPUT+3
    stz GC_INPUT+10
    rep #$20
.a16
    lda #${operand:04X}
    sta GC_INPUT+4
    lda #${pc:04X}
    sta GC_INPUT+6
''')
        def resume(target):return f'''    rep #$30
.a16
.i16
    lda #${target&65535:04X}
    sta GT+4
    jmp retire
'''
        if ram and name in REGULAR and mode not in ('imp','imm','acc'):
            from timeline_ram import access
            out.append(access(name,mode,operand)+resume(pc+len(raw)))
        elif ram and name=='JMP' and mode=='ind':
            from timeline_ram import jump
            out.append(jump(operand))
        elif name in REGULAR:
            out.append('    jsr load_guest\n.a8\n.i8\n    .byte '+','.join(f'${v:02X}' for v in raw)+'\n    jsr save_guest\n'+resume(pc+len(raw)))
        elif name in BRANCHES:
            target=(pc+2+(operand if operand<128 else operand-256))&65535
            out.append(f'    jsr load_guest\n.a8\n.i8\n    {name.lower()} taken_{pc:04x}\n    jsr save_guest\n'+resume(pc+2)+f'.a8\n.i8\ntaken_{pc:04x}:\n    jsr save_guest\n'+resume(target))
        elif name=='JMP':out.append(resume(operand))
        elif name in ('CLI','SEI','CLD','SED'):
            mask={'CLI':0xFB,'SEI':4,'CLD':0xF7,'SED':8}[name];op='and' if name in ('CLI','CLD') else 'ora'
            out.append(f'    sep #$20\n.a8\n    lda GT+9\n    {op} #${mask:02X}\n    sta GT+9\n'+resume(pc+1))
        elif name in ('PHA','PHP','JSR'):
            out.append('    sep #$30\n.a8\n.i8\n    ldx GT+10\n')
            if name=='JSR':
                ret=pc+2
                out.append(f'    lda #${ret>>8:02X}\n    sta $0100,x\n    dex\n    lda #${ret&255:02X}\n')
            else:
                out.append('    lda GT+6\n' if name=='PHA' else '    lda GT+9\n    ora #$30\n')
            out.append('    sta $0100,x\n    dex\n    stx GT+10\n'+resume(operand if name=='JSR' else pc+1))
        elif name in ('PLA','PLP','RTS','RTI'):
            out.append('    sep #$30\n.a8\n.i8\n    ldx GT+10\n    inx\n    lda $0100,x\n')
            if name in ('PLA','PLP'):
                out.append('    sta GT+'+('6' if name=='PLA' else '9')+'\n    stx GT+10\n')
                if name=='PLA':out.append('    jsr set_nz\n')
                out.append(resume(pc+1))
            else:
                if name=='RTI':out.append('    sta GT+9\n    inx\n    lda $0100,x\n')
                out.append('    sta GT+4\n    inx\n    lda $0100,x\n    sta GT+5\n    stx GT+10\n    rep #$30\n.a16\n.i16\n')
                if name=='RTS':out.append('    inc GT+4\n')
                out.append('    jmp retire\n')
        elif name=='TSX':out.append('    sep #$20\n.a8\n    lda GT+10\n    sta GT+7\n    jsr set_nz\n'+resume(pc+1))
        elif name=='TXS':out.append('    sep #$20\n.a8\n    lda GT+7\n    sta GT+10\n'+resume(pc+1))
        else:raise AssertionError(name)
    out.append('PCs:\n    .word '+','.join(f'${r[0]:04X}' for r in rows)+'\nEntries:\n    .word '+','.join(f'ins_{r[0]:04x}' for r in rows)+'\n')
    return '\n'.join(out)


DRIVER=r'''
.setcpu "65816"
.segment "CODE"
.a8
.i8
Reset:
    sei
    cld
    clc
    xce
    rep #$30
.a16
.i16
    ldx #$1FF0
    txs
    lda #0
    tcd
    sep #$20
.a8
    pha
    plb
    stz $4200
    stz $420B
    stz $420C
    lda #$80
    sta $2100
    lda #0
    sta f:$7E1FFF
    ldx #0
clear_context:
    stz GT,x
    inx
    cpx #32
    bne clear_context
    ldx #0
copy_initial:
    lda f:InitialRAM,x
    sta $0000,x
    inx
    cpx #512
    bne copy_initial
    ldx #0
copy_registers:
    lda f:InitialRegisters,x
    sta GT+4,x
    inx
    cpx #7
    bne copy_registers
    rep #$20
.a16
    stz $1B02
next_instruction:
    lda GT+16
    cmp #TimelineSteps
    bne dispatch
    sep #$20
.a8
    lda #$5A
    sta f:$7E1FFF
halt:
    jmp halt
.a16
dispatch:
    ldx #0
find_pc:
    lda GT+4
    cmp f:PCs,x
    beq found
    inx
    inx
    cpx #TimelineInstructions*2
    bne find_pc
    sep #$20
.a8
    lda #$E1
    sta GT+14
    jmp fault
.a16
found:
    jmp (Entries,x)
retire:
.a16
.i16
    jsr GuestTimelineRetire
    sep #$20
.a8
    lda GT+14
    beq :+
    jmp fault
:
    jsr capture
    rep #$30
.a16
.i16
    jmp next_instruction
.a8
fault:
    lda #$EE
    sta f:$7E1FFF
    jmp halt

; Loading guest flags masks NES-only bits and keeps host M/X/I set and D clear.
; The original P's non-NZVC bits live in GT and survive normal ALU instructions.
.a16
.i16
load_guest:
    sep #$30
.a8
.i8
    lda GT+9
    and #$C3
    ora #$34
    pha
    ldx GT+7
    ldy GT+8
    lda GT+6
    plp
    rts
save_guest:
    sta GT+6
    stx GT+7
    sty GT+8
    php
    pla
    and #$C3
    sta $1B04
    lda GT+9
    and #$3C
    ora $1B04
    sta GT+9
    rts
set_nz:
    cmp #0
    php
    pla
    and #$82
    sta $1B04
    lda GT+9
    and #$7D
    ora $1B04
    sta GT+9
    rts
capture:
    rep #$10
.i16
    ldx #0
clear_header:
    stz $1C00,x
    inx
    cpx #32
    bne clear_header
    ldx #0
header_identity:
    lda GT,x
    sta $1C00,x
    inx
    cpx #14
    bne header_identity
    lda GT+20
    sta $1C0E
    lda GT+21
    sta $1C0F
    lda GT+22
    sta $1C10
    lda GT+19
    sta $1C11
    rep #$20
.a16
    lda GT+16
    sta $1C12
    sep #$20
.a8
    ldx $1B02
    ldy #0
write_header:
    lda $1C00,y
    sta f:$7F0000,x
    iny
    inx
    cpy #32
    bne write_header
    ldy #0
write_memory:
    lda $0000,y
    sta f:$7F0000,x
    iny
    inx
    cpy #512
    bne write_memory
    stx $1B02
    rts
.include "guest_cycles.inc"
.include "guest_interrupt.inc"
.include "guest_timeline.inc"
.include "program.inc"
.segment "RODATA"
.include "tables.inc"
TimelineEvents: .incbin "events.bin"
InitialRAM: .incbin "initial-ram.bin"
InitialRegisters: .incbin "initial-registers.bin"
.segment "HEADER"
.byte "TIMELINE INTEGRATION "
.byte $20,$00,$06,$00,$01,$00,$00
.word $FFFF,$0000
.segment "VECTOR"
.word 0,0,halt,halt,halt,halt,0,halt
.word 0,0,halt,0,halt,halt,Reset,halt
'''


def create_native(out: Path,plan: dict,initial: bytes,*,retirement: str|None=None,program_text: str|None=None,host_mode: str|None=None) -> Path:
    validate_plan(plan)
    if host_mode is not None:
        from timeline_host import MODES
        if not isinstance(host_mode,str) or host_mode not in MODES:
            raise ValueError('Unknown host NMI mode')
    ram_bytes=memory_bytes(plan)
    code=bytes.fromhex(plan['code']);rows=decode(code,plan['origin'],plan['starts'],ram=ram_bytes==2048);events=validate_events(plan['events'])
    if type(plan['steps']) is not int or not 1<=plan['steps']<=112:raise ValueError('Require 1..112 dependent steps')
    if not isinstance(initial,bytes) or len(initial)!=32+ram_bytes or any(initial[:4]) or int.from_bytes(initial[4:6],'little')!=plan['origin']:
        raise ValueError('Require one initial reference state at time zero and program entry')
    if any(initial[11:32]):raise ValueError('Initial state must precede requests and any executed step')
    if plan['irq'] not in plan['starts'] or plan['nmi'] not in plan['starts'] or plan['irq']==plan['nmi']:
        raise ValueError('Distinct observed vector entries required')
    out.mkdir(parents=True,exist_ok=True)
    (out/'initial-ram.bin').write_bytes(initial[32:])
    (out/'initial-registers.bin').write_bytes(initial[4:11])
    (out/'events.bin').write_bytes(b''.join(struct.pack('<IBBBB',e['cycle'],e['irq'],e['nmi'],0,0) for e in events))
    (out/'program.inc').write_text(generate(code,plan['origin'],plan['starts'],ram=ram_bytes==2048) if program_text is None else program_text)
    (out/'tables.inc').write_text(tables()+native_tables())
    for name in ('guest_cycles.inc','guest_interrupt.inc','guest_timeline.inc'):
        text=(ROOT/'snes/src'/name).read_text()
        if name=='guest_timeline.inc' and retirement is not None:text=retirement
        (out/name).write_text(text)
    prefix=f"TimelineSteps={plan['steps']}\nTimelineInstructions={len(rows)}\nTimelineEventCount={len(events)}\nTimelineIRQ=${plan['irq']:04X}\nTimelineNMI=${plan['nmi']:04X}\n"
    driver=DRIVER
    if ram_bytes==2048:
        # Every guest address is resolved before access; raw mirrors never touch
        # the host context at $1800. Capture all 2 KiB, at most 31 rows per bank.
        driver=driver.replace('cpx #512','cpx #2048').replace('cpy #512','cpy #2048')
        driver=driver.replace('.include "guest_cycles.inc"','.include "timeline_ram.inc"\n.include "guest_cycles.inc"')
        (out/'timeline_ram.inc').write_bytes((ROOT/'snes/src/timeline_ram.inc').read_bytes())
    if host_mode is not None:
        from timeline_host import prepare
        driver=prepare(out,driver,host_mode)
    (out/'fixture.s').write_text(prefix+driver)
    subprocess.run([tool('ca65'),'-g','-I',str(out),'--bin-include-dir',str(out),'-o',str(out/'fixture.o'),str(out/'fixture.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),'-o',str(out/'fixture.bin'),str(out/'fixture.o')],check=True)
    data=finalize_rom((out/'fixture.bin').read_bytes(),b'');validate_sfc(data)
    path=out/'fixture.sfc';path.write_bytes(data);return path
