; Native BG/OBJ conversion of the LIVE guest state, not recorded frames.
; First renderer supports a single HUD/playfield split. Additional IRQ splits
; are counted as unsupported rather than claimed as visually faithful.
TOPCTRL=$0C00
TOPMASK=$0C01
TOPFINE=$0C02
TOPTEMP=$0C03
TOPMIRROR=$0C05
TOPLINE=$0C06
TOPCHR=$0C10
BGCHR=$0C20
NTBASE=$0C30
VROW=$0C32
VQUAD=$0C34
VROUTE=$0C36
VDESTBASE=$0C38
VFORCE=$0C3A
VGROUP=$0C3C
VFLAGS=$0C3E
VSRC=$80
VDST=$84
VAT=$88
VATVAL=$0C8C
VSPY=$0CA0
VSPX=$0CA2
VSPT=$0CA4
VSPF=$0CA6
VSPATTR=$0CA8
DIRTY=$0D00
OLDMIRROR=$0D70
OLDTOP=$0D71
BG_CACHE=$0D80
TOP_CACHE=$0D84
SPR_CACHE=$0D88
UPLOAD=$0E00
VIDEO_MULTISPLIT=$0CE0
BOTTOMEN=$0CE2
TOPEN=$0CE3

CaptureTop:
.a8
.i16
    lda CTRL
    sta TOPCTRL
    lda MASK
    sta TOPMASK
    lda FINEX
    sta TOPFINE
    lda f:$7E5105
    sta TOPMIRROR
    lda IRQENABLE
    beq @nosplit
    lda IRQPOS
    bra @line
@nosplit:
    lda #$00
@line:
    sta TOPLINE
    rep #$20
.a16
    lda TEMPV
    sta TOPTEMP
    sep #$20
.a8
    jsr SelectBgBanks
    rep #$20
.a16
    lda BGCHR
    sta TOPCHR
    lda BGCHR+2
    sta TOPCHR+2
    sep #$20
.a8
    rts
CaptureSplit:
.a8
.i16
    lda IRQCOUNT
    cmp #$02
    bcc @done
    rep #$20
.a16
    inc VIDEO_MULTISPLIT
    sep #$20
.a8
@done:
    rts
SelectBgBanks:
.a8
.i16
    ldx #$0000
    lda CTRL
    and #$20
    beq @small
@large:
    lda f:$7E5128,x
    and #$7F
    sta BGCHR,x
    inx
    cpx #$0004
    bne @large
    rts
@small:
    lda CTRL
    and #$10
    beq @first
    ldx #$0004
@first:
    ldy #$0000
@loop:
    lda f:$7E5120,x
    and #$7F
    sta BGCHR,y
    inx
    iny
    cpy #$0004
    bne @loop
    rts

; Called by guest writes with A16 containing a physical nametable address.
; D remains the COP scratch page. Other code uses only absolute variables here.
MarkPhysicalRow:
.a16
.i16
    pha
    and #$FC00
    cmp #$3000
    beq @zero
    cmp #$3400
    beq @one
    cmp #$5C00
    beq @two
    pla
    rts
@zero:
    ldy #$0000
    bra @offset
@one:
    ldy #$0020
    bra @offset
@two:
    ldy #$0040
@offset:
    pla
    and #$03FF
    cmp #$03C0
    bcs @attribute
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    sta $082A
    tya
    clc
    adc $082A
    tax
    sep #$20
.a8
    lda #$01
    sta DIRTY,x
    rep #$20
.a16
    rts
@attribute:
    and #$0038
    lsr a
    sta $082A
    tya
    clc
    adc $082A
    tax
    lda #$0101
    sta DIRTY,x
    sta DIRTY+2,x
    rts

RenderFrame:
.a8
.i16
    rep #$30
.a16
    lda #$0C00
    tcd
    sep #$20
.a8
    jsr SelectBgBanks
    ; Dirty physical nametable rows are expanded only when changed.
    lda f:$7E5105
    cmp OLDMIRROR
    beq @same
    sta OLDMIRROR
    lda #$01
    bra @force
@same:
    lda #$00
@force:
    sta VFORCE
    rep #$20
.a16
    stz VQUAD
@quad:
    lda VQUAD
    asl a
    tax
    sep #$20
.a8
    lda f:$7E5105
@shift:
    cpx #$0000
    beq @routed
    lsr a
    dex
    bra @shift
@routed:
    and #$03
    rep #$20
