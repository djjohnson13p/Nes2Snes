; Optional four-voice approximation using our original SPC700 receiver.
; Optional frame-quantized envelopes/lengths live in native_apu.inc; no DMC or sweep.
.if USE_EXPERIMENTAL_AUDIO
ACACHE = $0A00
AREADY = $0A80
ATOKEN = $0A81
AFAULT = $0A82
ACOUNT = $0A84
AVOICE = $0A88
AVOL   = $0A8A
APITCH = $0A8C
ASOURCE= $0A8E
ATIMER = $0A90
APUBASE= $0A92

.a8
.i16
AudioWait:
    ; A=expected echo, X preserved. Carry set on bounded timeout.
    ldy #$FFFF
@wait:
    cmp $2140
    beq @ok
    dey
    bne @wait
    lda #$01
    sta AFAULT
    stz AREADY
    sec
    rts
@ok:
    clc
    rts
AudioInitialize:
    lda #$AA
    jsr AudioWait
    jcs @done
    lda $2141
    cmp #$BB
    jne @error
    lda #$01
    sta $2141
    ldx #$0400
    stx $2142
    lda #$CC
    sta $2140
    jsr AudioWait
    jcs @done
    ldx #$0000
@send:
    lda f:AudioProgram+$800000,x
    sta $2141
    txa
    sta $2140
    jsr AudioWait
    jcs @done
    inx
    cpx #(AudioProgramEnd-AudioProgram)
    bne @send
    stz $2141
    ldx #$0400
    stx $2142
    lda #<((AudioProgramEnd-AudioProgram)+1)
    bne :+
    inc a
:
    sta ATOKEN
    sta $2140
    lda #$7F
    jsr AudioWait
    bcs @done
    ldx #$007F
    lda #$FF
@cache:
    sta ACACHE,x
    dex
    bpl @cache
    lda #$01
    sta AREADY
@done:
    rts
@error:
    lda #$02
    sta AFAULT
    rts
AudioWrite:
    ; A=value, X=DSP register; caller allows A/Y/flags to change.
    cmp ACACHE,x
    beq @done
    sta AVOL+1
    lda AREADY
    beq @done
    lda AVOL+1
    sta ACACHE,x
    sta $2142
    txa
    sta $2141
    inc ATOKEN
    lda ATOKEN
    sta $2140
    jsr AudioWait
    bcs @done
    rep #$20
.a16
    inc ACOUNT
    sep #$20
.a8
@done:
    rts
AudioFrame:
    lda AREADY
    jne @run
    rts
@run:
    stz AVOICE
    stz AVOICE+1
    stz APUBASE
    stz APUBASE+1
@pulse:
    ldx APUBASE
    lda f:$7E4000,x
    pha
.if USE_AUDIO_COUNTERS
    jsr ApuGetVolume
.else
    and #$0F
.endif
    asl a
    sta AVOL
    asl a
    clc
    adc AVOL
    sta AVOL
    pla
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    sta ASOURCE
.if USE_AUDIO_SWEEP
    rep #$20
.a16
    lda SWPERIOD,x
    sta ATIMER
    sep #$20
.a8
    jsr SweepMuted
    beq :+
    stz AVOL
:
.else
    lda f:$7E4003,x
    and #$07
    sta ATIMER+1
    lda f:$7E4002,x
    sta ATIMER
.endif
    lda AVOICE
    beq @first
    lda f:$7E4015
    and #$02
    bra @enabled
@first:
    lda f:$7E4015
    and #$01
@enabled:
    bne @timer
    stz AVOL
@timer:
    rep #$20
.a16
    lda ATIMER
    cmp #$0008
    bcs @pitch
    sep #$20
.a8
    stz AVOL
    rep #$20
.a16
    lda ATIMER
@pitch:
    asl a
    tax
    lda f:PulsePitch+$800000,x
    sta APITCH
    sep #$20
.a8
    jsr AudioVoice
    lda AVOICE
    bne @triangle
    lda #$10
    sta AVOICE
    lda #$04
    sta APUBASE
    jmp @pulse
@triangle:
    lda #$20
    sta AVOICE
    lda #$04
    sta ASOURCE
    lda #$42
    sta AVOL
    lda f:$7E4015
    and #$04
    beq @trioff
.if USE_AUDIO_COUNTERS
    lda ALENGTH+8
    beq @trioff
    lda ALINEAR
.else
    lda f:$7E4008
    and #$7F
.endif
    bne @tritimer
@trioff:
    stz AVOL
@tritimer:
    lda f:$7E400B
    and #$07
    sta ATIMER+1
    lda f:$7E400A
    sta ATIMER
    rep #$20
.a16
    lda ATIMER
    asl a
    tax
    lda f:TrianglePitch+$800000,x
    sta APITCH
    sep #$20
.a8
    jsr AudioVoice
    ; Noise uses voice 3 and the DSP's global noise generator.
.if USE_AUDIO_COUNTERS
    ldx #$000C
    jsr ApuGetVolume
.else
    lda f:$7E400C
    and #$0F
.endif
    asl a
    asl a
    sta AVOL
    lda f:$7E4015
    and #$08
    bne @noise
    stz AVOL
@noise:
    ldx #$0030
    lda AVOL
    jsr AudioWrite
    ldx #$0031
    lda AVOL
    jsr AudioWrite
    lda f:$7E400E
    and #$0F
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:NoiseClock+$800000,x
    ora #$20
    ldx #$006C
    jsr AudioWrite
.if USE_AUDIO_COUNTERS
    rep #$20
.a16
    lda AUPDATES
    sta AOUTPUTFRAMES
    sep #$20
.a8
.endif
    rts
AudioVoice:
    ; AVOICE contains 0,$10,$20. AVOL/APITCH/ASOURCE describe that voice.
    ldx AVOICE
    lda AVOL
    jsr AudioWrite
    inx
    lda AVOL
    jsr AudioWrite
    inx
    lda APITCH
    jsr AudioWrite
    inx
    lda APITCH+1
    jsr AudioWrite
    inx
    lda ASOURCE
    jsr AudioWrite
    rts
.segment "RODATA"
AudioProgram: .incbin "audio-spc.bin"
AudioProgramEnd:
PulsePitch: .incbin "pulse-pitch.bin"
TrianglePitch: .incbin "triangle-pitch.bin"
; Approximate NTSC NES noise periods mapped to nearest DSP clock.
NoiseClock: .byte 31,31,31,31,31,30,29,28,27,26,25,23,22,21,19,17
.segment "CODE"
.endif
