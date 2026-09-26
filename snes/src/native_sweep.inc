; Optional pulse sweep. Shares the explicit frame-quantized counter clock.
; Period is distinct from the last written register bytes, as on the NES.
; $0AF2..$0AFF was unallocated; guest context begins at $0B00.
.if USE_AUDIO_SWEEP
SWPERIOD = $0AF2                 ; words at +0, +4
SWDIV    = $0AF4                 ; bytes at +0, +4 (countdown to zero)
SWRELOAD = $0AF5
SWTARGET = $0AFA
SWCHANGE = $0AFC
SWSHIFT  = $0AFE
SWREG    = $0AFF

; Called after the ordinary shadow write. Preserve its A8/X16/Y16 inputs.
SweepWrite:
.a8
.i16
    pha
    phx
    cpx #$0008
    bcs @done
    txa
    and #$03
    cmp #$01
    beq @control
    cmp #$02
    beq @low
    cmp #$03
    beq @high
    bra @done
@control:
    dex
    lda #$01
    sta SWRELOAD,x              ; repeated values are still write events
    bra @done
@low:
    dex
    dex
    lda AEVENT
    sta SWPERIOD,x             ; retain the swept high bits
    bra @done
@high:
    dex
    dex
    dex
    lda AEVENT
    and #$07
    sta SWPERIOD+1,x           ; retain the swept low bits
@done:
    plx
    pla
    rts

; X16=0 or 4. Return A16 target and cache control/target. X/Y unchanged.
SweepTarget:
.a8
.i16
    lda f:$7E4001,x
    sta SWREG
    and #$07
    sta SWSHIFT
    rep #$20
.a16
    lda SWPERIOD,x
    sta SWCHANGE
    sep #$20
.a8
    lda SWSHIFT
    beq @ready
@shift:
    rep #$20
.a16
    lsr SWCHANGE
    sep #$20
.a8
    dec SWSHIFT
    bne @shift
@ready:
    lda SWREG
    and #$08
    bne @negative
    rep #$20
.a16
    lda SWPERIOD,x
    clc
    adc SWCHANGE
    sta SWTARGET
    rts
@negative:
    rep #$20
.a16
    lda SWPERIOD,x
    sec
    sbc SWCHANGE
    cpx #$0000
    bne :+
    dec a                       ; pulse 1 uses one's-complement subtraction
:
    and #$07FF
    sta SWTARGET
    rts

; A8=1 if inaudible due to current period or positive target overflow.
; Target overflow mutes even when sweep enable is clear or shift is zero.
SweepMuted:
.a8
.i16
    jsr SweepTarget
.a16
    lda SWPERIOD,x
    cmp #$0008
    bcc @yes16
    sep #$20
.a8
    lda SWREG
    and #$08
    bne @no
    rep #$20
.a16
    lda SWTARGET
    cmp #$0800
    bcs @yes16
    sep #$20
.a8
@no:
    lda #$00
    rts
@yes16:
    sep #$20
.a8
    lda #$01
    rts

; One half-frame opportunity. Update before consuming the divider reload flag.
SweepHalf:
.a8
.i16
    ldx #$0000
@channel:
    jsr SweepMuted
    bne @divider
    lda SWDIV,x
    bne @divider
    lda SWREG
    bpl @divider
    and #$07
    beq @divider
    rep #$20
.a16
    lda SWTARGET
    sta SWPERIOD,x
    sep #$20
.a8
@divider:
    lda SWDIV,x
    beq @reload
    lda SWRELOAD,x
    bne @reload
    dec SWDIV,x
    bra @next
@reload:
    lda SWREG
    lsr a
    lsr a
    lsr a
    lsr a
    and #$07
    sta SWDIV,x
    stz SWRELOAD,x
@next:
    cpx #$0004
    beq @done
    ldx #$0004
    jmp @channel
@done:
    rts
.endif
