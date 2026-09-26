; Trace-bounded native NES CPU bridge. Original program bytes are generated
; privately from the input ROM. This file contains only new host implementation.
.setcpu "65816"
; Fixed-size long conditional branches, independent of cc65 macro packages.
.macro jeq target
    bne :+
    jmp target
:
.endmacro
.macro jne target
    beq :+
    jmp target
:
.endmacro
.macro jcc target
    bcs :+
    jmp target
:
.endmacro
.macro jcs target
    bcc :+
    jmp target
:
.endmacro
.include "config.inc"

SA=$0800
SX=$0802
SY=$0804
SS=$0806
NPC=$0808
SB=$080A
SF=$080B
OPCODE=$080D
PPC=$10
MEM=$14
EA=$0818
VAL=$081A
TMP=$081B
OPER=$081E
MODE=$081F
PTR=$20
PADDR=$0824
INDEXBASE=$082C
DUMMYADDR=$082E

SLOT=$0900
RAWBANK=$0901
CODEBANK=$0902
COPBUSY=$0903
RUNNING=$0904
GFRAMES=$0906
HFRAMES=$0908
IFRAMES=$090A
FAULTPC=$090C
FAULTBANK=$090E
FAULTCODE=$090F
CTRL=$0910
MASK=$0911
STATUS=$0912
OADDR=$0913
LATCH=$0914
FINEX=$0915
TEMPV=$0916
VRAMV=$0918
RDBUF=$091A
PPUBUS=$091B
JOYLATCH=$0930
JOYSHIFT=$0931
STROBE=$0932
IRQPOS=$0940
IRQENABLE=$0941
IRQPENDING=$0942
IRQCOUNT=$0943
LASTIRQ=$0944
LASTCHR=$0945
FRAME_READY=$0946
NCTX=$0B00

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
    lda #USE_FASTROM
    sta $420D
    ; Clear all WRAM before allocating stack frames.
    stz $2181
    stz $2182
    stz $2183
    lda #$08
    sta $4300
    lda #$80
    sta $4301
    ldx #.loword(Zero)
    stx $4302
    stz $4304
    stz $4305
    stz $4306
    lda #$01
    sta $420B
    sta $420B
    .if USE_DIRECT_CALLS
    jsr InitializeDirectStubs
    .endif
    .if USE_EXPERIMENTAL_AUDIO
    jsr AudioInitialize
    .endif
    ; Initialize known PPU state.
    ldx #$0033
@clearppu:
    stz $2100,x
    dex
    bne @clearppu
    stz $212C
    stz $212D
    stz $2121
    stz $2122
    stz $2122
    lda #$0F
    sta $2100
    lda #$81
    sta RAWBANK
    lda #$A1
    sta CODEBANK
    lda #$03
    sta f:$7E5100
    lda #$FF
    sta f:$7E5117
    lda #$9E
    sta f:$7E5116
    lda #$80
    sta f:$7E5115
    ; Initialize virtual OAM as hidden.
    ldx #$0000
@oam:
    lda #$FF
    sta f:$7E3800,x
    inx
    cpx #$0100
    bne @oam
    ; Force initial texture and nametable uploads.
    ldx #$000F
    lda #$FF
@cache:
    sta $0D80,x
    dex
    bpl @cache
    sta $0D70
    sta $0D71
    lda #$81
    sta $4200             ; NMI and automatic joypad reads
    ldx #$01FF
    txs
    lda RAWBANK
    pha
    plb
    sep #$30
.a8
.i8
    jml $A10000+GUEST_RESET

; COP is used only at safely identified, replaceable instruction boundaries.
; A raw ROM mapping remains independent of the executable mapping.
CopHandler:
.if USE_FASTROM
    jml $800000+CopFast
CopFast:
.endif
.if USE_QUICK_DISPATCH
    ; Guest DBR always selects the unmodified ROM mapping, including low WRAM.
    ; Preserve full A and X before inspecting the original instruction. Y/D/DB
    ; stay untouched. The original COP frame is below these two 16-bit saves.
    rep #$30
.a16
.i16
    pha
    phx
    lda 6,s
    sec
    sbc #$0002
    tax
    lda a:$0000,x
    and #$00FF
    asl a
    tax
    jmp (QuickZpTable,x)
CopGeneric:
    plx
    pla
.endif
    rep #$30
.a16
.i16
    sta f:SA
    txa
    sta f:SX
    tya
    sta f:SY
    tsc
    sta f:SS
    lda 2,s
    sec
    sbc #$0002
    sta f:$0810
    sep #$20
.a8
    lda 1,s
    sta f:SF
    lda 4,s
    sta f:SB
    sec
    sbc #$20
    sta f:$0812
    rep #$20
.a16
    ldx #$1FFF
    txs
    lda #$0800
    tcd
    sep #$20
.a8
    lda #$00
    pha
    plb
    lda #$01
    sta COPBUSY
    rep #$20
.a16
    inc $0960
    bne :+
    inc $0962
:
    lda [PPC]
    and #$00FF
    tax
    stx OPCODE
    sep #$20
.a8
    lda OperationTable,x
    sta OPER
    jeq BadOperation
    lda ModeTable,x
    sta MODE
    lda LengthTable,x
    rep #$20
.a16
    and #$00FF
    clc
    adc $0810
    sta NPC
    ldy #$0001
    lda [PPC],y
    sta EA
    lda MODE
    and #$00FF
    asl a
    tax
    jmp (AddressModes,x)

AddressModes:
    .word ModeZp,ModeZpx,ModeZpy,ModeAbs,ModeAbsx,ModeAbsy,ModeIx,ModeIy
