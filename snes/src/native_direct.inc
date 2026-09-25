; Same-size absolute accesses enter a WRAM veneer via JSR. The veneer returns
; to the original execution bank using RTS. Compound work is in bank $80; its
; full context is restored before returning. Bank $C0 retains COP instructions.
.if USE_DIRECT_CALLS
.import __STUBS_LOAD__, __STUBS_RUN__, __STUBS_SIZE__
.assert __STUBS_SIZE__ <= $0800, lderror, "Direct-call veneers exceed reserved WRAM"
InitializeDirectStubs:
.a8
.i16
    ldx #__STUBS_RUN__
    stx $2181
    stz $2183
    stz $4300
    lda #$80
    sta $4301
    ldx #__STUBS_LOAD__
    stx $4302
    stz $4304
    ldx #__STUBS_SIZE__
    stx $4305
    lda #$01
    sta $420B
    rts

; On entry: A/X/Y are 8-bit guest registers except X is the selected writer
; index. Original X and P remain in the veneer stack. JSL adds three bytes.
; Save full A (including B), Y, D and DB before using any host scratch context.
.macro DirectWriteHandler name, value_offset
name:
.a8
.i8
    rep #$30
.a16
.i16
    pha
    phy
    phd
    phb
    inc $0980
    bne :+
    inc $0982
:
    lda #$0800
    tcd
    sep #$20
.a8
    lda #$00
    pha
    plb
    lda #$01
    sta COPBUSY
    lda value_offset,s
    sta VAL
    cpx #$0010
    bcs :+
    sta PPUBUS
:
    jsr (DirectWriters,x)
    sep #$20
.a8
    stz COPBUSY
    plb
    pld
    rep #$30
.a16
.i16
    ply
    pla
    sep #$30
.a8
.i8
    rtl
.endmacro
DirectWriteHandler DirectWriteA, 6
DirectWriteHandler DirectWriteX, 11
DirectWriteHandler DirectWriteY, 4
DirectWriters:
    .word WriteCtrl,WriteMask,WriteIgnore,WriteOaddr,WriteOdata,WriteScroll,WriteAddr,WritePpuData
    .word WriteOamDma,WriteJoy,WriteIrqPos,WriteIrqEnable

; LDA changes N/Z only. AND/ORA/LDA/STA preserve guest C/V/D/I. The joypad's
; internal shift additionally requires preserving C across that bookkeeping.
DirectReadStatus:
.a8
.i8
    lda STATUS
    and #$E0
    sta TMP
    lda PPUBUS
    and #$1F
    ora TMP
    pha
    lda STATUS
    and #$7F
    sta STATUS
    stz LATCH
    pla
    sta PPUBUS
    rtl
DirectReadJoy:
    php
    lda JOYSHIFT
    and #$01
    ora #$40
    sta TMP
    lda STROBE
    bne @held
    lda JOYSHIFT
    lsr a
    ora #$80
    sta JOYSHIFT
@held:
    plp
    lda TMP
    rtl
DirectReadJoy2:
    lda #$40
    rtl
DirectReadIrq:
    lda f:$004212
    and #$80
    beq @inframe
    lda #$00
    bra @pending
@inframe:
    lda #$40
@pending:
    ora IRQPENDING
    stz IRQPENDING
    rtl
.endif
.include "direct-stubs.inc"