.a16
    and #$00FF
    sta VROUTE
    lda VQUAD
    xba
    asl a
    asl a
    asl a
    sta VDESTBASE
    jsr ConvertNametable
    inc VQUAD
    lda VQUAD
    cmp #$0004
    bne @quad
    ; BG2 is the selected top/HUD nametable. It has an independent CHR set.
    lda TOPTEMP
    xba
    lsr a
    lsr a
    and #$0003
    asl a
    tax
    sep #$20
.a8
    lda TOPMIRROR
@topshift:
    cpx #$0000
    beq @toproute
    lsr a
    dex
    bra @topshift
@toproute:
    and #$03
    cmp OLDTOP
    beq @topcached
    sta OLDTOP
    pha
    lda #$01
    sta VFORCE
    pla
    bra @topconvert
@topcached:
    pha
    stz VFORCE
    pla
@topconvert:
    rep #$20
.a16
    and #$00FF
    sta VROUTE
    lda #$2800
    sta VDESTBASE
    lda #$0004
    sta VQUAD
    jsr ConvertNametable
    ldx #$005E
    lda #$0000
@cleardirty:
    sta DIRTY,x
    dex
    dex
    bpl @cleardirty
    jsr ConvertObjects
    jsr ConvertPalette
    sep #$20
.a8
    ; Start from a known vblank boundary. No VRAM writes during active display.
@outblank:
    lda $4212
    bmi @outblank
@inblank:
    lda $4212
    bpl @inblank
    lda #$80
    sta $2100
    stz $420C
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    jsr UploadCharacters
    jsr UploadNametables
    jsr UploadObjectsPalette
    jsr SetVideoRegisters
    ; A large first upload may exceed vblank. Keep forced blank until another
    ; complete vblank instead of exposing a partially uploaded frame.
@finishblank:
    lda $4212
    bpl @finishblank
    lda MASK
    and #$18
    beq @remainblank
    lda #$0F
    sta $2100
@remainblank:
    rep #$20
.a16
    lda #$0000
    tcd
    sep #$20
.a8
    rts

; M=16, X=16. Convert only dirty rows of the selected physical/fill nametable.
ConvertNametable:
.a16
.i16
    stz VROW
    lda VROUTE
    cmp #$0003
    beq @fillbase
    asl a
    tax
    lda VramBases,x
    sta NTBASE
@fillbase:
@row:
    sep #$20
.a8
    lda VFORCE
    bne @convert
    rep #$20
.a16
    lda VROUTE
    cmp #$0003
    beq @next
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc VROW
    tax
    sep #$20
.a8
    lda DIRTY,x
    beq @next8
@convert:
    rep #$20
.a16
    jsr ConvertRow
    lda VQUAD
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc VROW
    tax
    sep #$20
.a8
    lda #$01
    sta UPLOAD,x
@next8:
    rep #$20
.a16
@next:
    inc VROW
    lda VROW
    cmp #$001E
    bne @row
    rts

ConvertRow:
.a16
.i16
    lda VROW
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc NTBASE
    sta $0C80
    lda VROW
    and #$001C
    asl a
    clc
    adc NTBASE
    clc
    adc #$03C0
    sta $0C88
    sep #$20
.a8
    lda #$7E
    sta $0C82
    sta $0C8A
    rep #$20
.a16
    lda VROW
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc VDESTBASE
    tax
    lda VROUTE
    cmp #$0003
    jeq FillRow
    ldy #$0000
    stz VGROUP
@group:
    sep #$20
.a8
    lda [VAT]
    sta VATVAL
    lda VROW
    and #$02
    beq @upper
    lda VATVAL
    lsr a
    lsr a
    lsr a
    lsr a
    sta VATVAL
@upper:
    lda VATVAL
    and #$03
    asl a
    asl a
    ora #$20
    sta VFLAGS+1
    stz VFLAGS
    rep #$20
.a16
    lda [VSRC],y
    and #$00FF
    ora VFLAGS
    sta f:$7F0000,x
    iny
    inx
    inx
    lda [VSRC],y
    and #$00FF
    ora VFLAGS
    sta f:$7F0000,x
    iny
    inx
    inx
    sep #$20
.a8
    lda VATVAL
    lsr a
    lsr a
    and #$03
    asl a
    asl a
    ora #$20
    sta VFLAGS+1
    rep #$20
.a16
    lda [VSRC],y
    and #$00FF
    ora VFLAGS
    sta f:$7F0000,x
    iny
    inx
    inx
    lda [VSRC],y
    and #$00FF
    ora VFLAGS
    sta f:$7F0000,x
    iny
    inx
    inx
    inc $0C88
    inc VGROUP
    lda VGROUP
    cmp #$0008
    jne @group
    rts