ModeZpx:
    lda EA
    clc
    adc SX
    bra ModeByte
ModeZpy:
    lda EA
    clc
    adc SY
    bra ModeByte
ModeZp:
    lda EA
ModeByte:
    and #$00FF
    sta EA
    bra AddressReady
ModeAbsx:
    lda EA
    sta INDEXBASE
    clc
    adc SX
    sta EA
    jsr IndexedDummyRead
    bra AddressReady
ModeAbsy:
    lda EA
    sta INDEXBASE
    clc
    adc SY
    sta EA
    jsr IndexedDummyRead
    bra AddressReady
ModeIx:
    lda EA
    clc
    adc SX
    and #$00FF
    tax
    jsr ReadZeroPointer
    bra AddressReady
ModeIy:
    lda EA
    and #$00FF
    tax
    jsr ReadZeroPointer
    lda EA
    sta INDEXBASE
    clc
    adc SY
    sta EA
    jsr IndexedDummyRead
    bra AddressReady
ReadZeroPointer:
    sep #$20
.a8
    lda f:$7E0000,x
    sta EA
    rep #$20
.a16
    inx
    txa
    and #$00FF
    tax
    sep #$20
.a8
    lda f:$7E0000,x
    sta EA+1
    rep #$20
.a16
    rts
ModeAbs:
AddressReady:
    lda EA
    cmp #$2000
    bcs @notram
    and #$07FF
@notram:
    sta $0814
    sep #$20
.a8
    lda #$7E
    sta $0816
    rep #$20
.a16
    lda EA
    cmp #$8000
    bcc @operate
    sep #$20
.a8
    lda RAWBANK
    sta $0816
    rep #$20
.a16
@operate:
    lda OPER
    and #$00FF
    asl a
    tax
    sep #$20
.a8
    jmp (OperationHandlers,x)
OperationHandlers:
    .word BadOperation,OpLda,OpLdx,OpLdy,OpSta,OpStx,OpSty
    .word OpAnd,OpOra,OpEor,OpAdc,OpSbc,OpCmp,OpCpx,OpCpy,OpBit
    .word OpAsl,OpLsr,OpRol,OpRor,OpInc,OpDec
OpSta:
    lda SA
    sta VAL
    jsr WriteValue
    jmp CopReturn
OpStx:
    lda SX
    sta VAL
    jsr WriteValue
    jmp CopReturn
OpSty:
    lda SY
    sta VAL
    jsr WriteValue
    jmp CopReturn
OpLda:
    jsr ReadValue
    sta SA
    jsr SetNZ
    jmp CopReturn
OpLdx:
    jsr ReadValue
    sta SX
    jsr SetNZ
    jmp CopReturn
OpLdy:
    jsr ReadValue
    sta SY
    jsr SetNZ
    jmp CopReturn
OpAnd:
    jsr ReadValue
    and SA
    bra StoreNZ
OpOra:
    jsr ReadValue
    ora SA
    bra StoreNZ
OpEor:
    jsr ReadValue
    eor SA
StoreNZ:
    sta SA
    jsr SetNZ
    jmp CopReturn
OpAdc:
    jsr ReadValue
    sta VAL
    lda SF
    lsr a
    lda SA
    adc VAL
    sta SA
    php
    pla
    and #$C3
    sta TMP
    lda SF
    and #$3C
    ora TMP
    sta SF
    jmp CopReturn
OpSbc:
    jsr ReadValue
    sta VAL
    lda SF
    lsr a
    lda SA
    sbc VAL
    sta SA
    php
    pla
    and #$C3
    sta TMP
    lda SF
    and #$3C
    ora TMP
    sta SF
    jmp CopReturn
OpCmp:
    jsr ReadValue
    sta VAL
    lda SA
    cmp VAL
    bra MergeNZC
OpCpx:
    jsr ReadValue
    sta VAL
    lda SX
    cmp VAL
    bra MergeNZC
OpCpy:
    jsr ReadValue
    sta VAL
    lda SY
    cmp VAL
MergeNZC:
    php
    pla
    and #$83
    sta TMP
    lda SF
    and #$7C
    ora TMP
    sta SF
    jmp CopReturn
OpBit:
    jsr ReadValue
    sta VAL
    and SA
    cmp #$00
    php
    pla
    and #$02
    sta TMP
    lda VAL
    and #$C0
    ora TMP
    sta TMP
    lda SF
    and #$3D
    ora TMP
    sta SF
    jmp CopReturn
OpAsl:
    jsr ReadRmw
    asl a
    bra FinishRmwC
OpLsr:
    jsr ReadRmw
    lsr a
    bra FinishRmwC
OpRol:
    jsr ReadRmw
    sta VAL
    lda SF
    lsr a
    lda VAL
    rol a
    bra FinishRmwC
OpRor:
    jsr ReadRmw
    sta VAL
    lda SF
    lsr a
    lda VAL
    ror a
FinishRmwC:
    sta VAL
    php
    pla
    and #$83
    sta TMP
    lda SF
    and #$7C
    ora TMP
    sta SF
    jsr WriteValue
    jmp CopReturn
OpInc:
    jsr ReadRmw
    inc a
    bra FinishRmw
OpDec:
    jsr ReadRmw
    dec a
FinishRmw:
    sta VAL
    jsr SetNZ
    jsr WriteValue
    jmp CopReturn
ReadRmw:
    jsr ReadValue
    sta VAL
    ; NMOS RMW writes the old value as well as the final value.
    jsr WriteValue
    lda VAL
    rts
