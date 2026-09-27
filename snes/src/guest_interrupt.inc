; Sampled-boundary NES interrupt entry. NOT installed in native.s.
; Native-mode caller owns $1860..$187F, guest stack $0100..$01FF for the call.
; Caller stack must be separate from guest stack. No asynchronous writes.
; Input: opcode,preP,postP,IRQ,NMI,S,PC.u16,decision,cost,status,reserved,
;        IRQvector.u16,NMIvector.u16. Outputs update postP,NMI,S,PC and result.
; Invalid opcode/requests/reserved: status 1/2, no guest change, no cycle charge.
; Original opcode and already-sampled line/latch input REQUIRED. Not pin polling,
; event deadlines, BRK/hijacking, stall accounting or real host IRQ delivery.
; Preserves caller A/X/Y/D/DBR/P and balanced stack, including all M/X modes.
GI=$1860
GI_CLASS=$1870
.segment "CODE"
.proc GuestInterruptBoundary
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
    stz GI+8
    stz GI+9
    stz GI+10
    lda GI+3
    cmp #2
    bcc :+
    jmp invalid_fields
:
    lda GI+4
    cmp #2
    bcc :+
    jmp invalid_fields
:
    lda GI+11
    beq :+
    jmp invalid_fields
:
    rep #$20
.a16
    lda GI
    and #$00FF
    tax
    sep #$20
.a8
    lda f:InterruptOpcodeClass,x
    beq invalid_opcode
    sta GI_CLASS
    lda GI+4
    bne nmi
    lda GI+3
    beq done
    lda GI_CLASS
    cmp #2
    beq old_i
    lda GI+2
    bra test_i
old_i:
    lda GI+1
test_i:
    and #4
    bne done
    lda #1
    sta GI+8
    bra push_frame
nmi:
    lda #2
    sta GI+8
    stz GI+4
push_frame:
    sep #$10
.i8
    ldx GI+5
    lda GI+7
    sta $0100,x
    dex
    lda GI+6
    sta $0100,x
    dex
    lda GI+2
    and #$EF
    ora #$20
    sta $0100,x
    dex
    stx GI+5
    lda GI+2
    ora #4
    sta GI+2
    lda #7
    sta GI+9
    lda GI+8
    cmp #2
    beq nmi_vector
    rep #$20
.a16
    lda GI+12
    bra set_pc
nmi_vector:
    rep #$20
.a16
    lda GI+14
set_pc:
    sta GI+6
    bra done
.a8
invalid_opcode:
    lda #1
    sta GI+10
    bra done
invalid_fields:
    lda #2
    sta GI+10
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
.endproc
