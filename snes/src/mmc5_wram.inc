; 32-KiB single-chip PRG RAM at $7E:8000..FFFF. Experimental profile only.
; CW_LOCK/PAGE and pointer/address temporaries are inside the host-NMI snapshot.
; A protected write executes its arithmetic/flags and retires but discards the
; memory write. ROM writes, absent-chip mapping and unadmitted I/O still fault.
.segment "CODE"
.proc CartridgeInit
    rep #$10
.i16
    sep #$20
.a8
    stz CW_LOCK
    stz CW_PAGE
    stz CW_KIND
    .repeat 4, bank
        ldx #0
        lda #$41+bank
:
        sta f:$7E8000+bank*$2000,x
        inx
        cpx #$2000
        bne :-
    .endrepeat
    rts
.endproc

; A16 logical PRG-RAM address; typed physical bank is MB_BANK.
.proc CartridgePointer
.a16
.i16
    and #$1FFF
    ora #$8000
    sta MPTR
    lda MB_BANK
    and #3
    xba
    asl a
    asl a
    asl a
    asl a
    asl a
    ora MPTR
    sta MPTR
    sep #$20
.a8
    lda #$7E
    sta MPTR+2
    rts
.endproc

.proc CartridgeCommit
.a8
.i8
    rep #$10
.i16
    lda CW_KIND
    bne cartridge
    ldx MR_ADDR
    lda MR_VALUE
    sta $0000,x
    rts
cartridge:
    lda CW_LOCK
    cmp #6
    bne locked
    phd
    rep #$20
.a16
    lda #MPTR
    tcd
    sep #$20
.a8
    lda MR_VALUE
    sta [$00]
    pld
locked:
    rts
.endproc

.proc TimelineResolveMMC5
    rep #$30
.a16
.i16
    stz CW_KIND-1 ; MR_VALUE/CW_KIND, scratch only, not a guest write.
    lda MR_MODE
    and #$FF
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
    and #$FF
    jmp mapped
zpx:
    lda GC_INPUT+2
    bra zp_index
zpy:
    lda GC_INPUT+3
zp_index:
    and #$FF
    clc
    adc GC_INPUT+4
    and #$FF
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
    and #$FF
    sta MR_INDEX
    lda GC_INPUT+4
    bra indexed
indirect_x:
    lda GC_INPUT+2
    and #$FF
    clc
    adc GC_INPUT+4
    and #$FF
    jsr pointer
    jmp check
indirect_y:
    lda GC_INPUT+4
    and #$FF
    jsr pointer
    sta GC_INPUT+8
    sep #$20
.a8
    lda #1
    sta GC_INPUT+10
    rep #$20
.a16
    lda GC_INPUT+3
    and #$FF
    sta MR_INDEX
    lda MR_BASE
indexed:
    ; Preserve the previous profile's preliminary-region refusal. This is not
    ; a reproduction of dummy bus accesses or mapper snooping during them.
    sta MR_BASE
    cmp #$2000
    bcc add_index
    cmp #$6000
    bcs :+
    jmp outside
:
    jsr MapperBank
    lda GT+14
    beq :+
    jmp outside
:
    rep #$20
.a16
    lda MR_BASE
add_index:
    clc
    adc MR_INDEX
check:
    cmp #$2000
    bcc mapped
    cmp #$6000
    bcs :+
    jmp outside
:
    sta MR_ADDR
    jsr MapperBank
    sta MB_BANK
    lda GT+14
    beq :+
    jmp outside
:
    lda MB_BANK
    bmi cartridge
    lda MR_WRITE
    beq :+
    jmp outside
:
    rep #$20
.a16
    lda MR_ADDR
    jsr MapperRead
.a8
    bra value
cartridge:
    lda #1
    sta CW_KIND
    rep #$20
.a16
    lda MR_ADDR
    jsr CartridgePointer
    phd
    rep #$20
.a16
    lda #MPTR
    tcd
    sep #$20
.a8
    lda [$00]
    pld
value:
    sta MR_VALUE
    rep #$30
.a16
.i16
    rts
mapped:
    and #$07FF
    sta MR_ADDR
    tax
    sep #$20
.a8
    lda $0000,x
    bra value
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
    tax
    sep #$20
.a8
    lda $0000,x
    sta MR_BASE
    rep #$20
.a16
    txa
    inc a
    and #$FF
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