SetNZ:
    cmp #$00
    php
    pla
    and #$82
    sta TMP
    lda SF
    and #$7D
    ora TMP
    sta SF
    rts

CopReturn:
    rep #$30
.a16
.i16
    ldx SS
    lda NPC
    sta f:$7E0002,x
    sep #$20
.a8
    lda SF
    ora #$30
    sta f:$7E0001,x
    lda CODEBANK
    sta f:$7E0004,x
    stz COPBUSY
    lda RAWBANK
    pha
    plb
    rep #$30
.a16
    lda f:SS
    tcs
    lda f:SX
    tax
    lda f:SY
    tay
    lda f:SA
    pea $0000
    pld
    rti

; Indexed-zero-page operands are provably ordinary RAM after 8-bit wrapping.
; Execute the actual arithmetic/logical instruction instead of interpreting its
; flags. This fast path never bypasses a hardware access or a mapper operation.
.if USE_QUICK_DISPATCH
PrepareQuickZpx:
.a16
.i16
    inc $0964
    bne :+
    inc $0966
:
    inc $0960
    bne :+
    inc $0962
:
    ; JSR adds two bytes: +3 is saved X, +5 saved A, +7 guest P, +8 guest PC.
    lda 8,s
    dec a
    tax
    lda a:$0000,x
    and #$00FF
    clc
    adc 3,s
    and #$00FF
    tax
    sep #$20
.a8
    lda 7,s
    pha
    rep #$20
.a16
    lda 6,s               ; saved full A, including the hidden high byte
    plp                   ; restore guest carry/overflow and 8-bit M/X
.a8
.i8
    rts

.macro QuickZpxHandler name, operation
name:
.a16
.i16
    jsr PrepareQuickZpx
.a8
.i8
    operation a:$0000,x
    jmp QuickZpxDone
.endmacro
QuickZpxHandler QuickLDA, lda
QuickZpxHandler QuickLDY, ldy
QuickZpxHandler QuickSTA, sta
QuickZpxHandler QuickAND, and
QuickZpxHandler QuickORA, ora
QuickZpxHandler QuickEOR, eor
QuickZpxHandler QuickADC, adc
QuickZpxHandler QuickSBC, sbc
QuickZpxHandler QuickCMP, cmp
QuickZpxHandler QuickASL, asl
QuickZpxHandler QuickLSR, lsr
QuickZpxHandler QuickROL, rol
QuickZpxHandler QuickROR, ror
QuickZpxHandler QuickINC, inc
QuickZpxHandler QuickDEC, dec

; Pure RAM / original-ROM indirect reads can execute directly too. All
; hardware and cartridge-RAM addresses fall back to the existing I/O handler.
PrepareQuickIndirect:
.a16
.i16
    lda 8,s               ; PC with the helper JSR frame on the stack
    dec a
    tax
    lda a:$0000,x         ; MUST be absolute: direct-page would ignore DBR
    and #$00FF
    tax
    cpx #$00FF
    beq @wrap
    lda a:$0000,x
    bra @pointer
@wrap:
    sep #$20
.a8
    lda a:$0000
    xba
    lda a:$00FF
    rep #$20
.a16
@pointer:
    sta EA
    tya
    clc
    adc EA
    cmp #$2000
    bcc @ram
    cmp #$8000
    bcs @safe
    ; Remove this helper's JSR return before the generic entry pops A/X.
    pla
    jmp CopGeneric
@ram:
    and #$07FF
@safe:
    tax
    inc $0968
    bne :+
    inc $096A
:
    inc $0960
    bne :+
    inc $0962
:
    sep #$20
.a8
    lda 7,s
    and #$EF              ; retain 16-bit address X during the native load
    pha
    rep #$20
.a16
    lda 6,s
    plp
.a8
.i16
    rts
.macro QuickIndirectHandler name, operation
name:
.a16
.i16
    jsr PrepareQuickIndirect
.a8
.i16
    operation a:$0000,x
    jmp QuickZpxDone
.endmacro
; LDA does not consume the old A/C/V. Avoid a restore/execute/save round trip
; for this common read, but merge only N/Z into the real guest status frame.
.if USE_SPECIALIZED_INDIRECT_LDA
QuickLDA_IY:
.a16
.i16
    lda 6,s
    dec a
    tax
    lda a:$0000,x
    and #$00FF
    tax
    cpx #$00FF
    beq @wrap
    lda a:$0000,x
    bra @pointer
@wrap:
    sep #$20
.a8
    lda a:$0000
    xba
    lda a:$00FF
    rep #$20
.a16
@pointer:
    sta EA
    tya
    clc
    adc EA
    cmp #$2000
    bcc @ram
    cmp #$8000
    bcs @safe
    jmp CopGeneric
@ram:
    and #$07FF
@safe:
    tax
    inc $0968
    bne :+
    inc $096A
:
    inc $0960
    bne :+
    inc $0962
:
    sep #$20
.a8
    lda a:$0000,x
    sta 3,s                 ; preserve the original hidden high byte of A
    php
    pla
    and #$82
    sta TMP
    lda 5,s
    and #$7D
    ora TMP
    sta 5,s
    rep #$30
.a16
.i16
    plx
    pla
    rti
.else
QuickIndirectHandler QuickLDA_IY, lda
.endif
QuickIndirectHandler QuickCMP_IY, cmp
QuickIndirectHandler QuickSBC_IY, sbc
QuickIndirectHandler QuickADC_IY, adc
QuickIndirectHandler QuickAND_IY, and
QuickIndirectHandler QuickORA_IY, ora
QuickIndirectHandler QuickEOR_IY, eor

