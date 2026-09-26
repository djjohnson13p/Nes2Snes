; Function-level serial-poll replacement, NOT general controller emulation.
; The generated wrapper requires a guest-NMI context and X in 0..2. Its exact
; matched original body remains the fallback for every other X/context.
; Preserve hidden B, X, D/DBR and caller V/D/I. Return A=$30, Y=0, N=0,Z=1,
; C=the original second destination's bit 0, as eight serial ROLs would do.
.if USE_NATIVE_CONTROLLER
NativeControllerPoll:
.a8
.i8
    php
    rep #$20
.a16
    pha
    sep #$20
.a8
    phx
    CountRuntime $09A0
    lda #$01
    sta VAL
    rep #$10
.i16
    jsr WriteJoy             ; same physical input or logical-frame replay sample
    stz STROBE
    sep #$30
.a8
.i8
    lda JOYLATCH
    tax
    lda f:$800000+ControllerReverseBits,x
    sta TMP
    lda 1,s
    tax
    lda a:$0001,x
    sta VAL                  ; final rotate carry comes from this byte's bit 0
    lda TMP
    sta a:$0000,x
    lda #$00
    sta a:$0001,x
    lda JOYLATCH
    and #$80
    beq @clear
    lda #$41
    bra @last
@clear:
    lda #$40
@last:
    sta a:$0004              ; last first-port raw read
    lda #$40
    sta a:$0005              ; current bridge's unconnected second port
    lda #$FF
    sta JOYSHIFT             ; eight reads shift in eight one bits
    plx
    rep #$20
.a16
    pla
    sep #$20
.a8
    plp
    lda VAL
    lsr a
    lda #$30
    ldy #$00
    rtl
ControllerReverseBits:
    .repeat 256, n
        .byte ((n & 1)<<7)|((n & 2)<<5)|((n & 4)<<3)|((n & 8)<<1)|((n & 16)>>1)|((n & 32)>>3)|((n & 64)>>5)|((n & 128)>>7)
    .endrepeat
.endif
