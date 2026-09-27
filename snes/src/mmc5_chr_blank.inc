; Blanked set-A CHR-ROM profile. NOT installed in native.s.
; CR: eight low bank bytes, two packed latched high-bit bytes, upper latch,
; temporary byte. Twelve bytes protected; calculation scratch reuses MR.
; Fixed ChrMode belongs to this explicit profile, not a live-mode approximation.
; Original CHR data is immutable and follows the separate original PRG image.
CR=$1C30
.segment "CODE"
.proc ChrInit
    rep #$30
.a16
.i16
    ldx #0
clear:
    stz CR,x
    inx
    inx
    cpx #12
    bne clear
    rts
.endproc
.proc ChrModeWrite
    sep #$20
.a8
    lda GT+6
    and #3
    cmp #ChrMode
    beq done
    jmp PpuUnsupported
done:
    rts
.endproc

; X16 slot 0..7 -> A16 physical 1-KiB bank. X/Y/scratch clobbered.
.proc ChrBank
    rep #$30
.a16
.i16
    txa
    sta MR_ADDR
    txa
    ora #((1 << (3-ChrMode))-1)
    tax
    sep #$20
.a8
    lda CR,x
    sta MR_INDEX
    txa
    and #3
    asl a
    rep #$20
.a16
    and #$00FF
    tay
    txa
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda CR+8,x
shift:
    cpy #0
    beq high
    lsr a
    dey
    bra shift
high:
    and #3
    sta MR_INDEX+1
    rep #$20
.a16
    lda MR_INDEX
.repeat (3-::ChrMode)
    asl a
.endrepeat
    sta MR_INDEX
    lda MR_ADDR
    and #((1 << (3-ChrMode))-1)
    clc
    adc MR_INDEX
    and #ChrMask
    rts
.endproc

; Return actual pattern byte A8. Normal nametables use the preceding resolver.
; ROM writes use MR_MODE=3 and are ignored by PpuDataWrite, retaining its latch,
; delayed buffer and single address-increment effects. No external bus claim.
.proc ChrResolve
    rep #$30
.a16
.i16
    lda PV+6
    and #$3FFF
    cmp #$2000
    bcc pattern
    jmp PpuResolve
pattern:
    and #$03FF
    sta PV+14
    lda PV+6
    xba
    and #$001C
    lsr a
    lsr a
    tax
    jsr ChrBank
    pha
    and #$001F
    xba
    asl a
    asl a
    ora PV+14
    ora #$8000
    sta MPTR
    pla
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc #ChrStartBank
    sep #$20
.a8
    sta MPTR+2
    lda #3
    sta MR_MODE
    phd
    rep #$20
.a16
    lda #MPTR
    tcd
    sep #$20
.a8
    lda [$00]
    pld
    rts
.endproc

; Snapshot: mode, upper latch, 8 u16 logical bank registers, 8 u16 mapped slots,
; fourteen zero padding bytes. Immutable CHR content is bound by the input hash.
.proc ChrCapture
    rep #$30
.a16
.i16
    lda GT+16
    dec a
    asl a
    asl a
    asl a
    asl a
    sta MR_BASE
    asl a
    clc
    adc MR_BASE
    sta MR_BASE
    tax
    ldy #48
    sep #$20
.a8
    lda #0
clear:
    sta f:$7E5200,x
    inx
    dey
    bne clear
    ldx MR_BASE
    lda #ChrMode
    sta f:$7E5200,x
    lda CR+10
    sta f:$7E5201,x
.repeat 8, I
    lda CR+I
    sta f:$7E5202+2*I,x
    lda CR+8+(I/4)
.repeat 2*(I .mod 4)
    lsr a
.endrepeat
    and #3
    sta f:$7E5203+2*I,x
.endrepeat
.repeat 8, I
    ldx #I
    jsr ChrBank
.a16
.i16
    ldx MR_BASE
    sta f:$7E5212+2*I,x
.endrepeat
    sep #$20
.a8
    rts
.endproc