.include "native_indexed.inc"

; Narrow I/O fast paths implement exactly the existing supported semantics.
; Any other absolute address returns to the generic compatibility handler.
QuickLDA_ABS:
.a16
.i16
    lda 6,s
    dec a
    tax
    lda a:$0000,x
    cmp #$4016
    beq @joy
    cmp #$4017
    beq @joy2
    cmp #$2002
    beq @status
    cmp #$5204
    beq @irq
    jmp CopGeneric
@joy:
    jsr CountQuickIo
    sep #$20
.a8
    lda JOYSHIFT
    and #$01
    ora #$40
    sta 3,s
    lda STROBE
    bne @read
    lda JOYSHIFT
    lsr a
    ora #$80
    sta JOYSHIFT
@read:
    lda 3,s
    bra QuickReadResult
@joy2:
.a16
    jsr CountQuickIo
    sep #$20
.a8
    lda #$40
    bra QuickReadResult
@status:
.a16
    jsr CountQuickIo
    sep #$20
.a8
    lda STATUS
    and #$E0
    sta TMP
    lda PPUBUS
    and #$1F
    ora TMP
    sta 3,s
    lda STATUS
    and #$7F
    sta STATUS
    stz LATCH
    lda 3,s
    sta PPUBUS
    bra QuickReadResult
@irq:
.a16
    jsr CountQuickIo
    sep #$20
.a8
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
QuickReadResult:
.a8
.i16
    sta 3,s
    cmp #$00
    php
    pla
    and #$82
    sta TMP
    lda 5,s
    and #$7D
    ora TMP
    sta 5,s
    jmp QuickAbsReturn

QuickSTA_ABS:
.a16
.i16
    lda 6,s
    dec a
    tax
    lda a:$0000,x
    cmp #$5115
    beq @primary
    cmp #$5116
    beq @cbank
    cmp #$5117
    beq @fixed
.if USE_QUICK_PPU
    cmp #$2000
    bcc @fallback
    cmp #$4000
    jcc QuickPpuStore
.endif
    cmp #$5100
    bcc @fallback
    cmp #$512C
    jcc QuickMapperRegister
@fallback:
    jmp CopGeneric
@primary:
    jsr CountQuickIo
    sep #$20
.a8
    lda 3,s
    sta f:$7E5115
    and #$1E
    lsr a
    sta TMP
    lda SLOT
    and #$10
    ora TMP
    sta SLOT
    bra @update
@cbank:
    sep #$20
.a8
    lda 3,s
    and #$1F
    cmp #$1E
    beq @thirty
    cmp #$07
    bne @unsupported
    lda SLOT
    ora #$10
    sta SLOT
    bra @storec
@thirty:
    lda SLOT
    and #$0F
    sta SLOT
@storec:
    lda 3,s
    sta f:$7E5116
    rep #$20
.a16
    jsr CountQuickIo
    sep #$20
.a8
@update:
    jsr UpdateBanks
    lda RAWBANK
    pha
    plb
    jmp QuickAbsReturn
@fixed:
.a16
    sep #$20
.a8
    lda 3,s
    and #$1F
    cmp #$1F
    bne @unsupported
    lda 3,s
    sta f:$7E5117
    rep #$20
.a16
    jsr CountQuickIo
    jmp QuickAbsReturn
@unsupported:
    rep #$30
.a16
.i16
    jmp CopGeneric

; Ordinary mapper register backing, excluding the three live bank selectors
; already dispatched above. Preserve the last CHR-register set side effect.
QuickMapperRegister:
.a16
.i16
    tax
    cmp #$5120
    bcc @value
    and #$0008
    sep #$20
.a8
    sta LASTCHR
@value:
    sep #$20
.a8
    lda 3,s
    sta f:$7E0000,x
    rep #$20
.a16
    jsr CountQuickIo
    jmp QuickAbsReturn

.if USE_QUICK_PPU
; A holds the original CPU address. Reuse the existing PPU write semantics
; without materializing/interpreting a complete generic COP context. The
; original register saves and hardware COP return frame remain on the stack.
QuickPpuStore:
.a16
.i16
    and #$0007
    asl a
    tax
    inc $0970
    bne :+
    inc $0972
:
    jsr CountQuickIo
    phy
    phd
    phb
    lda #$0800
    tcd
    sep #$20
.a8
    lda #$00
    pha
    plb
    lda #$01
    sta COPBUSY
    lda 8,s               ; saved guest A after Y, D and DBR saves
    sta VAL
    sta PPUBUS
    jsr (PpuWriters,x)
    sep #$20
.a8
    stz COPBUSY
    plb
    pld
    rep #$10
.i16
    ply
    jmp QuickAbsReturn
.endif

CountQuickIo:
.a16
.i16
    inc $096C
    bne :+
    inc $096E
:
    inc $0960
    bne :+
    inc $0962
:
    rts
QuickAbsReturn:
    sep #$20
.a8
    lda CODEBANK
    sta 8,s               ; bank writes must also change the saved return PBR
    rep #$30
.a16
.i16
    lda 6,s
    inc a                 ; COP consumed 2 bytes; original absolute op used 3
    sta 6,s
    plx
    pla
    rti

QuickZpxDone:
.a8
.i8
    php
    rep #$30
.a16
.i16
    sta 4,s               ; return the resulting full accumulator
    sep #$20
.a8
    pla
    ora #$30              ; guest always returns to 8-bit M/X
    sta 5,s               ; let RTI restore the operation's actual result flags
    rep #$30
.a16
.i16
    plx
    pla
    rti
