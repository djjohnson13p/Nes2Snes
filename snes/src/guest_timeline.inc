; Integrated procedural timeline retirement. Not linked into native.s.
; Requires original PRE-instruction GC descriptor ($1840), actual post-execution
; state at GT, and immutable sorted TimelineEvents (cycle.u32, IRQ,NMI,0,0).
; Deadlines are evaluated AFTER instructions: this is the explicitly authored
; request-stream policy, NOT physical NES pin polling or PPU/mapper deadlines.
; Caller exclusively owns GC/GI/GT, original stack page, and helper scratch.
; Instruction semantics execute before this routine. Any fault stops acceptance;
; this routine does NOT roll back an already completed instruction.
GT=$18C0
; GT: time.u32, PC.u16, A,X,Y,P,S,IRQ,NMI,eventIndex,status,0,ordinal.u16,
;     preP,opcode,cost,entryCost,decision,0; remaining bytes reserved.
.segment "CODE"
.proc GuestTimelineRetire
    php
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
    stz GT+14
    ; Bounded prototype must stop rather than silently wrap its logical clock.
    rep #$20
.a16
    lda GT+2
    cmp #$FFFF
    bne time_ok
    lda GT
    cmp #$FFF2
    bcc time_ok
    sep #$20
.a8
    lda #4
    sta GT+14
    jmp done
time_ok:
    jsr GuestInstructionCycles
    sep #$20
.a8
    lda GC_STATUS
    beq :+
    lda #1
    sta GT+14
    jmp done
:
    lda GC_COST
    sta GT+20
    rep #$20
.a16
    and #$FF
    clc
    adc GT
    sta GT
    bcc :+
    inc GT+2
:
event_loop:
    sep #$20
.a8
    lda GT+13
    cmp #TimelineEventCount
    bcc :+
    jmp enter_boundary
:
    rep #$20
.a16
    and #$FF
    asl a
    asl a
    asl a
    tax
    lda f:TimelineEvents+2,x
    cmp GT+2
    bcc event_due
    bne enter_boundary
    lda f:TimelineEvents,x
    cmp GT
    bcc event_due
    bne enter_boundary
event_due:
    sep #$20
.a8
    lda f:TimelineEvents+4,x
    sta GT+11
    lda f:TimelineEvents+5,x
    ora GT+12
    sta GT+12
    inc GT+13
    bra event_loop
enter_boundary:
    sep #$20
.a8
    lda GC_INPUT
    sta GI
    sta GT+19
    lda GC_INPUT+1
    sta GI+1
    lda GT+9
    sta GI+2
    lda GT+11
    sta GI+3
    lda GT+12
    sta GI+4
    lda GT+10
    sta GI+5
    stz GI+11
    rep #$20
.a16
    lda GT+4
    sta GI+6
    lda #TimelineIRQ
    sta GI+12
    lda #TimelineNMI
    sta GI+14
    jsr GuestInterruptBoundary
    sep #$20
.a8
    lda GI+10
    beq :+
    lda #2
    sta GT+14
    jmp done
:
    lda GI+2
    sta GT+9
    lda GI+4
    sta GT+12
    lda GI+5
    sta GT+10
    lda GI+8
    sta GT+22
    lda GI+9
    sta GT+21
    rep #$20
.a16
    and #$FF
    clc
    adc GT
    sta GT
    bcc :+
    inc GT+2
:
    lda GI+6
    sta GT+4
    inc GT+16
done:
    rep #$30
.a16
.i16
    plb
    pld
    ply
    plx
    pla
    plp
    rts
.endproc
