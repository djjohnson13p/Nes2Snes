; Frozen scene renderer using real SNES BG1 and OBJ layers. No NES game code.
.setcpu "65816"
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
    sta $2100
    stz $4200
    stz $420B
    stz $420C
    stz $420D
    ldx #$0033
ClearPpu:
    stz $2100,x
    dex
    bne ClearPpu
    lda #$80
    sta $2115
    ldx #$0000
    stx $2116
    lda #$09
    sta $4300
    lda #$18
    sta $4301
    ldx #.loword(Zero)
    stx $4302
    stz $4304
    stz $4305
    stz $4306
    lda #$01
    sta $420B
    ; Mode 0, BG1 2bpp, BG1 tilemap at VRAM word $1000.
    stz $2105
    lda #$10
    sta $2107
    stz $210B
    stz $210D
    stz $210D
    lda #$07             ; crop original 240-line image to its middle 224 lines
    sta $210E
    stz $210E
    ; 8x8/16x16 sprite size pair; use only small sprites. Base = byte $8000.
    lda #$02
    sta $2101
    lda #$11
    sta $212C            ; BG1 + sprites
    ; Background tile data.
    ldx #$0000
    stx $2116
    ldx #.loword(Background)
    stx $4302
    ldx #$1000
    stx $4305
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    lda #$01
    sta $420B
    ; All 512 sprite tiles, zero-extended to SNES 4bpp.
    ldx #$4000
    stx $2116
    ldx #.loword(Sprites)
    stx $4302
    ldx #$4000
    stx $4305
    lda #$01
    sta $420B
    ; Full tilemap.
    ldx #$1000
    stx $2116
    ldx #.loword(Tilemap)
    stx $4302
    ldx #$0800
    stx $4305
    lda #$01
    sta $420B
    ; Palette.
    stz $2121
    stz $4300
    lda #$22
    sta $4301
    ldx #.loword(Cgram)
    stx $4302
    ldx #$0200
    stx $4305
    lda #$01
    sta $420B
    ; Both low and high OAM tables.
    stz $2102
    stz $2103
    lda #$04
    sta $4301
    ldx #.loword(Oam)
    stx $4302
    ldx #$0220
    stx $4305
    lda #$01
    sta $420B
    lda #$0F
    sta $2100
Forever:
    bra Forever
Nmi:
    rti
Irq:
    rti
.segment "RODATA"
Zero: .byte 0
Background: .incbin "background.2bpp"
Sprites: .incbin "sprites.4bpp"
Tilemap: .incbin "tilemap.bin"
Cgram: .incbin "cgram.bin"
Oam: .incbin "oam.bin"
.segment "HEADER"
    .byte "NES2SNES SCENE TEST  "
    .byte $20,$00,$06,$00,$01,$00,$00
    .word $FFFF,$0000
.segment "VECTOR"
    .word $0000,$0000,Irq,Irq,Irq,Nmi,$0000,Irq
    .word $0000,$0000,Irq,$0000,Irq,Nmi,Reset,Irq
