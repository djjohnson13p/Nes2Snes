; MMC5 PRG-ROM-only prototype profile; not installed in native.s.
; All state/scratch $1852..$187F is inside the existing host-NMI envelope.
; Caller is the protected timeline dispatcher (D=DBR=0). No standalone ABI.
; Modes 1,2,3; PRG-RAM-selected slots are recorded as $FF and fault on access.
; MapperBankMask describes a power-of-two authored ROM with 4..128 8-KiB banks.
; No PPU, expansion audio, WRAM, mapper IRQ, dummy bus cycles or event timing.
MR_MODE=$1852
MR_BASE=$1854
MR_ADDR=$1856
MR_VALUE=$1858
MR_INDEX=$185A
MR_WRITE=$185C
MPTR=$185D
MB_REG=$1871
MB_SLOTS=$1878
MB_CURRENT=$187C
MB_BANK=$187D
MB_CHECK=$187E
.segment "CODE"
.proc MapperInit
    sep #$20
.a8
    lda #3
    sta MB_REG
    lda #$80
    sta MB_REG+1
    inc a
    sta MB_REG+2
    inc a
    sta MB_REG+3
    lda #$FF
    sta MB_REG+4
    jmp MapperRemap
.endproc

.proc MapperRemap
    rep #$10
.i16
    sep #$20
.a8
    lda MB_REG
    and #3
    cmp #1
    beq mode1
    cmp #2
    beq mode2
    ; Mode zero has already been rejected BEFORE the register write.
    lda MB_REG+1
    jsr one
    sta MB_SLOTS
    lda MB_REG+2
    jsr one
    sta MB_SLOTS+1
    lda MB_REG+3
    jsr one
    sta MB_SLOTS+2
    bra last
mode1:
    ldx #0
    lda MB_REG+2
    jsr pair
    ldx #2
    lda MB_REG+4
    ora #$80
    jsr pair
    rts
mode2:
    ldx #0
    lda MB_REG+2
    jsr pair
    lda MB_REG+3
    jsr one
    sta MB_SLOTS+2
last:
    lda MB_REG+4
    and #MapperBankMask
    sta MB_SLOTS+3
    rts
one:
    bmi rom
    lda #$FF
    rts
rom:
    and #MapperBankMask
    rts
pair:
    jsr one
    cmp #$FF
    bne :+
    sta MB_SLOTS,x
    sta MB_SLOTS+1,x
    rts
:
    and #$FE
    sta MB_SLOTS,x
    inc a
    sta MB_SLOTS+1,x
    rts
.endproc

; A16 guest cartridge address -> A8 physical bank or status=5, A8=$FF.
.proc MapperBank
.a16
.i16
    cmp #$8000
    bcc invalid
    and #$6000
    xba
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda MB_SLOTS,x
    cmp #$FF
    bne done
invalid:
    sep #$20
.a8
    lda #5
    sta GT+14
    lda #$FF
done:
    rts
.endproc

; Read A16 mapped address into A8. Uses a protected direct-page long pointer;
; never borrows original guest zero page. Restores D=0 after the raw ROM read.
.proc MapperRead
.a16
.i16
    sta MB_CHECK
    cmp #$2000
    bcc ram
    jsr MapperBank
    sta MB_BANK
    lda GT+14
    beq :+
    rts
:
    rep #$20
.a16
    lda MB_CHECK
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
    lda MB_BANK
    lsr a
    lsr a
    inc a
    sta MPTR+2
    phd
    rep #$20
.a16
    lda #MPTR
    tcd
    sep #$20
.a8
    lda [$00]
    pld
    rts
.a16
ram:
    and #$07FF
    tax
    sep #$20
.a8
    lda $0000,x
    rts
.endproc

.proc TimelineResolveMMC5
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
    ; Validate the preliminary region before computing the wrapped final one.
    sta MR_BASE
    cmp #$2000
    bcc add_index
    cmp #$8000
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
    cmp #$8000
    bcs :+
    jmp outside
:
    sta MR_ADDR
    sep #$20
.a8
    lda MR_WRITE
    beq :+
    jmp outside
:
    rep #$20
.a16
    lda MR_ADDR
    jsr MapperRead
.a8
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
