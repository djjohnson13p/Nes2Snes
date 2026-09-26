; Native re-emission of a completely classified inline-table dispatch idiom.
; Only read-only original-ROM tables in the nonwrapping range qualify. The
; unmodified original body remains callable for every rejected context.
; This runs in mirrored WRAM in the caller's execution bank, with D=0 and DBR
; selecting the independent raw-data map. Original guest X is never touched.
DispatchCount = $09B0
.a8
.i8
    php
    rep #$20
.a16
    pha
    ; Stack: full original A, P, and the unchanged JSR return address.
    lda 4,s
    cmp #$8000
    bcc @fallback
    cmp #$FF01
    bcs @fallback
    sep #$20
.a8
    lda RUNNING
    cmp #$01
    bne @fallback
    rep #$20
.a16
    .if ::USE_RUNTIME_COUNTERS
    inc DispatchCount
    bne :+
    inc DispatchCount+2
:
    .endif
    pla
    plp
.a8
.i8
    ; The bounded table makes both indirect loads ordinary native reads.
    ; Emit the operations directly rather than returning through two COPs.
    ; Eight-bit INY deliberately wraps between the low and high table reads.
    asl a
    sty $03
    tay
    iny
    pla
    sta $00
    pla
    sta $01
    lda ($00),y
    sta $02
    iny
    lda ($00),y
    ldy $03
    sta $03
    jmp ($0002)
@fallback:
    rep #$20
.a16
    pla
    plp
.a8
.i8
    jmp OriginalDispatch
