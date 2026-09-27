"""Redistributable instruction-timing cases with no commercial input.

Each NES test boots a tiny independent program, executes the selected opcode,
and stops. The original emulator supplies elapsed cycles. The SNES program runs
only the native accountant using those PRE-instruction inputs, not guest code.
"""
from __future__ import annotations
from pathlib import Path
import json
import struct
import subprocess
from opcodes6502 import OPS
from guest_cycles import Instruction, BRANCHES, metadata, tables
from native_fixture import Program
from build_viewer import ROOT, tool, finalize_rom, validate_sfc


def cases() -> list[dict]:
    rows=[]
    for op,(name,mode,size) in sorted(OPS.items()):
        variants=range(6) if mode=='rel' else range(3) if mode in ('absx','absy','iy') else range(2)
        for v in variants:
            pc=(0x8100,0x80FD,0x8102)[(v//2)%3] if mode=='rel' else 0x8100
            flags=0x3C if v%2==0 else 0xF3
            operand={'imm':0x59,'zp':0x40,'zpx':0xFF,'zpy':0xFF,'ix':0xFC,'iy':0xFF,
                     'abs':0x0300,'absx':0x0200 if v==0 else 0x02FF if v==1 else 0xFFFF,
                     'absy':0x0200 if v==0 else 0x02FF if v==1 else 0xFFFF,
                     'ind':0x02FF,'rel':0xF8 if v>=4 else 8}.get(mode,0)
            pointer=0x0200 if v==0 else 0x02FF if v==1 else 0xFFFF
            if name in BRANCHES:
                mask,sense=BRANCHES[name];taken=bool(v%2)
                flags=(flags|mask) if sense==taken else (flags&~mask)
            if name in ('JSR','JMP') and mode=='abs':operand=0xE100
            rows.append(dict(name=f'{op:02x}-{v}',opcode=op,pc=pc,operand=operand,
                             p=flags,x=3,y=3,pointer=pointer))
    return rows


def create_nes(out: Path, row: dict) -> Path:
    out.mkdir(parents=True,exist_ok=True)
    p=Program(0xE000)
    p.op('SEI');p.op('CLD');p.op('LDX','imm',255);p.op('TXS')
    def store(a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
    for a in (0x2000,0x2001,0x4010,0x4015):store(a,0)
    store(0x4017,0x40)
    for a in (0,0x40,0x42,0x200,0x201,0x202,0x2FF,0x300,0x301,0x302,0x102):store(a,0x69)
    # ($FC,X) with X=3 and ($FF),Y both exercise zero-page pointer wrapping.
    store(0xFF,row['pointer']&255);store(0,row['pointer']>>8)
    name,mode,size=OPS[row['opcode']]
    if name=='JMP' and mode=='ind':
        store(0x2FF,0);store(0x200,0xE1) # NMOS indirect-JMP wrap.
    if name in ('RTS','RTI'):
        dest=0xE0FF if name=='RTS' else 0xE100
        p.op('LDA','imm',dest>>8);p.op('PHA');p.op('LDA','imm',dest&255);p.op('PHA')
        if name=='RTI':p.op('LDA','imm',0x34);p.op('PHA')
    elif name in ('PLA','PLP'):
        p.op('LDA','imm',0xF3);p.op('PHA')
    p.op('LDX','imm',row['x']);p.op('LDY','imm',row['y'])
    p.op('LDA','imm',row['p']);p.op('PHA');p.op('LDA','imm',0x41);p.op('PLP')
    p.op('JMP','abs',row['pc'])
    rom=bytearray([0xEA])*32768
    setup=p.finish();assert len(setup)<256;rom[0x6000:0x6000+len(setup)]=setup
    op=bytes([row['opcode']])+row['operand'].to_bytes(2,'little')[:size-1]
    pos=row['pc']-0x8000;rom[pos:pos+size]=op
    jump=bytes([0x4C,0,0xE1])
    if name in BRANCHES:
        following=row['pc']+2;target=(following+(row['operand'] if row['operand']<128 else row['operand']-256))&65535
        rom[following-0x8000:following-0x8000+3]=jump
        rom[target-0x8000:target-0x8000+3]=jump
    elif name not in ('RTS','RTI','BRK','JMP','JSR'):
        rom[pos+size:pos+size+3]=jump
    # All terminal paths, including BRK's vector, enter this marker routine.
    stop=Program(0xE100);stop.op('LDA','imm',0x5A);stop.op('STA','zp',0x7E)
    stop.label('done');stop.op('JMP','abs','done');rom[0x6100:0x6100+len(stop.data)]=stop.finish()
    struct.pack_into('<HHH',rom,0x7FFA,0xE100,0xE000,0xE100)
    path=out/'fixture.nes';path.write_bytes(b'NES\x1a\x02\x01'+bytes(10)+rom+bytes(8192));return path


NATIVE_DRIVER = r'''
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
    stz $7E
    stz $7F
    rep #$20
.a16
    stz $1B00
    stz $1B02
again:
    ldx $1B00
    ldy #0
    sep #$20
.a8
copy:
    lda f:Inputs,x
    sta $1840,y
    inx
    iny
    cpy #14
    bne copy
    stx $1B00
    ; Exercise caller decimal and all M/X width combinations.
    lda $7F
    and #3
    rep #$20
.a16
    and #$FF
    tax
    lda #$0355
    tcd
    sep #$20
.a8
    lda #$7E
    pha
    plb
    lda f:Flags,x
    pha
    rep #$30
.a16
.i16
    lda #$1234
    ldx #$5678
    ldy #$ABCD
    plp
    jsr GuestInstructionCycles
    php
    rep #$30
.a16
.i16
    sta f:$7E1C00
    txa
    sta f:$7E1C02
    tya
    sta f:$7E1C04
    tdc
    sta f:$7E1C06
    sep #$20
.a8
    phb
    pla
    sta f:$7E1C08
    pla
    sta f:$7E1C09
    cld
    rep #$30
.a16
.i16
    tsc
    sta f:$7E1C0A
    lda #0
    tcd
    sep #$20
.a8
    pha
    plb
    ldx $1B02
    ldy #0
save_state:
    lda $1840,y
    sta f:$7E4000,x
    inx
    iny
    cpy #14
    bne save_state
    ldy #0
save_context:
    lda $1C00,y
    sta f:$7E4000,x
    inx
    iny
    cpy #12
    bne save_context
    stx $1B02
    inc $7F
    lda $7F
    cmp #CASE_COUNT
    beq complete
    rep #$20
.a16
    jmp again
.a8
complete:
    lda #$5A
    sta $7E
halt:
    jmp halt
unexpected:
    sep #$20
.a8
    lda #$EE
    sta f:$7E007E
    jmp unexpected
.include "guest_cycles.inc"
.segment "RODATA"
.include "tables.inc"
Flags: .byte $4D,$6F,$5D,$FD
Inputs: .incbin "inputs.bin"
.segment "HEADER"
.byte "GUEST CYCLE ACCOUNT  "
.byte $20,$00,$06,$00,$01,$00,$00
.word $FFFF,$0000
.segment "VECTOR"
.word 0,0,unexpected,unexpected,unexpected,unexpected,0,unexpected
.word 0,0,unexpected,0,unexpected,unexpected,Reset,unexpected
'''


def create_native(out: Path, inputs: list[bytes], *, kernel: str | None=None, table: str | None=None) -> Path:
    if not 1<=len(inputs)<=64 or any(len(row)!=14 for row in inputs):raise ValueError('Require 1..64 14-byte input records')
    out.mkdir(parents=True,exist_ok=True)
    (out/'inputs.bin').write_bytes(b''.join(inputs))
    (out/'guest_cycles.inc').write_text(kernel if kernel is not None else (ROOT/'snes/src/guest_cycles.inc').read_text())
    (out/'tables.inc').write_text(table if table is not None else tables())
    source=out/'fixture.s';source.write_text(f'CASE_COUNT={len(inputs)}\n'+NATIVE_DRIVER)
    subprocess.run([tool('ca65'),'-g','-I',str(out),'--bin-include-dir',str(out),'-o',str(out/'fixture.o'),str(source)],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),'-o',str(out/'fixture.bin'),str(out/'fixture.o')],check=True)
    data=finalize_rom((out/'fixture.bin').read_bytes(),b'');validate_sfc(data)
    path=out/'fixture.sfc';path.write_bytes(data);return path
