; Forced-blank PPUDATA semantics. ResolveVram leaves an A8 result pointer and
; carry marks CHR/MMC5 fill. Palette data bypasses the delayed read buffer, but
; the same access still refills that buffer from the underlying nametable.
ReadPpuData:
    jsr ResolveVram
    jsr ReadResolvedVram
    sta TMP
    rep #$20
.a16
    lda PADDR
    cmp #$3F00
    bcs @palette
    sep #$20
.a8
    lda RDBUF
    pha
    lda TMP
    sta RDBUF
    bra @advance
@palette:
    sep #$20
.a8
    lda TMP
    and #$3F
    sta TMP
    lda MASK
    and #$01
    beq @color
    lda TMP
    and #$30
    sta TMP
@color:
    lda PPUBUS
    and #$C0
    ora TMP
    pha
    ; Use the original mirrored PPU address, not its palette alias index.
    ; Resolve without changing live v: the access increments v exactly once.
    rep #$20
.a16
    lda PADDR
    and #$2FFF
    jsr ResolveVramAddress
    jsr ReadResolvedVram
    sta RDBUF
@advance:
    jsr AdvanceVram
    pla
    sta PPUBUS
    rts

; Read a previously resolved address. Preserve the resolver's carry on entry.
ReadResolvedVram:
.a8
    bcs @special
    lda [PTR]
    rts
@special:
    rep #$20
.a16
    lda PADDR
    cmp #$2000
    bcc @chr
    and #$03FF
    cmp #$03C0
    bcs @attr
    sep #$20
.a8
    lda f:$7E5106
    rts
@attr:
    sep #$20
.a8
    lda f:$7E5107
    and #$03
    sta TMP
    asl a
    asl a
    ora TMP
    sta TMP
    asl a
    asl a
    asl a
    asl a
    ora TMP
    rts
@chr:
    jmp ReadChr
