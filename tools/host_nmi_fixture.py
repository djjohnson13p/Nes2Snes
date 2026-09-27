"""Native caller-register and scratch tests across real SNES vblank NMIs.

All 256 P values execute in native mode; M/X select actual register widths.
The optional bank-$80 mirror checks hardware PBR restoration. Expected outputs
are not in the ROM: it contains only initial inputs and captures actual returns.
"""
from pathlib import Path
import struct
import subprocess
from build_viewer import ROOT,tool,finalize_rom,validate_sfc
from timeline_host import PROTECTED,WORKER


def inputs() -> list[dict]:
    return [dict(p=p,dbr=0x7E+(p&1),d=0x300+((17*p)&255),
                 a=0xA000+p,x=0x56FF-p,y=0xCA00+p) for p in range(256)]


def scratch() -> bytes:
    return bytes((i*37+11)&255 for i in range(sum(n for _,n in PROTECTED)))


def reassemble(out: Path) -> Path:
    subprocess.run([tool('ca65'),'-g','-I',str(out),'--bin-include-dir',str(out),
                    '-o',str(out/'fixture.o'),str(out/'fixture.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),
                    '-Ln',str(out/'fixture.lbl'),'-o',str(out/'fixture.bin'),str(out/'fixture.o')],check=True)
    data=finalize_rom((out/'fixture.bin').read_bytes(),b'');validate_sfc(data)
    rom=out/'fixture.sfc';rom.write_bytes(data);return rom


def create(out: Path, *, nested: bool=False, mirror: bool=False) -> Path:
    if type(nested) is not bool or type(mirror) is not bool:
        raise ValueError('Native test settings must be booleans')
    out.mkdir(parents=True,exist_ok=True)
    (out/'inputs.bin').write_bytes(b''.join(struct.pack('<BBHHHH',r['p'],r['dbr'],r['d'],r['a'],r['x'],r['y']) for r in inputs()))
    (out/'scratch.bin').write_bytes(scratch())
    (out/'timeline_host_nmi.inc').write_bytes((ROOT/'snes/src/timeline_host_nmi.inc').read_bytes())
    text=r'''
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
    stz $1FFF
    ldx #0
clear_host:
    stz $1D00,x
    inx
    cpx #64
    bne clear_host
    lda #$A5
    sta $1E80
    lda #$5A
    sta $1FF1
'''
    offset=0
    for address,length in PROTECTED:
        text+=f'''    ldx #0
initial_{address:04x}:
    lda f:Scratch+{offset},x
    sta ${address:04X},x
    inx
    cpx #{length}
    bne initial_{address:04x}
'''
        offset+=length
    text+=f'''    lda #{int(nested)}
    sta HN_NEST
    jml ${0x800000 if mirror else 0:06X}+Begin
Begin:
    lda $4210
    lda #$80
    sta $4200
again:
    rep #$30
.a16
.i16
    ldx $1D12
    lda f:Inputs+4,x
    sta $1D20
    lda f:Inputs+6,x
    sta $1D22
    lda f:Inputs+8,x
    sta $1D24
    lda f:Inputs+2,x
    tcd
    sep #$20
.a8
    lda f:Inputs+1,x
    pha
    plb
    lda f:Inputs,x
    pha
    rep #$30
.a16
.i16
    lda f:$7E1D20
    ldx f:$7E1D22
    ldy f:$7E1D24
    plp
    wai
RegisterResume:
    php
    rep #$30
.a16
.i16
    sta f:$7E1D30
    txa
    sta f:$7E1D32
    tya
    sta f:$7E1D34
    tdc
    sta f:$7E1D36
    sep #$20
.a8
    phb
    pla
    sta f:$7E1D38
    pla
    sta f:$7E1D39
    phk
    pla
    sta f:$7E1D3C
    cld
    rep #$30
.a16
.i16
    tsc
    sta f:$7E1D3A
    lda #0
    tcd
    sep #$20
.a8
    pha
    plb
    ldx $1D14
    ldy #0
write_registers:
    lda $1D30,y
    sta f:$7F0000,x
    inx
    iny
    cpy #13
    bne write_registers
'''
    for address,length in PROTECTED:
        text+=f'''    ldy #0
write_{address:04x}:
    lda ${address:04X},y
    sta f:$7F0000,x
    inx
    iny
    cpy #{length}
    bne write_{address:04x}
'''
    text+=r'''    stx $1D14
    rep #$20
.a16
    lda $1D12
    clc
    adc #10
    sta $1D12
    inc $1D10
    lda $1D10
    cmp #256
    beq finished
    jmp again
finished:
    sep #$20
.a8
    stz $4200
    lda #$5A
    sta $1FFF
halt:
    jmp halt
.include "timeline_host_nmi.inc"
'''+WORKER+r'''
HostExpectedResume=RegisterResume
.segment "RODATA"
Inputs: .incbin "inputs.bin"
Scratch: .incbin "scratch.bin"
.segment "HEADER"
.byte "HOST NMI CONTEXT     "
.byte $20,$00,$06,$00,$01,$00,$00
.word $FFFF,$0000
.segment "VECTOR"
.word 0,0,halt,halt,halt,TimelineHostNMI,0,halt
.word 0,0,halt,0,halt,halt,Reset,halt
'''
    # 65816 LDX/LDY do not have absolute-long modes. DBR may be $7F here;
    # loading X/Y via the accumulator preserves the intended arbitrary DBR.
    text=text.replace('    lda f:$7E1D20\n    ldx f:$7E1D22\n    ldy f:$7E1D24',
                      '    lda f:$7E1D22\n    tax\n    lda f:$7E1D24\n    tay\n    lda f:$7E1D20')
    (out/'fixture.s').write_text(text)
    return reassemble(out)