.endif

; NMOS indexed bus accesses perform an intermediate read before every
; store/RMW, and before page-crossing reads. Reads of PPU/joypad/IRQ registers
; can have effects even when their value is discarded. Ignore ordinary RAM/ROM
; dummy reads here: this bridge has no cycle-accurate bus or MMC5 PCM-read mode.
; Called only for abs,X / abs,Y / (zp),Y after INDEXBASE and EA are known.
IndexedDummyRead:
.a16
.i16
    lda OPER
    and #$00FF
    cmp #$0004
    bcc @read
    cmp #$0007
    bcc @dummy              ; STA/STX/STY (only legal modes can reach here)
    cmp #$0010
    bcs @dummy              ; read-modify-write
@read:
    lda EA
    eor INDEXBASE
    and #$FF00
    beq @done
@dummy:
    lda EA
    and #$00FF
    sta DUMMYADDR
    lda INDEXBASE
    and #$FF00
    ora DUMMYADDR
    cmp #$2000
    bcc @done
    cmp #$4000
    bcc @effect
    cmp #$4015
    beq @effect
    cmp #$4016
    beq @effect
    cmp #$4017
    beq @effect
    cmp #$5204
    bne @done
@effect:
    pha
    lda EA
    pha
    lda 3,s
    sta EA
    inc $0998
    bne :+
    inc $099A
:
    jsr ReadValue
    rep #$30
.a16
.i16
    pla
    sta EA
    pla
@done:
    rts

; Read a guest address, with no read of real SNES registers by guest code.
ReadValue:
    rep #$20
.a16
    lda EA
    cmp #$2000
    bcc @raw
    cmp #$4000
    jcc ReadPpu
.if USE_AUDIO_COUNTERS
    cmp #$4015
    beq @apu_status
.endif
    cmp #$4016
    jeq ReadJoy
    cmp #$4017
    jeq ReadJoy2
    cmp #$5204
    jeq ReadIrqStatus
@raw:
    sep #$20
.a8
    lda [MEM]
    rts
.if USE_AUDIO_COUNTERS
@apu_status:
    sep #$20
.a8
    jmp ApuReadStatus
.endif
ReadJoy:
    sep #$20
.a8
    lda JOYSHIFT
    and #$01
    ora #$40
    pha
    lda STROBE
    bne @held
    lda JOYSHIFT
    lsr a
    ora #$80
    sta JOYSHIFT
@held:
    pla
    rts
ReadJoy2:
    sep #$20
.a8
    lda #$40
    rts
ReadIrqStatus:
    sep #$20
.a8
    lda $4212
    and #$80
    beq @inframe
    lda #$00
    bra @pending
@inframe:
    lda #$40
@pending:
    ora IRQPENDING
    stz IRQPENDING
    rts
ReadPpu:
.a16
    and #$0007
    cmp #$0002
    beq @status
    cmp #$0007
    jeq ReadPpuData
    sep #$20
.a8
    lda PPUBUS
    rts
@status:
    sep #$20
.a8
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
    rts

WriteValue:
    rep #$20
.a16
    lda EA
    cmp #$2000
    bcc @raw
    cmp #$4000
    jcc WritePpu
    cmp #$4014
    jeq WriteOamDma
    cmp #$4016
    jeq WriteJoy
.if USE_AUDIO_COUNTERS
    cmp #$4018
    jcc ApuWriteFromContext
.endif
    cmp #$5115
    jeq WritePrimary
    cmp #$5116
    jeq WriteCbank
    cmp #$5117
    jeq WriteFixed
    cmp #$5203
    jeq WriteIrqPos
    cmp #$5204
    jeq WriteIrqEnable
    cmp #$5120
    bcc @raw
    cmp #$512C
    bcs @raw
    sep #$20
.a8
    lda EA
    and #$08
    sta LASTCHR
@raw:
    rep #$20
.a16
    lda EA
    cmp #$5C00
    bcc @store
    cmp #$6000
    bcs @store
    jsr MarkPhysicalRow
@store:
    sep #$20
.a8
    lda VAL
    sta [MEM]
    rts
WriteFixed:
    sep #$20
.a8
    lda VAL
    and #$1F
    cmp #$1F
    jne BadBank
    lda VAL
    sta f:$7E5117
    rts
WritePrimary:
    sep #$20
.a8
    lda VAL
    sta f:$7E5115
    and #$1E
    lsr a
    sta TMP
    lda SLOT
    and #$10
    ora TMP
    sta SLOT
    bra UpdateBanks
WriteCbank:
    sep #$20
.a8
    lda VAL
    sta f:$7E5116
    and #$1F
    cmp #$1E
    beq @thirty
    cmp #$07
    jne BadBank
    lda SLOT
    ora #$10
    sta SLOT
    bra UpdateBanks
@thirty:
    lda SLOT
    and #$0F
    sta SLOT
UpdateBanks:
    lda SLOT
    clc
    adc #$81
    sta RAWBANK
    clc
    adc #$20
    sta CODEBANK
    rts
WriteIrqPos:
    sep #$20
.a8
    lda VAL
    sta IRQPOS
    sta f:$7E5203
    rts
WriteIrqEnable:
    sep #$20
.a8
    lda VAL
    and #$80
    sta IRQENABLE
    sta f:$7E5204
    rts

WriteOamDma:
    sep #$20
.a8
    lda VAL
    cmp #$20
    bcs @genericcopy
    ; MVN safely copies WRAM to WRAM; SNES DMA cannot do that transfer.
    ; Mirror NES RAM pages before selecting the 256-byte source block.
    rep #$30
