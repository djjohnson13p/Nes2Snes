; Original 2A03 instruction-cost primitive, NOT installed in native.s.
; Input/output record $1840..$184D; caller exclusively owns $1840..$1853.
; Bytes: opcode,P,X,Y,operand.u16,originalPC.u16,pointer.u16,pointerValid,
;        cost,status,reserved. Status 0=ok,1=unsupported,2=missing pointer.
; Requires original bytes/registers; translated COP opcodes are not valid input.
; No guest execution, bus accesses, interrupt delivery, DMA or host-cycle claims.
; Preserves caller A/X/Y/D/DBR/P and balanced stack, with native mode required.
GC_INPUT=$1840
GC_COST=$184B
GC_STATUS=$184C
GC_SCRATCH=$1850
.segment "CODE"
.proc GuestInstructionCycles
    php
    rep #$30
.a16
.i16
    pha
    phx
    phy
    phd
    phb
    cld
    lda #0
    tcd
    sep #$20
.a8
    pha
    plb
    stz GC_COST
    stz GC_STATUS
    rep #$20
.a16
    lda GC_INPUT
    and #$00ff
    tax
    sep #$20
.a8
    lda f:GuestCycleBase,x
    bne supported
    lda #1
    sta GC_STATUS
    jmp done
supported:
    sta GC_COST
    lda f:GuestCycleAdjust,x
    bne :+
    jmp done
:
    cmp #4
    beq branch_cost
    cmp #3
    beq indirect_y
    cmp #1
    beq indexed_x
    lda GC_INPUT+3
    bra absolute_index
indexed_x:
    lda GC_INPUT+2
absolute_index:
    clc
    adc GC_INPUT+4
    bra crossing
indirect_y:
    lda GC_INPUT+10
    cmp #1
    beq :+
    stz GC_COST
    lda #2
    sta GC_STATUS
    bra done
:
    lda GC_INPUT+3
    clc
    adc GC_INPUT+8
crossing:
    bcc done
    inc GC_COST
    bra done
branch_cost:
    ; Validated branch opcode: high two bits choose N,V,C,Z; bit 5 is sense.
    txa
    and #$c0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    rep #$20
.a16
    and #$00ff
    tax
    sep #$20
.a8
    lda f:masks,x
    and GC_INPUT+1
    beq clear_flag
    lda GC_INPUT
    and #$20
    beq done
    bra taken
clear_flag:
    lda GC_INPUT
    and #$20
    bne done
taken:
    inc GC_COST
    rep #$20
.a16
    lda GC_INPUT+6
    clc
    adc #2
    sta GC_SCRATCH
    lda GC_INPUT+4
    and #$00ff
    cmp #$0080
    bcc :+
    ora #$ff00
:
    clc
    adc GC_SCRATCH
    eor GC_SCRATCH
    and #$ff00
    beq done
    sep #$20
.a8
    inc GC_COST
done:
    rep #$30
.a16
.i16
    plb
    pld
    ply
    plx
    pla
    plp
    rts
masks: .byte $80,$40,$01,$02
.endproc
