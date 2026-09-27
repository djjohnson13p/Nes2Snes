; Guarded internal RAM for the experimental composed timeline, not native.s.
; GC contains ORIGINAL opcode/operand/pre-X/pre-Y. Resolves all guest mirrors
; before access. Both base/preliminary and final addresses must be internal RAM.
; $1852..$185D are inside the existing host-NMI snapshot. Guest RAM is $0000..$07FF.
; Failure: GT.status=5, no target access, guest mutation or clock retirement.
; Caller is the native dispatcher with D=DBR=0; no preservation ABI is implied.
; Current request policy has no within-instruction events or mapper bus snooping.
MR_MODE=$1852
MR_BASE=$1854
MR_ADDR=$1856
MR_VALUE=$1858
MR_INDEX=$185A
.segment "CODE"
.proc TimelineResolveRAM
    rep #$30
.a16
.i16
    lda MR_MODE
    and #$00FF
    cmp #1
    beq zp
    cmp #2
    beq zpx
    cmp #3
    beq zpy
    cmp #4
    beq absolute
    cmp #5
    beq absolute_x
    cmp #6
    beq absolute_y
    cmp #7
    beq indirect_x
    cmp #8
    beq indirect_y
    jmp outside
zp:
    lda GC_INPUT+4
    and #$00FF
    jmp mapped
zpx:
    lda GC_INPUT+2
    bra zp_index
zpy:
    lda GC_INPUT+3
zp_index:
    and #$00FF
    clc
    adc GC_INPUT+4
    and #$00FF
    jmp mapped
absolute:
    lda GC_INPUT+4
    jmp check
absolute_x:
    lda GC_INPUT+2
    bra absolute_index
absolute_y:
    lda GC_INPUT+3
absolute_index:
    and #$00FF
    sta MR_INDEX
    lda GC_INPUT+4
    bra indexed
indirect_x:
    lda GC_INPUT+2
    and #$00FF
    clc
    adc GC_INPUT+4
    and #$00FF
    jsr pointer
    jmp check
indirect_y:
    lda GC_INPUT+4
    and #$00FF
    jsr pointer
    sta GC_INPUT+8
    sep #$20
.a8
    lda #1
    sta GC_INPUT+10
    rep #$20
.a16
    lda GC_INPUT+3
    and #$00FF
    sta MR_INDEX
    lda MR_BASE
indexed:
    ; A wrapped final RAM address must not conceal a preliminary ROM/I/O read.
    cmp #$2000
    bcs outside
    clc
    adc MR_INDEX
check:
    cmp #$2000
    bcs outside
mapped:
    and #$07FF
    sta MR_ADDR
    tax
    sep #$20
.a8
    lda $0000,x
    sta MR_VALUE
    rep #$30
.a16
.i16
    rts
outside:
    sep #$20
.a8
    lda #5
    sta GT+14
    rep #$30
.a16
.i16
    rts
pointer:
    ; Zero-page pointer high-byte fetch wraps independently of native D/X rules.
    tax
    sep #$20
.a8
    lda $0000,x
    sta MR_BASE
    rep #$20
.a16
    txa
    inc a
    and #$00FF
    tax
    sep #$20
.a8
    lda $0000,x
    sta MR_BASE+1
    rep #$20
.a16
    lda MR_BASE
    rts
.endproc
