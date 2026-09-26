; Coalesce adjacent dirty rows without adding any bytes to the transfer.
; Called with M=8, X=16, DBR=0, D=$0C00 by UploadPreparedFrame. Like the
; original uploader, this clobbers A/X/Y and DMA channel 0. VROW is scratch.
; Bottom rows and the HUD have disjoint source/destination ranges and are
; scanned separately; a clean row always terminates a run. Forced blank and
; the frame-ready ownership rules remain the caller's responsibility.
.if USE_COALESCED_NT_DMA
UploadNametablesCoalesced:
.a8
.i16
    lda UPLOAD_ANY
    bne @needed
    rts
@needed:
    stz UPLOAD_ANY
    lda #$7F
    sta $4304
    ldx #$0000
@bottom:
    lda UPLOAD,x
    beq @skipbottom
    txy
@bottomrun:
    stz UPLOAD,x
    inx
    cpx #$0080
    beq @sendbottom
    lda UPLOAD,x
    bne @bottomrun
@sendbottom:
    rep #$20
.a16
    sty VROW
    tya
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
    txa
    sec
    sbc VROW
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
    cpx #$0080
    bcc @bottom
    bra @tophud
@skipbottom:
    inx
    cpx #$0080
    bcc @bottom
@tophud:
    ldx #$0000
@top:
    lda UPLOAD+$80,x
    beq @skiptop
    txy
@toprun:
    stz UPLOAD+$80,x
    inx
    cpx #$0020
    beq @sendtop
    lda UPLOAD+$80,x
    bne @toprun
@sendtop:
    rep #$20
.a16
    sty VROW
    tya
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$2800
    sta $4302
    tya
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$3000
    sta $2116
    txa
    sec
    sbc VROW
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta $4305
    sep #$20
.a8
    lda #$01
    sta $420B
    cpx #$0020
    bcc @top
    rts
@skiptop:
    inx
    cpx #$0020
    bcc @top
    rts
.endif