FillRow:
.a16
    lda f:$7E5107
    and #$0003
    xba
    asl a
    asl a
    ora #$2000
    sta VFLAGS
    lda f:$7E5106
    and #$00FF
    ora VFLAGS
    ldy #$0020
@loop:
    sta f:$7F0000,x
    inx
    inx
    dey
    bne @loop
    rts

ConvertObjects:
.a16
.i16
    lda #$2000
    sta $0C84
    sep #$20
.a8
    lda #$7F
    sta $0C86
    rep #$20
.a16
    ldx #$0000
    ldy #$0000
@object:
    lda f:$7E3800,x
    and #$00FF
    cmp #$00EF
    jcs @hidden
    sec
    sbc #$0007
    and #$00FF
    xba
    sta VSPY
    lda f:$7E3803,x
    and #$00FF
    ora VSPY
    sta VSPX
    lda f:$7E3802,x
    and #$00FF
    sta VSPATTR
    and #$0003
    asl a
    sta VSPF
    lda VSPATTR
    and #$00C0
    ora VSPF
    ora #$0030
    sta VSPF
    lda VSPATTR
    and #$0020
    beq @front
    lda VSPF
    and #$00DF
    sta VSPF
@front:
    lda CTRL
    and #$0020
    beq @small
    lda f:$7E3801,x
    and #$0001
    ora VSPF
    xba
    sta VSPF
    lda f:$7E3801,x
    and #$00FE
    sta VSPT
    lda VSPATTR
    and #$0080
    beq @normal
    inc VSPT
@normal:
    lda VSPX
    sta [VDST],y
    iny
    iny
    lda VSPT
    ora VSPF
    sta [VDST],y
    iny
    iny
    lda VSPX
    clc
    adc #$0800
    sta [VDST],y
    iny
    iny
    lda VSPT
    eor #$0001
    ora VSPF
    sta [VDST],y
    iny
    iny
    bra @next
@small:
    lda CTRL
    and #$0008
    lsr a
    lsr a
    lsr a
    ora VSPF
    xba
    sta VSPF
    lda f:$7E3801,x
    and #$00FF
    ora VSPF
    sta VSPT
    lda VSPX
    sta [VDST],y
    iny
    iny
    lda VSPT
    sta [VDST],y
    iny
    iny
    bra @hideone
@hidden:
    lda #$F000
    sta [VDST],y
    iny
    iny
    lda #$0000
    sta [VDST],y
    iny
    iny
@hideone:
    lda #$F000
    sta [VDST],y
    iny
    iny
    lda #$0000
    sta [VDST],y
    iny
    iny
@next:
    inx
    inx
    inx
    inx
    cpx #$0100
    jne @object
    rts

ConvertPalette:
.a16
.i16
    ldy #$0000
@entry:
    tya
    and #$0003
    bne @color
    lda f:$7E3F00
    bra @lookup
@color:
    tyx
    lda f:$7E3F00,x
@lookup:
    and #$003F
    asl a
    tax
    lda RgbPalette,x
    sta VFLAGS
    cpy #$0010
    bcs @sprite
    tya
    asl a
    tax
    lda VFLAGS
    sta f:$7F2300,x
    sta f:$7F2340,x
    bra @next
@sprite:
    tya
    and #$000C
    asl a
    asl a
    asl a
    ora #$0100
    sta VGROUP
    tya
    and #$0003
    asl a
    ora VGROUP
    tax
    lda VFLAGS
    sta f:$7F2300,x
@next:
    iny
    cpy #$0020
    bne @entry
    rts

UploadCharacters:
.a8
.i16
    ldy #$0000
@bg:
    lda BGCHR,y
    cmp BG_CACHE,y
    beq @bgskip
    sta BG_CACHE,y
    jsr BgDmaSource
    rep #$20
.a16
    tya
    xba
    asl a
    sta $2116
    lda #$0400
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
@bgskip:
    iny
    cpy #$0004
    bne @bg
    ldy #$0000
@top:
    lda TOPCHR,y
    cmp TOP_CACHE,y
    beq @topskip
    sta TOP_CACHE,y
    jsr BgDmaSource
    rep #$20
.a16
    tya
    xba
    asl a
    ora #$1000
    sta $2116
    lda #$0400
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
@topskip:
    iny
    cpy #$0004
    bne @top
    ldx #$0000
@sprite:
    lda f:$7E5120,x
    and #$7F
    cmp SPR_CACHE,x
    beq @sprskip
    sta SPR_CACHE,x
    pha
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc #$C5
    sta $4304
    pla
    rep #$20
