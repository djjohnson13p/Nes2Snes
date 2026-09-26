; Same-size absolute accesses enter a WRAM veneer via JSR. The veneer returns
; with RTS for ordinary I/O or RTL into a new bank for PRG selectors.
; Compound work is in bank $80; its
; full context is restored before returning. Bank $C0 retains COP instructions.
.if USE_DIRECT_CALLS
.import __STUBS_LOAD__, __STUBS_RUN__, __STUBS_SIZE__
.assert __STUBS_SIZE__ <= $0800, lderror, "Direct-call veneers exceed reserved WRAM"
InitializeDirectStubs:
.a8
.i16
    ldx #__STUBS_RUN__
    stx $2181
    stz $2183
    stz $4300
    lda #$80
    sta $4301
    ldx #__STUBS_LOAD__
    stx $4302
    stz $4304
    ldx #__STUBS_SIZE__
    stx $4305
    lda #$01
    sta $420B
    rts

; On entry: A/X/Y are 8-bit guest registers except X is the selected writer
; index. Original X and P remain in the veneer stack. JSL adds three bytes.
; Save full A (including B), Y, D and DB before using any host scratch context.
.macro DirectWriteHandler name, value_offset
name:
.a8
.i8
    rep #$30
.a16
.i16
    pha
    phy
    phd
    phb
    CountRuntime $0980
    lda #$0800
    tcd
    sep #$20
.a8
    lda #$00
    pha
    plb
    lda #$01
    sta COPBUSY
    lda value_offset,s
    sta VAL
    cpx #$0010
    bcs :+
    sta PPUBUS
:
    jsr (DirectWriters,x)
    sep #$20
.a8
    stz COPBUSY
    plb
    pld
    rep #$30
.a16
.i16
    ply
    pla
    sep #$30
.a8
.i8
    rtl
.endmacro
DirectWriteHandler DirectWriteA, 6
DirectWriteHandler DirectWriteX, 11
DirectWriteHandler DirectWriteY, 4
; These writers use only absolute low-WRAM state and preserve X/Y/D/DBR.
; The raw-ROM DBR still mirrors that WRAM. Only full A must be saved here;
; the veneer already saves guest P and X. Host-PBR/veneer-PC NMI gates protect
; the sequence. OAM, data-port and joypad work retain the full-context path.
.macro DirectSimpleHandler name, source
name:
.a8
.i8
    rep #$20
.a16
    pha
    CountRuntime $0984
    sep #$20
.a8
.if source = 1
    lda 6,s              ; guest X beneath JSL and full-A save
.elseif source = 2
    tya
.endif
    sta VAL
    cpx #$10
    bcs :+
    sta PPUBUS
:
    jsr (DirectWriters,x)
    rep #$20
.a16
    pla
    sep #$20
.a8
    rtl
.endmacro
DirectSimpleHandler DirectSimpleWriteA, 0
DirectSimpleHandler DirectSimpleWriteX, 1
DirectSimpleHandler DirectSimpleWriteY, 2
DirectWriters:
    .word WriteCtrl,WriteMask,WriteIgnore,WriteOaddr,WriteOdata,WriteScroll,WriteAddr,WritePpuData
    .word WriteOamDma,WriteJoy,WriteIrqPos,WriteIrqEnable

; APU write callback: do not lose same-value reloads in the shadow cache.
.if USE_AUDIO_COUNTERS
.macro DirectApuHandler name, value_offset
name:
.a8
.i8
    rep #$30
.a16
.i16
    pha
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
    lda value_offset,s
    jsr ApuWriteRegister
    stz COPBUSY
    plb
    pld
    rep #$30
.a16
.i16
    ply
    pla
    sep #$30
.a8
.i8
    rtl
.endmacro
DirectApuHandler DirectApuA, 6
DirectApuHandler DirectApuX, 11
DirectApuHandler DirectApuY, 4
.endif

; LDA changes N/Z only. AND/ORA/LDA/STA preserve guest C/V/D/I. The joypad's
; internal shift additionally requires preserving C across that bookkeeping.
DirectReadStatus:
.a8
.i8
    lda STATUS
    and #$E0
    sta TMP
    lda PPUBUS
    and #$1F
    ora TMP
    pha
    lda STATUS
    and #$7F
    sta STATUS
    stz LATCH
    pla
    sta PPUBUS
    rtl
DirectReadJoy:
    php
    lda JOYSHIFT
    and #$01
    ora #$40
    sta TMP
    lda STROBE
    bne @held
    lda JOYSHIFT
    lsr a
    ora #$80
    sta JOYSHIFT
@held:
    plp
    lda TMP
    rtl
DirectReadJoy2:
    lda #$40
    rtl
DirectReadIrq:
    lda f:$004212
    and #$80
    beq @inframe
    lda #$00
    bra @pending
@inframe:
    lda #$40
@pending:
    ora IRQPENDING
    stz IRQPENDING
    rtl
.endif
; A bank-store veneer reaches here only on unsupported selector values.
; Its frame is: full A, P, near-JSR return. Do not use stale COP diagnostics.
DirectBankFault:
.a8
.i8
    rep #$20
.a16
    lda 4,s
    sec
    sbc #$0002
    sta f:FAULTPC
    sep #$20
.a8
    lda CODEBANK
    sta f:FAULTBANK
    lda #$03
    sta f:FAULTCODE
    jmp FaultDisplay
.include "direct-stubs.inc"
