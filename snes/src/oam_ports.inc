; Blanked OAM CPU ports for the explicit test profile; not linked by native.s.
; OA reuses the former CHR temporary, within the existing host-NMI snapshot.
; OAM is guest memory, not host callback scratch. No rendering/DMA/decay model.
OA=$1C3B
.segment "CODE"
.proc OamInit
    rep #$30
.a16
.i16
    ldx #0
    sep #$20
.a8
    stz OA
    lda #0
clear:
    sta f:$7E5900,x
    inx
    cpx #256
    bne clear
    rep #$30
.a16
.i16
    rts
.endproc
.proc OamAddressWrite
    sep #$20
.a8
    lda GT+6
    sta OA
    sta PV+9
    rts
.endproc
.proc OamDataRead
    rep #$30
.a16
.i16
    lda OA
    and #$00FF
    tax
    sep #$20
.a8
    lda f:$7E5900,x
    sta PV+9
    rts
.endproc
.proc OamDataWrite
    rep #$30
.a16
.i16
    lda OA
    and #$00FF
    tax
    sep #$20
.a8
    lda GT+6
    sta PV+9
    txa
    and #3
    cmp #2
    bne ordinary
    lda GT+6
    and #$E3
    bra store
ordinary:
    lda GT+6
store:
    sta f:$7E5900,x
    inc OA
    rts
.endproc
.proc OamCapture
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
    sep #$20
.a8
    lda OA
    sta f:$7E500D,x
    rts
.endproc