.a16
.i16
    lda VAL
    and #$0007
    xba
    tax
    ldy #$3800
    lda #$00FF
    mvn #$7E,#$7E
    sep #$20
.a8
    lda #$00
    pha
    plb                    ; MVN changed DBR to its destination bank
    rts
@genericcopy:
    lda VAL
    sta $0821
    stz $0820
    lda RAWBANK
    sta $0822
    lda VAL
    cmp #$20
    bcs @copy
    and #$07
    sta $0821
    lda #$7E
    sta $0822
@copy:
    rep #$20
.a16
    ldy #$0000
@loop:
    lda [PTR],y
    tyx
    sta f:$7E3800,x
    iny
    iny
    cpy #$0100
    bne @loop
    sep #$20
.a8
    rts
WriteJoy:
    sep #$20
.a8
    lda VAL
    and #$01
    sta STROBE
    jeq @done
.if TEST_INPUT_REPLAY
    ; Test-only input is indexed by logical guest frame, not host timing.
    ; This block is absent from ordinary interactive builds.
    rep #$20
.a16
    lda GFRAMES
    cmp #REPLAY_LENGTH
    bcs @replayend
    tax
    sep #$20
.a8
    lda f:$800000+InputReplay,x
    bra @replayvalue
@replayend:
    sep #$20
.a8
    lda #$00
@replayvalue:
    sta JOYLATCH
    sta JOYSHIFT
    rts
.endif
    rep #$20
.a16
    lda $4218
    sta $0828
    stz JOYLATCH
.macro joybit mask, bit
    lda $0828
    and #mask
    beq :+
    lda JOYLATCH
    ora #bit
    sta JOYLATCH
:
.endmacro
    joybit $0080,$0001
    joybit $C000,$0002
    joybit $2000,$0004
    joybit $1000,$0008
    joybit $0800,$0010
    joybit $0400,$0020
    joybit $0200,$0040
    joybit $0100,$0080
    sep #$20
.a8
    lda JOYLATCH
    sta JOYSHIFT
@done:
    rts

WritePpu:
.a16
    and #$0007
    asl a
    tax
    sep #$20
.a8
    lda VAL
    sta PPUBUS
    jmp (PpuWriters,x)
PpuWriters:
    .word WriteCtrl,WriteMask,WriteIgnore,WriteOaddr,WriteOdata,WriteScroll,WriteAddr,WritePpuData
WriteIgnore:
    rts
WriteCtrl:
    sta CTRL
    rep #$20
.a16
    and #$0003
    xba
    asl a
    asl a
    sta $0826
    lda TEMPV
    and #$F3FF
    ora $0826
    sta TEMPV
    sep #$20
.a8
    rts
WriteMask:
    sta MASK
    rts
WriteOaddr:
    sta OADDR
    rts
WriteOdata:
    rep #$20
.a16
    lda OADDR
    and #$00FF
    tax
    sep #$20
.a8
    lda VAL
    sta f:$7E3800,x
    inc OADDR
    rts
WriteScroll:
    lda LATCH
    bne @second
    inc LATCH
    lda VAL
    and #$07
    sta FINEX
    lda VAL
    lsr a
    lsr a
    lsr a
    rep #$20
.a16
    and #$001F
    sta $0826
    lda TEMPV
    and #$FFE0
    ora $0826
    sta TEMPV
    sep #$20
.a8
    rts
@second:
    stz LATCH
    rep #$20
.a16
    lda VAL
    and #$00F8
    asl a
    asl a
    sta $0826
    lda VAL
    and #$0007
    xba
    asl a
    asl a
    asl a
    asl a
    ora $0826
    sta $0826
    lda TEMPV
    and #$8C1F
    ora $0826
    sta TEMPV
    sep #$20
.a8
    rts
WriteAddr:
    lda LATCH
    bne @second
    inc LATCH
    lda VAL
    and #$3F
    sta TEMPV+1
    rts
@second:
    stz LATCH
    lda VAL
    sta TEMPV
    rep #$20
.a16
    lda TEMPV
    sta VRAMV
.if USE_RASTER_SCROLL
    pha
    sep #$20
.a8
    lda RUNNING
    beq @noraster
    lda IRQCOUNT
    beq @noraster
    lda LASTIRQ
    sta RASTER_LINE
    lda #$01
    sta RASTER_VALID
    rep #$20
.a16
    pla
    sta RASTER_V
    bra @rasterdone
@noraster:
    rep #$20
.a16
    pla
@rasterdone:
.endif
    sep #$20
.a8
    rts

; Resolve PPU nametable/palette address to a long pointer. C set for fill/CHR.
ResolveVram:
    rep #$20
.a16
    lda VRAMV
    and #$3FFF
    sta PADDR
    cmp #$2000
    jcc @chr
    cmp #$3F00
    bcs @palette
    and #$0FFF
    xba
    lsr a
    lsr a
    and #$0003
    asl a
    tax
    sep #$20
.a8
    lda f:$7E5105
@shift:
    cpx #$0000
    beq @route
    lsr a
    dex
    bra @shift
@route:
    and #$03
    cmp #$03
    beq @fill
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda VramBases,x
    sta $0820
    lda PADDR
    and #$03FF
    clc
    adc $0820
    sta $0820
    sep #$20
.a8
    lda #$7E
    sta $0822
    clc
    rts
@palette:
.a16
    and #$001F
    sta $0820
    and #$0013
    cmp #$0010
    bne @paladdr
    lda $0820
    and #$000F
    sta $0820
@paladdr:
    lda $0820
    ora #$3F00
    sta $0820
    sep #$20
