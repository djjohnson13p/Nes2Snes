; Nonzero OAMADDR copy. The common zero-offset path stays unrolled in native.s.
; Contract: initialized ordinary internal RAM or the existing mapped ROM pages;
; forced blanking. Rendering-time corruption and I/O-source DMA are not modeled.
; Copy immediately and wrap the destination after each byte. A full transfer
; leaves OADDR unchanged and drives the I/O latch with the final source byte.
; Host dispatcher already saved the guest register and flag context.
OamDmaOffset:
    sep #$20
.a8
    lda VAL
    sta $0821
    stz $0820
    lda RAWBANK
    sta $0822
    lda VAL
    cmp #$20
    bcs @sourceReady
    and #$07
    sta $0821
    lda #$7E
    sta $0822
@sourceReady:
    rep #$10
.i16
    ldy #$0000
@copy:
    rep #$20
.a16
    lda OADDR
    and #$00FF
    tax
    sep #$20
.a8
    lda [PTR],y
    sta f:$7E3800,x
    sta PPUBUS
    inc OADDR
    iny
    cpy #$0100
    bne @copy
    rts
