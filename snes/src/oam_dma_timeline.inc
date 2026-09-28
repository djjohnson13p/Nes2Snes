; Explicit RAM-only DMA adapter, not production native.s.
; Time zero is GET phase established by the original boot's synchronizing DMA.
; All original instructions remain in the guest clock; DMA adds only its stall.
; No DMC, rendering, external bus targets or guest interrupt requests admitted.
; Guest DMA metadata is outside host callback storage; MR/GT/PV are protected.
OD_COUNT=$7E5B00
OD_LAST=$7E5B02
OD_TOTAL=$7E5B04
.segment "CODE"
.proc OamDmaInit
    rep #$30
.a16
.i16
    lda #0
    sta f:OD_COUNT
    sta f:OD_LAST
    sta f:OD_TOTAL
    sta f:OD_TOTAL+2
    rts
.endproc
.proc OamDmaRun
    rep #$30
.a16
.i16
    lda GT+6
    and #$00FF
    cmp #$0020
    bcc supported
    jmp PpuUnsupported
supported:
    pha
    lda OA
    and #3
    cmp #3
    bne address_ok
    pla
    jmp PpuUnsupported
address_ok:
    pla
    and #7
    xba
    sta MR_BASE
    ; Absolute STA writes on the fourth cycle. A PUT write needs alignment.
    lda GT
    and #1
    eor #1
    clc
    adc #513
    sta MR_INDEX
    ; Reserve the existing retire helper's 14-cycle overflow envelope BEFORE
    ; any target write. This adapter does not let a copied prefix pass as complete.
    clc
    adc GT
    bcc clock_ok
    lda GT+2
    cmp #$FFFF
    beq overflow
    bra clock_ok
clock_ok:
    lda GT+2
    cmp #$FFFF
    bne transfer
    lda GT
    clc
    adc MR_INDEX
    cmp #$FFF2
    bcc transfer
overflow:
    sep #$20
.a8
    lda #4
    sta GT+14
    jmp fault
.a16
transfer:
    ldy #0
copy:
    tya
    clc
    adc MR_BASE
    tax
    sep #$20
.a8
    lda $0000,x
    sta MR_VALUE
    rep #$20
.a16
    lda OA
    and #$00FF
    tax
    sep #$20
.a8
    lda MR_VALUE
    sta PV+9
    txa
    and #3
    cmp #2
    bne ordinary
    lda MR_VALUE
    and #$E3
    bra store
ordinary:
    lda MR_VALUE
store:
    sta f:$7E5900,x
    inc OA
    rep #$20
.a16
    iny
    cpy #256
    bne copy
    lda MR_INDEX
    sta f:OD_LAST
    clc
    adc GT
    sta GT
    bcc :+
    inc GT+2
:
    lda f:OD_TOTAL
    clc
    adc MR_INDEX
    sta f:OD_TOTAL
    bcc :+
    lda f:OD_TOTAL+2
    inc a
    sta f:OD_TOTAL+2
:
    lda f:OD_COUNT
    inc a
    sta f:OD_COUNT
    rts
.endproc
.proc OamDmaCapture
    rep #$30
.a16
.i16
    lda GT+16
    dec a
    asl a
    asl a
    asl a
    tax
    lda f:OD_COUNT
    sta f:$7E6000,x
    lda f:OD_LAST
    sta f:$7E6002,x
    lda f:OD_TOTAL
    sta f:$7E6004,x
    lda f:OD_TOTAL+2
    sta f:$7E6006,x
    sep #$20
.a8
    rts
.endproc