.a8
    lda #$7E
    sta $0822
    clc
    rts
@fill:
    sep #$20
.a8
    sec
    rts
@chr:
    sep #$20
.a8
    sec
    rts
VramBases:
    .word $3000,$3400,$5C00
AdvanceVram:
    rep #$20
.a16
    lda CTRL
    and #$0004
    beq @one
    lda #$0020
    bra @advance
@one:
    lda #$0001
@advance:
    clc
    adc VRAMV
    and #$7FFF
    sta VRAMV
    sep #$20
.a8
    rts
WritePpuData:
    jsr ResolveVram
    bcs @ignore
    lda [PTR]
    cmp VAL
    beq @ignore
    rep #$20
.a16
    lda $0820
    jsr MarkPhysicalRow
    sep #$20
.a8
    lda VAL
    sta [PTR]
@ignore:
    jsr AdvanceVram
    rts
ReadPpuData:
    jsr ResolveVram
    bcs @special
    lda [PTR]
    bra @buffer
@special:
    rep #$20
.a16
    lda PADDR
    cmp #$2000
    bcc @readchr
    and #$03FF
    cmp #$03C0
    bcs @attr
    sep #$20
.a8
    lda f:$7E5106
    bra @buffer
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
    bra @buffer
@readchr:
    jsr ReadChr
@buffer:
    sta TMP
    rep #$20
.a16
    lda PADDR
    cmp #$3F00
    bcs @immediate
    sep #$20
.a8
    lda RDBUF
    pha
    lda TMP
    sta RDBUF
    bra @advance
@immediate:
    sep #$20
.a8
    lda TMP
    pha
@advance:
    jsr AdvanceVram
    pla
    sta PPUBUS
    rts
ReadChr:
.a16
    ; Raw CHR begins at LoROM bank $CD, 32 one-KiB pages per bank.
    lda PADDR
    xba
    lsr a
    lsr a
    and #$0007
    tax
    sep #$20
.a8
    lda CTRL
    and #$20
    beq @sprite
    lda LASTCHR
    beq @sprite
    rep #$20
.a16
    txa
    and #$0003
    tax
    sep #$20
.a8
    lda f:$7E5128,x
    bra @bank
@sprite:
    lda f:$7E5120,x
@bank:
    and #$7F
    sta TMP
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc #$CD
    sta $0822
    rep #$20
.a16
    lda TMP
    and #$001F
    xba
    asl a
    asl a
    ora #$8000
    sta $0820
    lda PADDR
    and #$03FF
    ora $0820
    sta $0820
    sep #$20
.a8
    lda [PTR]
    rts

; Host NMI runs a complete original NMI and then bounded virtual scanline IRQs.
; This first bridge is frame-scheduled, not cycle/scanline-exact emulation.
Nmi:
.if USE_FASTROM
    jml $800000+NmiFast
NmiFast:
.endif
    php
    rep #$20
.a16
    pha
    lda f:HFRAMES
    inc a
    sta f:HFRAMES
    sep #$20
.a8
    lda f:STATUS
    ora #$80
    sta f:STATUS
    lda f:$004210
    lda f:RUNNING
    ora f:COPBUSY
    bne @quick
    ; Reject interrupts in host code BEFORE touching NCTX. In particular,
    ; RUNNING has cleared during NmiRestore but the guest context is still live.
    ; Saved PBR is 7,S after PHP + the full accumulator push above.
    lda 7,s
    cmp #$A1
    bcc @quick
    cmp #$C1
    bcs @quick
    ; A WRAM veneer is an atomic guest operation. Never rewrite its saved
    ; PBR from CODEBANK: a bank-switch veneer may already target $C0, where
    ; that same WRAM PC is not mirrored. Preserve the real interrupt frame.
    rep #$20
.a16
    lda 5,s
    bpl @quick
    pla
    plp
    jmp NmiFull
@quick:
    rep #$20
.a16
    pla
    plp
    rti
NmiFull:
    rep #$30
.a16
.i16
    sta f:NCTX
    txa
    sta f:NCTX+2
    tya
    sta f:NCTX+4
    tdc
    sta f:NCTX+6
    tsc
    sta f:NCTX+8
    lda 2,s
    sta f:NCTX+10
    sep #$20
.a8
    lda 1,s
    sta f:NCTX+12
    lda 4,s
    sta f:NCTX+13
    phb
    pla
    sta f:NCTX+14
    rep #$20
.a16
    ldx #$1E00
    txs
    lda #$0000
    tcd
    sep #$20
.a8
    pha
    plb
    lda CTRL
    and #$80
    jeq NmiRestore
    lda NCTX+13
    cmp #$A1
    jcc NmiRestore
    cmp #$C1
    jcs NmiRestore
    .if USE_DIRECT_CALLS
    ; A guest NMI must not split a multi-instruction WRAM veneer or change
    ; its return bank while it is running. Resume it after this host NMI.
    rep #$20
.a16
    lda NCTX+10
    bmi :+
    sep #$20
.a8
    jmp NmiRestore
:
    sep #$20
.a8
    .endif
    lda #$01
    sta RUNNING
.if USE_PIPELINED_VIDEO
    jsr PresentPendingFrame
.endif
    rep #$20
.a16
    inc GFRAMES
    lda NCTX+8
    clc
    adc #$0004
    tcs
    sep #$20
.a8
    lda #($80*USE_FASTROM)
    pha
    rep #$20
.a16
    lda #.loword(GuestNmiReturn)
    pha
    sep #$20
