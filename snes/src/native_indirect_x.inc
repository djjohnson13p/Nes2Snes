; Original host implementation for NMOS 6502 (zero-page,X) reads.
; Included inside USE_QUICK_DISPATCH. The option is off by default.
; The original A/X and COP frame already exist on the guest stack. Y, D and
; DBR remain untouched. Hardware and cartridge RAM use the generic handler.
.if USE_QUICK_INDIRECT_X
PrepareQuickIndirectX:
.a16
.i16
    ; JSR adds two bytes: saved X at +3, A at +5, guest P at +7, PC at +8.
    lda 8,s
    dec a
    tax
    lda a:$0000,x          ; operand comes from the unmodified data mapping
    and #$00FF
    clc
    adc 3,s                ; original guest X, not the temporary dispatch X
    and #$00FF             ; wrap the pointer index within zero page
    tax
    cpx #$00FF
    beq @wrap
    lda a:$0000,x
    bra @pointer
@wrap:
    ; At $FF the high byte is at $00, never at stack address $0100.
    sep #$20
.a8
    lda a:$0000
    xba
    lda a:$00FF
    rep #$20
.a16
@pointer:
    cmp #$2000
    bcc @ram
    cmp #$8000
    bcs @safe
    ; Drop only this helper's return address; CopGeneric restores original X/A
    ; and decodes the original instruction with all supported I/O side effects.
    pla
    jmp CopGeneric
@ram:
    and #$07FF             ; NES internal RAM mirrors, not private host scratch
@safe:
    tax
    CountRuntime $0968     ; existing indirect-read diagnostic, optional
    CountRuntime $0960
    sep #$20
.a8
    lda 7,s
    and #$EF               ; keep 16-bit effective-address X for the data read
    pha
    rep #$20
.a16
    lda 6,s                ; restore full A, including its hidden high byte
    plp                    ; restore original carry/overflow and eight-bit A
.a8
.i16
    rts

.macro QuickIndirectXHandler name, operation
name:
.a16
.i16
    jsr PrepareQuickIndirectX
.a8
.i16
    operation a:$0000,x
    jmp QuickZpxDone        ; preserve actual operation flags and restore X
.endmacro
QuickIndirectXHandler QuickLDA_IX, lda
QuickIndirectXHandler QuickCMP_IX, cmp
QuickIndirectXHandler QuickADC_IX, adc
QuickIndirectXHandler QuickSBC_IX, sbc
QuickIndirectXHandler QuickAND_IX, and
QuickIndirectXHandler QuickORA_IX, ora
QuickIndirectXHandler QuickEOR_IX, eor
.endif
