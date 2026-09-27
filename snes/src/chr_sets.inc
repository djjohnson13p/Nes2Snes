; Fixed-size, forced-blank MMC5 A/B transfers with 8x16 sprite mode.
; Guest B-bank state at $7E:5A00..5A08 is NOT host callback scratch.
; Callers use the existing dispatcher context; scratch remains protected MR.
CS_B=$7E5A00
CS_LAST=$7E5A08
.segment "CODE"
.proc ChrSetsInit
    rep #$30
.a16
.i16
    ldx #8
    sep #$20
.a8
    lda #0
clear:
    sta f:CS_B,x
    dex
    bpl clear
    lda #$20
    sta PV
    sta PV+9
    rep #$30
.a16
.i16
    rts
.endproc

; X is a 1-KiB pattern slot. Bank-set B repeats over both pattern halves
; except in 8-KiB mode, where the sole B register selects a full 8-KiB bank.
.proc ChrBank
    rep #$30
.a16
.i16
    lda f:CS_LAST
    and #$00FF
    bne set_b
    jmp ChrBankA
set_b:
    txa
    sta MR_ADDR
    ora #((1 << (3-ChrMode))-1)
    and #3
    asl a
    tax
    lda f:CS_B,x
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

; Existing 48-byte record keeps mode, upper latch, set A and mapped slots.
; Reuse its reserved padding for set B (8 bytes) and last-set selection (1).
.proc ChrSetsCapture
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
    tax
    sep #$20
.a8
.repeat 9, I
    lda f:CS_B+I
    sta f:$7E5222+I,x
.endrepeat
    rts
.endproc
