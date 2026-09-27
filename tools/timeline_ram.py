"""Native generation for guarded internal-RAM addressing in the timeline.

The guest's $0000-$1FFF resolves to host $0000-$07FF. Non-RAM final or
preliminary indexed addresses fault before target operand access or retirement.
This deliberately excludes mapper bus observation and interleaved DMA/events.
"""
from opcodes6502 import OPS

MODES = {'zp':1,'zpx':2,'zpy':3,'abs':4,'absx':5,'absy':6,'ix':7,'iy':8}
WRITES = {'STA','STX','STY','INC','DEC','ASL','LSR','ROL','ROR'}
ABSOLUTE = {name:op for op,(name,mode,_) in OPS.items() if mode=='abs'}


def access(name: str, mode: str, operand: int) -> str:
    """Execute a real native ALU instruction against the resolved RAM operand."""
    if mode not in MODES or name not in ABSOLUTE:
        raise ValueError('Unsupported RAM instruction')
    text=f'''    sep #$20
.a8
    lda #{MODES[mode]}
    sta MR_MODE
    jsr TimelineResolveRAM
    sep #$20
.a8
    lda GT+14
    beq :+
    jmp fault
:
    jsr load_guest
.a8
.i8
    .byte ${ABSOLUTE[name]:02X},<MR_VALUE,>MR_VALUE
    jsr save_guest
'''
    if name in WRITES:
        text+='''    rep #$10
.i16
    ldx MR_ADDR
    lda MR_VALUE
    sta $0000,x
'''
    return text


def jump(operand: int) -> str:
    """NMOS JMP-indirect reads its high byte within the original pointer page."""
    if type(operand) is not int or not 0<=operand<0x2000:
        raise ValueError('Indirect jump pointer must be in internal RAM')
    lo=operand&0x7FF
    hi=((operand&0xFF00)|((operand+1)&255))&0x7FF
    return f'''    sep #$20
.a8
    lda ${lo:04X}
    sta GT+4
    lda ${hi:04X}
    sta GT+5
    rep #$30
.a16
.i16
    jmp retire
'''
