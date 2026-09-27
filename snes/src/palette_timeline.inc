; Blanked palette transfers on the experimental timeline, not native.s.
; Palette storage is separate guest memory; all scratch is already protected.
; Entry uses dispatcher D=DBR=0. No live-v substitution for the shadow read.
PL_RAM=$7E5800
.segment "CODE"
.proc PaletteInit
    rep #$30
.a16
.i16
    ldx #31
    sep #$20
.a8
    lda #0
clear:
    sta f:PL_RAM,x
    dex
    bpl clear
    rep #$30
.a16
.i16
    rts
.endproc

; Resolve canonical palette storage: every fourth sprite entry aliases its
; corresponding background entry, not all four backdrop entries together.
.proc PaletteIndex
    rep #$30
.a16
.i16
    lda PV+6
    and #$001F
    tax
    and #3
    bne selected
    txa
    and #$000F
    tax
selected:
    sep #$20
.a8
    rts
.endproc

; Underlying address is $2F00 | (v & $FF); quadrant 3 is always selected.
; This routine never changes v, t, w, fine-X or the I/O latch.
.proc PaletteShadow
    rep #$30
.a16
.i16
    lda PV+6
    and #$00FF
    ora #$0300
    sta PV+14
    sep #$20
.a8
    lda PV+10
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    cmp #2
    bne :+
    jmp PpuUnsupported
:
    cmp #3
    beq fill
    cmp #1
    bne memory
    lda PV+15
    ora #4
    sta PV+15
memory:
    ldx PV+14
    lda f:$7E4800,x
    rts
fill:
    lda PV+14
    cmp #$C0
    bcs attribute
    lda PV+11
    rts
attribute:
    lda PV+12
    sta PV+13
    asl a
    asl a
    ora PV+13
    sta PV+13
    asl a
    asl a
    asl a
    asl a
    ora PV+13
    rts
.endproc

.proc PaletteDataRead
    rep #$30
.a16
.i16
    lda PV+6
    and #$3FFF
    cmp #$3F00
    bcs palette
    jmp PpuDataRead
palette:
    jsr PaletteShadow
.a8
    sta PV+8
    jsr PaletteIndex
.a8
    lda f:PL_RAM,x
    sta PV+13
    lda PV+1
    and #1
    beq full_color
    lda PV+13
    and #$30
    sta PV+13
full_color:
    lda PV+9
    and #$C0
    ora PV+13
    sta PV+9
    sta MR_VALUE
    jsr PpuIncrement
.a8
    lda MR_VALUE
    rts
.endproc

.proc PaletteDataWrite
    rep #$30
.a16
.i16
    lda PV+6
    and #$3FFF
    cmp #$3F00
    bcs palette
    jmp PpuDataWrite
palette:
    jsr PaletteIndex
.a8
    lda GT+6
    and #$3F
    sta f:PL_RAM,x
    txa
    and #3
    bne finish
    lda GT+6
    and #$3F
    sta f:PL_RAM+16,x
finish:
    lda GT+6
    sta PV+9
    jsr PpuIncrement
    rts
.endproc
