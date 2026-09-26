; Indexed absolute operations: runtime-checked RAM / original-ROM path.
; COP already saved full A and X. Y, D and DBR remain the guest's values.
; Effective addresses wrap at 16 bits, and internal RAM folds to 2 KiB.
; PPU/cartridge RAM and ROM stores retain CopGeneric; selected APU stores
; reuse the existing event handler, with a fallback for PPU-page dummy reads.
.if USE_QUICK_INDEXED
QUICK_INDEXED_CALLS=$0990

.macro PrepareIndexed name, use_y, write_only
name:
.a16
.i16
    lda 8,s                 ; saved guest PC after COP and this helper JSR
    dec a
    tax
    lda a:$0000,x           ; original operand, never the patched instruction
    sta INDEXBASE
    .if use_y
        sta EA
        tya
        clc
        adc EA
    .else
        clc
        adc 3,s             ; original 8-bit X, saved as a full 16-bit word
    .endif
    cmp #$2000
    bcc @ram
    .if !write_only
        cmp #$8000
        bcs @safe
    .endif
    .if write_only
        sta EA
        pla                 ; discard helper return; preserve the computed EA
        lda EA
        jmp QuickIndexedIoWrite
    .else
        pla                 ; discard helper return; retain untouched A/X saves
        jmp CopGeneric
    .endif
@ram:
    and #$07FF
@safe:
    tax
    CountRuntime QUICK_INDEXED_CALLS
    CountRuntime $0960
    sep #$20
.a8
    lda 7,s
    and #$EF                ; keep address X wide while restoring guest C/V
    pha
    rep #$20
.a16
    lda 6,s                 ; saved accumulator, including the hidden B byte
    plp
.a8
.i16
    rts
.endmacro

PrepareIndexed PrepareIndexedReadX, 0, 0
PrepareIndexed PrepareIndexedReadY, 1, 0
PrepareIndexed PrepareIndexedWriteX, 0, 1
PrepareIndexed PrepareIndexedWriteY, 1, 1

; Emit explicit names so the generated dispatch table and ca65 labels agree.
.macro IndexedHandler label_name, operation, prepare
label_name:
.a16
.i16
    jsr prepare
.a8
.i16
    operation a:$0000,x
    jmp QuickIndexedDone
.endmacro
IndexedHandler QuickLDA_ABSX, lda, PrepareIndexedReadX
IndexedHandler QuickLDA_ABSY, lda, PrepareIndexedReadY
IndexedHandler QuickAND_ABSX, and, PrepareIndexedReadX
IndexedHandler QuickAND_ABSY, and, PrepareIndexedReadY
IndexedHandler QuickORA_ABSX, ora, PrepareIndexedReadX
IndexedHandler QuickORA_ABSY, ora, PrepareIndexedReadY
IndexedHandler QuickEOR_ABSX, eor, PrepareIndexedReadX
IndexedHandler QuickEOR_ABSY, eor, PrepareIndexedReadY
IndexedHandler QuickADC_ABSX, adc, PrepareIndexedReadX
IndexedHandler QuickADC_ABSY, adc, PrepareIndexedReadY
IndexedHandler QuickSBC_ABSX, sbc, PrepareIndexedReadX
IndexedHandler QuickSBC_ABSY, sbc, PrepareIndexedReadY
IndexedHandler QuickCMP_ABSX, cmp, PrepareIndexedReadX
IndexedHandler QuickCMP_ABSY, cmp, PrepareIndexedReadY
IndexedHandler QuickSTA_ABSX, sta, PrepareIndexedWriteX
IndexedHandler QuickSTA_ABSY, sta, PrepareIndexedWriteY

; Indexed stores may address I/O. Reuse the verified write-event routines,
; never turn I/O into a plain SNES bus access. Full A/X and guest P are already
; saved by COP; preserve Y/D/DBR for the shared writers.
QuickIndexedIoWrite:
.a16
.i16
    cmp #$4000
    jcc CopGeneric          ; PPU dummy reads must happen before indexed writes
    cmp #$4018
    jcs CopGeneric
    cmp #$4014
    jeq CopGeneric          ; OAM source / transfer has independent semantics
    cmp #$4016
    jeq CopGeneric          ; controller strobe is not an APU write
    pha
    lda INDEXBASE
    cmp #$4000
    bcs :+
    pla
    jmp CopGeneric          ; intermediate read may still be a PPU register
:
    pla
    and #$001F
    tax
    CountRuntime $0994
    CountRuntime $0960
.if USE_AUDIO_COUNTERS
    phy
    phd
    phb
    sep #$20
.a8
    lda #$00
    pha
    plb
    lda #$01
    sta COPBUSY
    lda 8,s                ; original A below Y/D/DBR saves
    jsr ApuWriteRegister    ; repeated identical writes still reload counters
    sep #$20
.a8
    stz COPBUSY
    plb
    pld
    rep #$10
.i16
    ply
.else
    sep #$20
.a8
    lda 3,s
    sta f:$7E4000,x
.endif
    jmp QuickAbsReturn

QuickIndexedDone:
.a8
.i16
    php
    rep #$30
.a16
.i16
    sta 4,s                 ; resulting full A replaces the saved A
    sep #$20
.a8
    pla
    ora #$30                ; guest M/X return to 8-bit
    sta 5,s                 ; preserve the operation's flags across PC advance
    jmp QuickAbsReturn      ; advance past the third original instruction byte
.endif
