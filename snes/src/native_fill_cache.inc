; Frame-quantized fill-mode cache invalidation. Applies to the existing
; non-extended-attribute fill renderer, not mid-scanline fill changes.
; $0D6A..$0D6D follow OBJECTS_CTRL and precede OLDMIRROR; WRAM clears at boot.
.if USE_FILL_CACHE_FIX
FILL_TILE_CACHE=$0D6A
FILL_COLOR_CACHE=$0D6B
FILL_CHANGED=$0D6C
FILL_CACHE_VALID=$0D6D
UpdateFillCache:
.a8
.i16
    stz FILL_CHANGED
    lda FILL_CACHE_VALID
    beq @changed
    lda f:$7E5106
    cmp FILL_TILE_CACHE
    bne @changed
    lda f:$7E5107
    and #$03
    cmp FILL_COLOR_CACHE
    bne @changed
    rts
@changed:
    lda f:$7E5106
    sta FILL_TILE_CACHE
    lda f:$7E5107
    and #$03
    sta FILL_COLOR_CACHE
    lda #$01
    sta FILL_CHANGED
    sta FILL_CACHE_VALID
    rts
.endif