.a8
    lda #$34
    pha
    lda CODEBANK
    sta $09F2
    lda RAWBANK
    pha
    plb
    rep #$30
.a16
    lda #GUEST_NMI
    sta f:$09F0
    lda f:NCTX+2
    tax
    lda f:NCTX+4
    tay
    lda f:NCTX
    sep #$30
.a8
.i8
    jmp [$09F0]
GuestNmiReturn:
    rep #$30
.a16
.i16
    ldx #$1E00
    txs
    lda #$0000
    tcd
    sep #$20
.a8
    pha
    plb
    stz IRQCOUNT
    stz LASTIRQ
    jsr CaptureTop
NextGuestIrq:
    lda IRQENABLE
    jeq AfterGuestIrqs
    lda IRQPOS
    jeq AfterGuestIrqs
    cmp #$F0
    jcs AfterGuestIrqs
    cmp LASTIRQ
    jcc AfterGuestIrqs
    jeq AfterGuestIrqs
    sta LASTIRQ
    inc IRQCOUNT
    lda IRQCOUNT
    cmp #$09
    jcs AfterGuestIrqs
    lda #$80
    sta IRQPENDING
    rep #$20
.a16
    inc IFRAMES
    lda NCTX+8
    clc
    adc #$0004
    tcs
    sep #$20
.a8
    lda #($80*USE_FASTROM)
    pha
    rep #$20
.a16
    lda #.loword(GuestIrqReturn)
    pha
    sep #$20
.a8
    lda #$34
    pha
    lda CODEBANK
    sta $09F2
    lda RAWBANK
    pha
    plb
    rep #$30
.a16
    lda #GUEST_IRQ
    sta f:$09F0
    lda #$0000
    ldx #$0000
    ldy #$0000
    sep #$30
.a8
.i8
    jmp [$09F0]
GuestIrqReturn:
    rep #$30
.a16
.i16
    ldx #$1E00
    txs
    lda #$0000
    tcd
    sep #$20
.a8
    pha
    plb
    jsr CaptureSplit
    jmp NextGuestIrq
AfterGuestIrqs:
    .if USE_AUDIO_COUNTERS
    jsr ApuFrame
    .endif
    .if USE_EXPERIMENTAL_AUDIO
    jsr AudioFrame
    .endif
    jsr RenderFrame
    stz RUNNING
.if TEST_NMI_RESTORE_STRESS
    ; TEST ONLY: force multiple host NMIs in the context-restoration window.
    ; Ordinary builds contain none of this deliberate delay.
    rep #$10
.i16
    ldx #$FFFF
@restore_delay:
    dex
    bne @restore_delay
.endif
NmiRestore:
    rep #$30
.a16
.i16
    ldx NCTX+8
    lda NCTX+10
    sta f:$7E0002,x
    sep #$20
.a8
    lda NCTX+12
    sta f:$7E0001,x
    lda NCTX+13
    cmp #$A1
    bcc @savedbank
    cmp #$C1
    bcs @savedbank
    lda CODEBANK
    sta f:$7E0004,x
    lda RAWBANK
    bra @dbr
@savedbank:
    sta f:$7E0004,x
    lda NCTX+14
@dbr:
    pha
    plb
    rep #$30
.a16
    lda f:NCTX+8
    tcs
    lda f:NCTX+6
    tcd
    lda f:NCTX+2
    tax
    lda f:NCTX+4
    tay
    lda f:NCTX
    rti

.include "native_apu.inc"
.include "native_audio.inc"
.include "native_direct.inc"
.include "native_video.inc"

BadOperation:
    sep #$20
.a8
    lda #$02
    sta f:FAULTCODE
    rep #$20
.a16
    lda f:$0810
    sta f:FAULTPC
    sep #$20
.a8
    lda f:SB
    sta f:FAULTBANK
    jmp FaultDisplay
BadBank:
    lda #$03
    sta f:FAULTCODE
    rep #$20
.a16
    lda f:$0810
    sta f:FAULTPC
    sep #$20
.a8
    lda f:SB
    sta f:FAULTBANK
    jmp FaultDisplay
Fault:
    rep #$20
.a16
    lda 2,s
    sec
    sbc #$0002
    sta f:FAULTPC
    sep #$20
.a8
    lda 4,s
    sta f:FAULTBANK
    lda #$01
    sta f:FAULTCODE
FaultDisplay:
    lda #$00
    pha
    plb
    stz $4200
    stz $420C
    lda #$80
    sta $2100
    stz $212C
    stz $2121
    lda #$1F
    sta $2122
    stz $2122
    lda #$0F
    sta $2100
@halt:
    wai
    bra @halt
Irq:
    rti
.segment "RODATA"
Zero: .byte 0
.if USE_QUICK_DISPATCH
QuickZpTable:
.include "quick-zp-table.inc"
.endif
OperationTable: .incbin "operation.bin"
ModeTable: .incbin "mode.bin"
LengthTable: .incbin "length.bin"
RgbPalette: .incbin "palette.bin"
.if USE_RASTER_SCROLL
BlankChrBanks: .incbin "blank-chr.bin"
.endif
.if TEST_INPUT_REPLAY
InputReplay: .incbin "input-replay.bin"
.endif
.segment "HEADER"
    .byte "NES2SNES NATIVE TEST "
    .byte ($20+$10*USE_FASTROM),$00,$0C,$00,$01,$00,$00
    .word $FFFF,$0000
.segment "VECTOR"
    .word $0000,$0000,CopHandler,Fault,Fault,Nmi,$0000,Irq
    .word $0000,$0000,CopHandler,$0000,Fault,Nmi,Reset,Irq