.a16
    and #$000F
    xba
    asl a
    asl a
    asl a
    ora #$8000
    sta $4302
    txa
    xba
    asl a
    asl a
    ora #$4000
    sta $2116
    lda #$0800
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
@sprskip:
    inx
    cpx #$0008
    bne @sprite
    rts
BgDmaSource:
.a8
.i16
    pha
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc #$C1
    sta $4304
    pla
    rep #$20
.a16
    and #$001F
    xba
    asl a
    asl a
    ora #$8000
    sta $4302
    sep #$20
.a8
    rts

UploadNametables:
.a8
.i16
    lda #$7F
    sta $4304
    ldx #$0000
@bottom:
    lda UPLOAD,x
    beq @skip
    stz UPLOAD,x
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta $4302
    lsr a
    clc
    adc #$2000
    sta $2116
    lda #$0040
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
@skip:
    inx
    cpx #$0080
    bne @bottom
    ldx #$0000
@top:
    lda UPLOAD+$80,x
    beq @topskip
    stz UPLOAD+$80,x
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$2800
    sta $4302
    txa
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$3000
    sta $2116
    lda #$0040
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
@topskip:
    inx
    cpx #$0020
    bne @top
    rts

UploadObjectsPalette:
.a8
.i16
    stz $4300
    lda #$04
    sta $4301
    ldx #$2000
    stx $4302
    ldx #$0220
    stx $4305
    stz $2102
    stz $2103
    lda #$01
    sta $420B
    lda #$22
    sta $4301
    ldx #$2300
    stx $4302
    ldx #$0200
    stx $4305
    stz $2121
    lda #$01
    sta $420B
    rts

; Derive horizontal/vertical scroll from NES t/fine-x. 240/256-line vertical
; nametable wrapping and additional IRQ raster effects still require work.
SetVideoRegisters:
.a8
.i16
    stz $2105
    lda #$23
    sta $2107
    lda #$30
    sta $2108
    lda #$10
    sta $210B
    lda #$02
    sta $2101
    rep #$20
.a16
    lda TEMPV
    and #$001F
    asl a
    asl a
    asl a
    sta VFLAGS
    lda FINEX
    and #$0007
    ora VFLAGS
    sta VFLAGS
    lda TEMPV
    and #$0400
    lsr a
    lsr a
    ora VFLAGS
    sep #$20
.a8
    sta $210D
    xba
    sta $210D
    rep #$20
.a16
    lda TEMPV
    jsr VerticalOffset
    sep #$20
.a8
    sta $210E
    xba
    sta $210E
    rep #$20
.a16
    lda TOPTEMP
    and #$001F
    asl a
    asl a
    asl a
    sta VFLAGS
    lda TOPFINE
    and #$0007
    ora VFLAGS
    sep #$20
.a8
    sta $210F
    xba
    sta $210F
    rep #$20
.a16
    lda TOPTEMP
    and #$F7FF
    jsr VerticalOffset
    sep #$20
.a8
    sta $2110
    xba
    sta $2110
    stz BOTTOMEN
    stz TOPEN
    lda MASK
    and #$08
    beq @nobg
    lda #$01
    sta BOTTOMEN
    lda #$02
    sta TOPEN
@nobg:
    lda MASK
    and #$10
    ora BOTTOMEN
    sta BOTTOMEN
    lda MASK
    and #$10
    ora TOPEN
    sta TOPEN
    lda BOTTOMEN
    sta $212C
    lda TOPLINE
    cmp #$09
    bcc @nosplit
    cmp #$88
    bcs @nosplit
    sec
    sbc #$08
    sta f:$7F2500
    lda TOPEN
    sta f:$7F2501
    lda #$7F
    sta f:$7F2502
    lda BOTTOMEN
    sta f:$7F2503
    lda #$00
    sta f:$7F2504
    stz $4310
    lda #$2C
    sta $4311
    ldx #$2500
    stx $4312
    lda #$7F
    sta $4314
    lda #$02
    sta $420C
@nosplit:
    rts
VerticalOffset:
.a16
    sta VFLAGS
    and #$03E0
    lsr a
    lsr a
    sta VGROUP
    lda VFLAGS
    and #$7000
    xba
    lsr a
    lsr a
    lsr a
    lsr a
    ora VGROUP
    sta VGROUP
    lda VFLAGS
    and #$0800
    lsr a
    lsr a
    lsr a
    ora VGROUP
    clc
    adc #$0007
    rts
