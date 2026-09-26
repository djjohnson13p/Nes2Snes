; NES PPUMASK left-edge clipping using the native SNES window hardware.
; A per-scanline TMW table follows the SAME run lengths as the main-screen
; layer table. It never changes the background scroll or sprite coordinates.
; Inputs are immutable presentation snapshots; live guest writes are not read.
.if USE_LAYER_MASKS
TOPWINDOW=$0CE4
BOTTOMWINDOW=$0CE5
WINDOW_READY=$0CE7

SetWindowRegisters:
.a8
.i16
    lda FRAME_MASK
    jsr MaskToWindow
    sta BOTTOMWINDOW
    sta $212E
    lda TOPMASK
    jsr MaskToWindow
    sta TOPWINDOW
    lda HDMA_ENABLE
    and #$02
    beq @constant
    lda TOPWINDOW
    cmp BOTTOMWINDOW
    beq @constant
    jsr InitializeWindows
    ; Copy TM's non-repeating run lengths and translate the corresponding
    ; selected layer into its left-edge mask. Blank bands need only OBJ.
    ldx #$0000
@run:
    lda f:$7F2500,x
    sta f:$7F2540,x
    beq @configure
    inx
    ; All supported tables have a final playfield segment. Earlier
    ; segments are top/HUD or its blank band, even when BG2 is disabled.
    lda f:$7F2501,x       ; count for the following segment
    beq @bottom
    lda TOPWINDOW
    bra @write
@bottom:
    lda BOTTOMWINDOW
@write:
    sta f:$7F2540,x
    inx
    bra @run
@configure:
    stz $4330
    lda #$2E
    sta $4331
    ldx #$2540
    stx $4332
    lda #$7F
    sta $4334
    lda HDMA_ENABLE
    ora #$08
    sta HDMA_ENABLE
    sta $420C
    rts
@constant:
    lda BOTTOMWINDOW
    beq @done
    jsr InitializeWindows
@done:
    rts

InitializeWindows:
.a8
.i16
    lda WINDOW_READY
    bne @done
    inc WINDOW_READY
    ; Window 1 clips the inclusive interval [0,7], independently per layer.
    lda #$22
    sta $2123             ; enable window 1 on BG1 and BG2, non-inverted
    stz $2124
    lda #$02
    sta $2125             ; enable window 1 on OBJ, not the color window
    stz $2126
    lda #$07
    sta $2127
    stz $212A
    stz $212B
@done:
    rts

MaskToWindow:
.a8
.i16
    rep #$20
.a16
    and #$0006
    lsr a
    tax
    sep #$20
.a8
    lda WindowMasks,x
    rts
WindowMasks:
    .byte $13,$10,$03,$00
.endif
