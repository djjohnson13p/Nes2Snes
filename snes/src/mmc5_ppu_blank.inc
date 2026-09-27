; Blanked PPU nametable access in the experimental timeline, NOT native.s.
; PV = CTRL,MASK,w,x,t.u16,v.u16,buffer,latch,NTmap,fill,attr,value,addr.u16.
; All PV bytes are protected by the extended host capture-area stack snapshot.
; CIRAM $7E:4800..4FFF and per-boundary state log $7E:5000..51FF are guest data.
; No rendering, CHR/palette/OAM access, NMI enable, or status timing is implied.
; Entry uses dispatcher D=DBR=0. Helpers may clobber A/X/Y/P; guest state is in GT.
PV=$1C20
.segment "CODE"
.proc PpuInit
    rep #$30
.a16
.i16
    ldx #0
    sep #$20
.a8
clear:
    stz PV,x
    inx
    cpx #16
    bne clear
    ldx #0
fill:
    lda #$3C
    sta f:$7E4800,x
    lda #$C3
    sta f:$7E4C00,x
    inx
    cpx #1024
    bne fill
    lda #$20
    sta PV+5
    sta PV+7
    lda #1
    sta PV+6
    lda #$3C
    sta PV+8
    lda #$44
    sta PV+10
    lda #$11
    sta PV+11
    lda #2
    sta PV+12
    rep #$30
.a16
.i16
    rts
.endproc

.proc PpuUnsupported
    sep #$20
.a8
    lda #5
    sta GT+14
    jmp fault
.endproc

.proc PpuControl
    sep #$20
.a8
    lda GT+6
    and #$C0
    beq :+
    jmp PpuUnsupported
:
    lda GT+6
    sta PV
    sta PV+9
    and #3
    asl a
    asl a
    sta PV+13
    lda PV+5
    and #$F3
    ora PV+13
    sta PV+5
    rts
.endproc
.proc PpuMask
    sep #$20
.a8
    lda GT+6
    and #$18
    beq :+
    jmp PpuUnsupported
:
    lda GT+6
    sta PV+1
    sta PV+9
    rts
.endproc
.proc PpuLatchRead
    sep #$20
.a8
    lda PV+9
    rts
.endproc
.proc PpuLatchWrite
    sep #$20
.a8
    lda GT+6
    sta PV+9
    rts
.endproc
.proc PpuScroll
    sep #$20
.a8
    lda GT+6
    sta PV+9
    lda PV+2
    bne vertical
    lda GT+6
    and #7
    sta PV+3
    lda GT+6
    lsr a
    lsr a
    lsr a
    sta PV+13
    lda PV+4
    and #$E0
    ora PV+13
    sta PV+4
    bra toggle
vertical:
    rep #$20
.a16
    lda GT+6
    and #$00F8
    asl a
    asl a
    sta PV+14
    lda PV+4
    and #$0C1F
    ora PV+14
    sta PV+4
    sep #$20
.a8
    lda GT+6
    and #7
    asl a
    asl a
    asl a
    asl a
    ora PV+5
    sta PV+5
toggle:
    lda PV+2
    eor #1
    sta PV+2
    rts
.endproc
.proc PpuAddress
    sep #$20
.a8
    lda GT+6
    sta PV+9
    lda PV+2
    bne low
    lda GT+6
    and #$3F
    sta PV+5
    bra toggle
low:
    lda GT+6
    sta PV+4
    rep #$20
.a16
    lda PV+4
    sta PV+6
    sep #$20
.a8
toggle:
    lda PV+2
    eor #1
    sta PV+2
    rts
.endproc
.proc PpuMap
    sep #$20
.a8
    lda GT+6
    sta PV+13
    ldx #4
check:
    lda PV+13
    and #3
    cmp #2
    bne :+
    jmp PpuUnsupported
:
    lsr PV+13
    lsr PV+13
    dex
    bne check
    lda GT+6
    sta PV+10
    rts
.endproc
.proc PpuFillTile
    sep #$20
.a8
    lda GT+6
    sta PV+11
    rts
.endproc
.proc PpuFillAttr
    sep #$20
.a8
    lda GT+6
    cmp #4
    bcc :+
    ; Pinned FCEUmm does not mask upper bits; do not adopt its discrepancy.
    jmp PpuUnsupported
:
    sta PV+12
    rts
.endproc

; Validate BEFORE buffer/latch/address or CIRAM mutation. Return addressed byte
; in A8 and resolved kind in MR_MODE. PV+14 contains a physical CIRAM offset.
.proc PpuResolve
    rep #$30
.a16
.i16
    lda PV+6
    and #$3FFF
    cmp #$2000
    bcc unsupported
    cmp #$3F00
    bcs unsupported
    pha
    and #$03FF
    sta PV+14
    pla
    xba
    and #$000C
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda PV+10
shift:
    cpx #0
    beq selected
    lsr a
    lsr a
    dex
    bra shift
selected:
    and #3
    sta MR_MODE
    cmp #2
    beq unsupported
    cmp #3
    beq fill
    cmp #1
    bne ciram
    lda PV+15
    ora #4
    sta PV+15
ciram:
    rep #$20
.a16
    ldx PV+14
    sep #$20
.a8
    lda f:$7E4800,x
    rts
fill:
    rep #$20
.a16
    lda PV+14
    cmp #$03C0
    sep #$20
.a8
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
unsupported:
    jmp PpuUnsupported
.endproc
.proc PpuIncrement
    rep #$30
.a16
.i16
    lda PV
    and #4
    beq one
    lda #32
    bra add
one:
    lda #1
add:
    clc
    adc PV+6
    and #$7FFF
    sta PV+6
    sep #$20
.a8
    rts
.endproc
.proc PpuDataRead
    jsr PpuResolve
.a8
    sta PV+13
    lda PV+8
    sta MR_VALUE
    sta PV+9
    lda PV+13
    sta PV+8
    jsr PpuIncrement
.a8
    lda MR_VALUE
    rts
.endproc
.proc PpuDataWrite
    jsr PpuResolve
.a8
    lda MR_MODE
    cmp #3
    beq ignored
    ldx PV+14
    lda GT+6
    sta f:$7E4800,x
ignored:
    lda GT+6
    sta PV+9
    jsr PpuIncrement
    rts
.endproc
.proc PpuCapture
    rep #$30
.a16
.i16
    lda GT+16
    dec a
    asl a
    asl a
    asl a
    asl a
    tax
    ldy #0
    sep #$20
.a8
copy:
    lda PV,y
    sta f:$7E5000,x
    inx
    iny
    cpy #13
    bne copy
    lda #0
pad:
    sta f:$7E5000,x
    inx
    iny
    cpy #16
    bne pad
    rts
.endproc
