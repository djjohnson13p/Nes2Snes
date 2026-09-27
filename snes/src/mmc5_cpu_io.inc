; CPU-only ExRAM + multiplier, inside the explicit MMC5 I/O prototype profile.
; ExRAM $7E:4000..43FF is guest memory, disjoint from PRG RAM and host scratch.
; EX_MODE/MUL/PRODUCT occupy GT+24..29, protected across host NMIs.
; Caller: native dispatcher with D=DBR=0. No standalone preservation ABI.
.segment "CODE"
.proc ExInit
    rep #$10
.i16
    sep #$20
.a8
    lda #3
    sta EX_MODE
    stz EX_MUL
    stz EX_MUL+1
    stz EX_PRODUCT
    stz EX_PRODUCT+1
    ldx #0
    lda #$A5
fill:
    sta f:$7E4000,x
    inx
    cpx #1024
    bne fill
    rts
.endproc

; Read-only snapshot operand fetch. A16 is a validated $5C00..$5FFF address.
; Returns A8; CW_KIND=2 selects ExRAM writeback, not PRG RAM.
; The operand resolver stores MR_VALUE; pointer reads must not overwrite it.
.proc ExRead
.a16
.i16
    and #$03FF
    tax
    sta MR_ADDR
    sep #$20
.a8
    lda #2
    sta CW_KIND
    lda f:$7E4000,x
    rts
.endproc

.proc ExCommit
.a8
.i16
    lda EX_MODE
    cmp #2
    bne locked
    ldx MR_ADDR
    lda MR_VALUE
    sta f:$7E4000,x
locked:
    rts
.endproc

; Recompute the unsigned 8x8 product from persistent operands, without using
; shared SNES hardware-multiply registers or injecting expected result bytes.
; Binary 16-bit host arithmetic irrespective of the NES guest decimal flag.
.proc ExMultiply
    cld
    rep #$30
.a16
.i16
    lda EX_MUL
    and #$FF
    sta MR_BASE
    lda EX_MUL+1
    and #$FF
    sta MR_INDEX
    stz EX_PRODUCT
    ldx #8
multiply_loop:
    lsr MR_INDEX
    bcc skip
    lda EX_PRODUCT
    clc
    adc MR_BASE
    sta EX_PRODUCT
skip:
    asl MR_BASE
    dex
    bne multiply_loop
    rts
.endproc
