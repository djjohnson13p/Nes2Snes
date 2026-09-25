; Native SNES CHR viewer. Not a game port or NES emulator.
; Build-time assets are generated from a locally supplied ROM (or synthetic CHR).
.setcpu "65816"
.include "config.inc"

PAGE       = $00
OLD_HI     = $01
OLD_LO     = $02
EDGE_HI    = $03
EDGE_LO    = $04
PALETTE    = $05
DIRTY      = $06
TMP        = $07
FRAME      = $08

.segment "CODE"
.a8
.i8
Reset:
    sei
    cld
    clc
    xce
    rep #$30
.a16
.i16
    ldx #$1FFF
    txs
    lda #$0000
    tcd
    sep #$20
.a8
    phk
    plb
    lda #$80
    sta $2100             ; forced blank throughout initialization
    stz $4200             ; NMI, IRQ and auto joy initially disabled
    stz $420B
    stz $420C
    stz $420D             ; SlowROM
    ldx #$0033
ClearPpu:
    stz $2100,x           ; $2101-$2133 only: leave INIDISP forced blank
    dex
    bne ClearPpu
    ldx #$000F
ClearVariables:
    stz $0000,x
    dex
    bpl ClearVariables
    ; Clear VRAM with a fixed zero byte, alternating the low/high VRAM ports.
    lda #$80
    sta $2115
    stz $2116
    stz $2117
    lda #$09
    sta $4300
    lda #$18
    sta $4301
    ldx #.loword(Zero)
    stx $4302
    stz $4304
    stz $4305
    stz $4306             ; DMA length zero means 65536 bytes
    lda #$01
    sta $420B
    ; Clear all 256 CGRAM entries.
    stz $2121
    lda #$08
    sta $4300
    lda #$22
    sta $4301
    ldx #$0200
    stx $4305
    lda #$01
    sta $420B
    ; Mode 0 BG1, 2bpp tiles, one 32x32 tilemap at VRAM word $1000.
    stz $2105
    lda #$10
    sta $2107
    stz $210B
    stz $210D
    stz $210D
    lda #$FF
    sta $210E
    sta $210E
    stz $2130
    stz $2131
    stz $2133
    lda #$01
    sta $212C
    ; Static font after the 256 currently displayed CHR tiles.
    ldx #$0800
    stx $2116
    ldx #.loword(Font)
    stx $4302
    ldx #$0400
    stx $4305
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    stz $4304
    lda #$01
    sta $420B
    ; Static layout. All 1024 entries are initialized.
    ldx #$1000
    stx $2116
    ldx #.loword(Tilemap)
    stx $4302
    ldx #$0800
    stx $4305
    lda #$01
    sta $420B
    jsr UploadPage
    jsr UploadPalette
    jsr UpdatePageNumber
    lda #$01
    sta $4200             ; automatic joypad reads; no NMI/IRQ needed by viewer

Main:
    ; Edge-synchronized vblank. No timing-dependent NES game code runs here.
WaitVisible:
    lda $4212
    bmi WaitVisible
WaitVblank:
    lda $4212
    bpl WaitVblank
WaitJoy:
    lda $4212
    and #$01
    bne WaitJoy
    inc FRAME
    lda $4219
    eor OLD_HI
    and $4219
    sta EDGE_HI
    lda $4219
    sta OLD_HI
    lda $4218
    eor OLD_LO
    and $4218
    sta EDGE_LO
    lda $4218
    sta OLD_LO
    ; Right or R: next 256-tile page. Left or L: previous page.
    lda EDGE_HI
    and #$01
    bne NextPage
    lda EDGE_LO
    and #$10
    bne NextPage
    lda EDGE_HI
    and #$02
    bne PreviousPage
    lda EDGE_LO
    and #$20
    beq CheckPalette
PreviousPage:
    lda PAGE
    bne DecrementPage
    lda #PAGE_COUNT
    sta PAGE
DecrementPage:
    dec PAGE
    bra PageChanged
NextPage:
    inc PAGE
    lda PAGE
    cmp #PAGE_COUNT
    bcc PageChanged
    stz PAGE
PageChanged:
    lda #$01
    sta DIRTY
CheckPalette:
    lda EDGE_HI
    and #$80              ; B cycles diagnostic palettes, not original game colors
    beq Render
    inc PALETTE
    lda PALETTE
    and #$03
    sta PALETTE
    lda #$01
    sta DIRTY
Render:
    lda DIRTY
    beq EnableDisplay
    ; Forced blank makes this safe even if a later build exceeds vblank DMA budget.
    lda #$80
    sta $2100
    jsr UploadPage
    jsr UploadPalette
    jsr UpdatePageNumber
    stz DIRTY
EnableDisplay:
    lda #$0F
    sta $2100
    jmp Main

UploadPage:
    ; Each page is 4 KiB. Eight pages occupy each appended LoROM bank.
    stz $2116
    stz $2117
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    stz $4302
    lda PAGE
    and #$07
    asl a
    asl a
    asl a
    asl a
    ora #$80
    sta $4303
    lda PAGE
    lsr a
    lsr a
    lsr a
    inc a
    sta $4304
    ldx #$1000
    stx $4305
    lda #$01
    sta $420B
    rts

UploadPalette:
    stz $2121
    lda PALETTE
    asl a
    asl a
    asl a
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ldy #$0008
PaletteLoop:
    lda Palettes,x
    sta $2122
    inx
    dey
    bne PaletteLoop
    rts

UpdatePageNumber:
    ; Two hexadecimal digits show the zero-based page at row 22, column 15.
    ldx #$12CF
    stx $2116
    lda PAGE
    lsr a
    lsr a
    lsr a
    lsr a
    jsr WriteHexDigit
    lda PAGE
    and #$0F
    jsr WriteHexDigit
    rts
WriteHexDigit:
    rep #$20
.a16
    and #$000F
    tax
    sep #$20
.a8
    lda HexTiles,x
    sta $2118
    lda #$01
    sta $2119
    rts

Nmi:
    rti
Irq:
    rti

.segment "RODATA"
Zero: .byte $00
HexTiles: .byte $10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$21,$22,$23,$24,$25,$26
Palettes:
    .word $0000,$294A,$5294,$7FFF
    .word $0000,$0140,$02A0,$03E0
    .word $0000,$280A,$5014,$7C1F
    .word $0000,$014A,$0294,$03FF
Font: .incbin "font.2bpp"
Tilemap: .incbin "tilemap.bin"

.segment "HEADER"
    .byte "NES2SNES CHR VIEWER  "
    .byte $20,$00,$08,$00,$01,$00,$00
    .word $FFFF,$0000
.segment "VECTOR"
    .word $0000,$0000,Irq,Irq,Irq,Nmi,$0000,Irq
    .word $0000,$0000,Irq,$0000,Irq,Nmi,Reset,Irq
