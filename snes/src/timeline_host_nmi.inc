; Native SNES NMI envelope for the procedural timeline (not native.s).
; Hardware owns P/PC/PBR stacking. Save FULL A/X/Y before changing their widths
; back, plus D/DBR. Snapshot live GC/GI/GT, capture cursor and capture header on
; the native stack; a nested invocation gets its own snapshot automatically.
;
; HostWork must keep native mode and balance its stack. It may use the protected
; scratch below, but MUST NOT write guest $0000..$01FF, output bank $7F, the host
; stack, or HN metadata except its designated counters. HostWork returns within
; the caller's measured stack/time bounds. This is not an arbitrary ISR sandbox.
; Native stack must have 160 free bytes PER nesting level plus worker call use.
; HN metadata $1D00..$1D1F is disjoint, initialized before enabling NMI.
HN_COUNT=$1D00                 ; serviced host NMIs, u32
HN_DEPTH=$1D04
HN_PEAK=$1D05
HN_FAULT=$1D06                 ; excessive nesting fails the whole run
HN_NEST=$1D07
HN_WAITS=$1D08                 ; interruptions at the deliberate WAI return PC
HN_NEST_WAITS=$1D0A
HN_WORK=$1D0C                  ; completed worker calls, u32
.segment "CODE"
.proc TimelineHostNMI
    rep #$30
.a16
.i16
    pha
    phx
    phy
    phd
    phb
    cld
    lda #0
    tcd
    sep #$20
.a8
    pha
    plb
    lda f:$004210              ; acknowledge the actual SNES NMI source
    lda HN_DEPTH
    cmp #2
    bcc admitted
    lda #1
    sta HN_FAULT
    jmp restore_registers
admitted:
    inc HN_DEPTH
    lda HN_DEPTH
    cmp HN_PEAK
    bcc :+
    sta HN_PEAK
:
    rep #$20
.a16
    inc HN_COUNT
    bne :+
    inc HN_COUNT+2
:
    ; Nine software-saved bytes precede hardware P, PC(lo/hi), PBR.
    lda 11,s
    cmp #HostExpectedResume
    bne :+
    inc HN_WAITS
:
    lda 11,s
    cmp #HostNestedResume
    bne :+
    inc HN_NEST_WAITS
:
    ldx #0
save_gc_gi:
    lda f:$7E1840,x
    pha
    inx
    inx
    cpx #64
    bne save_gc_gi
    ldx #0
save_gt:
    lda f:$7E18C0,x
    pha
    inx
    inx
    cpx #32
    bne save_gt
    ldx #0
save_cursor:
    lda f:$7E1B02,x
    pha
    inx
    inx
    cpx #4
    bne save_cursor
    ldx #0
save_capture:
    lda f:$7E1C00,x
    pha
    inx
    inx
    cpx #32
    bne save_capture
    tsc
    ldx $1D1E
    beq new_minimum
    cmp $1D1E
    bcs minimum_done
new_minimum:
    sta $1D1E
minimum_done:
    jsr TimelineHostWork
    ; The worker may return with changed M/X, D, DBR or decimal mode.
    rep #$30
.a16
.i16
    cld
    ldx #30
restore_capture:
    pla
    sta f:$7E1C00,x
    dex
    dex
    bpl restore_capture
    ldx #2
restore_cursor:
    pla
    sta f:$7E1B02,x
    dex
    dex
    bpl restore_cursor
    ldx #30
restore_gt:
    pla
    sta f:$7E18C0,x
    dex
    dex
    bpl restore_gt
    ldx #62
restore_gc_gi:
    pla
    sta f:$7E1840,x
    dex
    dex
    bpl restore_gc_gi
    sep #$20
.a8
    lda f:$7E1D04
    dec a
    sta f:$7E1D04
restore_registers:
    rep #$30
.a16
.i16
    plb
    pld
    ply
    plx
    pla
    rti
.endproc
