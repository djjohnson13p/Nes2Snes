; Event-driven pulse/noise envelopes and four note-length counters.
; Enabled only with --audio-counters. Runtime frame clocks are deliberately
; quantized to four quarter-frame opportunities per logical game update.
; This is NOT a cycle-accurate APU: frame IRQ, sweep and DMC are still absent.
.if USE_AUDIO_COUNTERS
ALENGTH  = $0AA0              ; channel offsets 0,4,8,12
ADECAY   = $0AB0              ; envelopes at offsets 0,4,12
ADIVIDER = $0AC0
ARESTART = $0AD0
ALINEAR  = $0AE0
ALINRELOAD = $0AE1
APHASE   = $0AE2
AQUANTA  = $0AE3
AHALFCLOCKS = $0AE4
AQUARTERCLOCKS = $0AE6
AREGWRITES = $0AE8
AUPDATES = $0AEA
AOUTPUTFRAMES = $0AF0
AEVENT   = $0AEC
ASTATUS  = $0AED

; Generic COP path, entering with A16, X/Y16, D=$0800, DBR=0.
ApuWriteFromContext:
.a16
.i16
    lda EA
    and #$001F
    tax
    sep #$20
.a8
    lda VAL
    jmp ApuWriteRegister

; A8=value; X16=register index 0..23. DBR=0; D is immaterial.
; Shadow values are stored even for currently unsupported sweep/DMC registers.
ApuWriteRegister:
.a8
.i16
    sta f:$7E4000,x
    sta AEVENT
.if USE_AUDIO_SWEEP
    jsr SweepWrite
.endif
    rep #$20
.a16
    inc AREGWRITES
    sep #$20
.a8
    cpx #$0015
    jeq @enable
    cpx #$0017
    jeq @frame
    cpx #$0010
    bcs @done
    txa
    and #$03
    cmp #$03
    bne @done
    ; High-timer/length writes retrigger even when the value did not change.
    txa
    and #$0C
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #$01
    cpx #$0008
    beq @linear
    sta ARESTART,x
    bra @length
@linear:
    sta ALINRELOAD
@length:
    lda f:$7E4015
    and ApuEnableMask,x
    beq @done                ; enabling later must NOT resurrect an old note
    lda AEVENT
    lsr a
    lsr a
    lsr a
    rep #$20
.a16
    and #$001F
    tay
    sep #$20
.a8
    lda ApuLengthTable,y
    sta ALENGTH,x
@done:
    rts
@enable:
    ldx #$0000
@enable_loop:
    lda AEVENT
    and ApuEnableMask,x
    bne :+
    stz ALENGTH,x
:
    inx
    inx
    inx
    inx
    cpx #$0010
    bne @enable_loop
    rts
@frame:
    stz APHASE
    lda AEVENT
    bpl @done
    ; Five-step reset clocks half and quarter once. Real hardware delays this
    ; by 3/4 CPU cycles; this frame-quantized bridge processes it at the write.
    jsr ApuHalf
    jmp ApuQuarter

; Bits 0..3 reflect length counters. DMC and frame IRQ status are unsupported.
ApuReadStatus:
.a8
.i16
    stz ASTATUS
    ldx #$0000
@loop:
    lda ALENGTH,x
    beq :+
    lda ASTATUS
    ora ApuEnableMask,x
    sta ASTATUS
:
    inx
    inx
    inx
    inx
    cpx #$0010
    bne @loop
    lda ASTATUS
    rts

; Advance the coarse sequencer once per guest frame, not per host display.
; 4-step: Q,QH,Q,QH. 5-step: Q,QH,Q,-,QH. This intentionally makes the
; audio tempo track the existing slowed guest; no hidden host overclock.
ApuFrame:
.a8
.i16
    lda #$04
    sta AQUANTA
@tick:
    lda f:$7E4017
    bmi @five
    lda APHASE
    and #$01
    beq :+
    jsr ApuHalf
:
    jsr ApuQuarter
    inc APHASE
    lda APHASE
    cmp #$04
    bcc @next
    stz APHASE
    bra @next
@five:
    lda APHASE
    cmp #$03
    beq @five_advance
    cmp #$01
    beq @half
    cmp #$04
    bne @quarter
@half:
    jsr ApuHalf
@quarter:
    jsr ApuQuarter
@five_advance:
    inc APHASE
    lda APHASE
    cmp #$05
    bcc @next
    stz APHASE
@next:
    dec AQUANTA
    bne @tick
    rep #$20
.a16
    inc AUPDATES
    sep #$20
.a8
    rts

ApuHalf:
.a8
.i16
.if USE_AUDIO_SWEEP
    jsr SweepHalf
.endif
    rep #$20
.a16
    inc AHALFCLOCKS
    sep #$20
.a8
    ldx #$0000
@loop:
    lda ALENGTH,x
    beq @next
    lda f:$7E4000,x
    cpx #$0008
    beq @triangle
    and #$20
    bra @halt
@triangle:
    and #$80
@halt:
    bne @next
    dec ALENGTH,x
@next:
    inx
    inx
    inx
    inx
    cpx #$0010
    bne @loop
    rts

ApuQuarter:
.a8
.i16
    rep #$20
.a16
    inc AQUARTERCLOCKS
    sep #$20
.a8
    ldx #$0000
@envelope:
    lda ARESTART,x
    beq @divider
    stz ARESTART,x
    lda #$0F
    sta ADECAY,x
    lda f:$7E4000,x
    and #$0F
    sta ADIVIDER,x
    bra @next
@divider:
    lda ADIVIDER,x
    beq @decay
    dec ADIVIDER,x
    bra @next
@decay:
    lda f:$7E4000,x
    and #$0F
    sta ADIVIDER,x
    lda ADECAY,x
    bne @decrement
    lda f:$7E4000,x
    and #$20
    beq @next
    lda #$0F
    sta ADECAY,x
    bra @next
@decrement:
    dec ADECAY,x
@next:
    cpx #$000C
    beq @triangle
    cpx #$0000
    beq :+
    ldx #$000C
    bra @envelope
:
    ldx #$0004
    bra @envelope
@triangle:
    lda ALINRELOAD
    beq @count
    lda f:$7E4008
    and #$7F
    sta ALINEAR
    bra @reload
@count:
    lda ALINEAR
    beq @reload
    dec ALINEAR
@reload:
    lda f:$7E4008
    bmi :+
    stz ALINRELOAD
:
    rts

; Return unscaled 0..15 volume for pulse 0/4 or noise 12.
ApuGetVolume:
.a8
.i16
    lda ALENGTH,x
    beq @silent
    lda f:$7E4000,x
    and #$10
    beq @envelope
    lda f:$7E4000,x
    and #$0F
    rts
@envelope:
    lda ADECAY,x
    rts
@silent:
    lda #$00
    rts

.segment "RODATA"
ApuEnableMask:
    .byte 1,0,0,0,2,0,0,0,4,0,0,0,8,0,0,0
ApuLengthTable:
    .byte 10,254,20,2,40,4,80,6,160,8,60,10,14,12,26,14
    .byte 12,16,24,18,48,20,96,22,192,24,72,26,16,28,32,30
.segment "CODE"
.endif

.include "native_sweep.inc"
