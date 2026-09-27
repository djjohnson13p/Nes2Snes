"""Opt-in physical SNES NMI stress for the existing timeline prototype.

The guest request policy is unchanged. Real SNES vblank NMIs interrupt the native
program; optional WAI sites expose particular live contexts deterministically.
Neither an expected guest state nor a captured reference timeline is an input.
"""
from pathlib import Path
from build_viewer import ROOT

MODES = ('free', 'loaded', 'alu', 'partial-save', 'cost', 'stack', 'time', 'capture', 'nested')
PROTECTED = ((0x1840, 64), (0x18C0, 32), (0x1B02, 4), (0x1C00, 32))
HOST_BYTES = 32

# The worker deliberately uses every protected scratch byte and clobbers all
# saved register classes. It never touches original guest RAM or guest output.
WORKER = r'''
.segment "CODE"
.proc TimelineHostWork
    rep #$30
.a16
.i16
    ldx #0
poison_gc:
    txa
    eor #$A55A
    sta f:$7E1840,x
    inx
    inx
    cpx #64
    bne poison_gc
    ldx #0
poison_gt:
    txa
    eor #$F081
    sta f:$7E18C0,x
    inx
    inx
    cpx #32
    bne poison_gt
    lda #$C35A
    sta f:$7E1B02
    sta f:$7E1B04
    ldx #0
poison_capture:
    txa
    eor #$67AB
    sta f:$7E1C00,x
    inx
    inx
    cpx #32
    bne poison_capture
    sep #$20
.a8
    lda f:$7E1D07
    beq no_nested
    lda f:$7E1D04
    cmp #1
    bne no_nested
    wai                         ; second real vblank, not a software NMI call
HostNestedResume:
no_nested:
    rep #$30
.a16
.i16
    lda f:$7E1D0C
    inc a
    sta f:$7E1D0C
    bne :+
    lda f:$7E1D0E
    inc a
    sta f:$7E1D0E
:
    lda #$0355
    tcd
    sep #$20
.a8
    lda #$7F
    pha
    plb
    rep #$30
.a16
.i16
    ldx #$ABCD
    ldy #$9876
    lda #$D3EF
    sed
    sec
    sep #$30
.a8
.i8
    rts
.endproc
HostNestedResume = TimelineHostWork::HostNestedResume
'''


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Host NMI integration anchor changed or duplicated')
    return text.replace(old, new, 1)


def prepare(folder: Path, driver: str, mode: str) -> str:
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError('Unknown host NMI mode')
    symbol = '$0000'             # no deliberate WAI in free-running execution
    edits = {
        'loaded': ('fixture', '    plp\n    rts\nsave_guest:', '    plp\n    wai\nHostWaitResume:\n    rts\nsave_guest:', 'HostWaitResume'),
        'alu': ('fixture', 'save_guest:\n', 'save_guest:\n    wai\nHostWaitResume:\n', 'HostWaitResume'),
        'partial-save': ('fixture', 'save_guest:\n    sta GT+6\n', 'save_guest:\n    sta GT+6\n    wai\nHostWaitResume:\n', 'HostWaitResume'),
        'cost': ('guest_cycles.inc', '    sta GC_COST\n    lda f:GuestCycleAdjust,x', '    sta GC_COST\n    wai\nHostWaitResume:\n    lda f:GuestCycleAdjust,x', 'GuestInstructionCycles::HostWaitResume'),
        'stack': ('guest_interrupt.inc', '    sta $0100,x\n    dex\n    lda GI+6', '    sta $0100,x\n    wai\nHostWaitResume:\n    dex\n    lda GI+6', 'GuestInterruptBoundary::HostWaitResume'),
        'time': ('guest_timeline.inc', '    sta GT\n    bcc :+\n    inc GT+2\n:\nevent_loop:', '    sta GT\n    wai\nHostWaitResume:\n    bcc :+\n    inc GT+2\n:\nevent_loop:', 'GuestTimelineRetire::HostWaitResume'),
        'capture': ('fixture', '    ldx $1B02\n    ldy #0\nwrite_header:', '    wai\nHostWaitResume:\n    ldx $1B02\n    ldy #0\nwrite_header:', 'HostWaitResume'),
    }
    chosen = 'capture' if mode == 'nested' else mode
    if chosen in edits:
        file, old, new, symbol = edits[chosen]
        if file == 'fixture':
            driver = replace_once(driver, old, new)
        else:
            p = folder / file
            p.write_text(replace_once(p.read_text(), old, new))
    driver = replace_once(driver, '    stz $1B02\nnext_instruction:', f'''    stz $1B02
    sep #$20
.a8
    ldx #0
clear_host:
    stz $1D00,x
    inx
    cpx #32
    bne clear_host
    lda #{int(mode == 'nested')}
    sta HN_NEST
    lda #$A5
    sta $1E80
    lda #$5A
    sta $1FF1
    lda $4210
    lda #$80
    sta $4200
    rep #$30
.a16
.i16
next_instruction:''')
    driver = replace_once(driver, '    lda #$5A\n    sta f:$7E1FFF', '    stz $4200\n    lda #$5A\n    sta f:$7E1FFF')
    driver = replace_once(driver, 'fault:\n    lda #$EE', 'fault:\n    stz $4200\n    lda #$EE')
    driver = replace_once(driver, '.word 0,0,halt,halt,halt,halt,0,halt', '.word 0,0,halt,halt,halt,TimelineHostNMI,0,halt')
    driver = replace_once(driver, '.include "guest_cycles.inc"', '.include "timeline_host_nmi.inc"\n'+WORKER+'\n.include "guest_cycles.inc"')
    (folder/'timeline_host_nmi.inc').write_bytes((ROOT/'snes/src/timeline_host_nmi.inc').read_bytes())
    return driver + f'\nHostExpectedResume = {symbol}\n'
