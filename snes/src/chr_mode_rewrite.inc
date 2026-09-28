; Blanked MMC5 size transitions, with rewrite-before-read provenance.
; CL_MODE and CL_VALID are guest mapper/policy memory, NOT host scratch.
; Raw A/B register values have defined interpretation only after rewriting in
; the active mode. Mode changes conservatively invalidate all twelve registers.
; This avoids claiming unknown low hardware latch bits from stale registers.
CL_MODE=$7E5A09
CL_VALID=$7E5A0A
.segment "CODE"
.proc ChrLiveInit
    rep #$30
.a16
.i16
    lda #$0FFF
    sta f:CL_VALID
    sep #$20
.a8
    lda #ChrMode
    sta f:CL_MODE
    rep #$30
.a16
.i16
    rts
.endproc
.proc ChrModeWrite
    sep #$20
.a8
    lda GT+6
    and #3
    cmp f:CL_MODE
    beq done
    sta f:CL_MODE
    rep #$20
.a16
    lda #0
    sta f:CL_VALID
    sep #$20
.a8
done:
    rts
.endproc

; Require every active register of the selected set to have been written in
; the current mode before pattern reads/writes. Nametable/palette operations
; remain independent. Failure occurs before latch/address/guest-memory mutation.
.proc ChrLiveReadCheck
    rep #$30
.a16
.i16
    lda f:CL_MODE
    and #$00FF
    asl a
    tax
    lda f:CS_LAST
    and #$00FF
    beq set_a
    lda f:CL_REQUIRED_B,x
    bra check
set_a:
    lda f:CL_REQUIRED_A,x
check:
    sta MR_INDEX
    and f:CL_VALID
    cmp MR_INDEX
    beq done
    jmp PpuUnsupported
done:
    rts
.endproc

; X16=pattern slot, result A16=physical bank or $FFFF for stale metadata.
; Snapshotting a stale mapping does not authorize its execution.
.proc ChrBank
    rep #$30
.a16
.i16
    txa
    sta MR_ADDR
    lda f:CL_MODE
    and #$00FF
    asl a
    tax
    lda MR_ADDR
    ora f:CL_GROUP,x
    sta MR_WRITE
    lda f:CS_LAST
    and #$00FF
    beq set_a
    lda MR_WRITE
    and #3
    ora #8
    sta MR_WRITE
set_a:
    lda MR_WRITE
    asl a
    tax
    lda f:CL_BITS,x
    and f:CL_VALID
    bne known
    lda #$FFFF
    rts
known:
    lda MR_WRITE
    cmp #8
    bcc read_a
    and #3
    asl a
    tax
    lda f:CS_B,x
    sta MR_INDEX
    bra scale
read_a:
    tax
    sep #$20
.a8
    lda CR,x
    sta MR_INDEX
    rep #$20
.a16
    txa
    and #3
    asl a
    tay
    txa
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda CR+8,x
unpack:
    cpy #0
    beq high
    lsr a
    dey
    bra unpack
high:
    and #3
    sta MR_INDEX+1
    rep #$20
.a16
scale:
    lda #3
    sec
    sbc f:CL_MODE
    and #$00FF
    tay
    lda MR_INDEX
shift:
    cpy #0
    beq offset
    asl a
    dey
    bra shift
offset:
    sta MR_INDEX
    lda f:CL_MODE
    and #$00FF
    asl a
    tax
    lda MR_ADDR
    and f:CL_GROUP,x
    clc
    adc MR_INDEX
    and #ChrMask
    rts
.endproc

.proc ChrLiveCapture
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
    lda f:CL_MODE
    sta f:$7E522B,x
    lda f:CL_VALID
    sta f:$7E522C,x
    lda f:CL_VALID+1
    sta f:$7E522D,x
    rts
.endproc
CL_GROUP: .word 7,3,1,0
CL_REQUIRED_A: .word $0080,$0088,$00AA,$00FF
CL_REQUIRED_B: .word $0800,$0800,$0A00,$0F00
CL_BITS: .word $0001,$0002,$0004,$0008,$0010,$0020,$0040,$0080,$0100,$0200,$0400,$0800
