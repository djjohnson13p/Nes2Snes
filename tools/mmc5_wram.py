"""Explicit 32-KiB single-chip MMC5 cartridge-RAM integration.

EWROM-like wiring: selectors 0..3 are four distinct pages; absent-chip selection
is refused rather than fabricated as RAM or open bus. Original PRG mapping and
code remain independent. CPU registers/RAM and final full cartridge RAM are
compared against original execution; this is not a cycle-by-cycle bus model.
"""
from pathlib import Path
from mmc5_timeline import REGISTERS, INITIAL
from timeline_ram import WRITES

PROFILE='mmc5-prg-ram32'
RAM_BYTES=32768


def validate(plan: dict) -> dict:
    from mmc5_timeline import validate as base
    return base(plan,cartridge_ram=True)


def initial_ram() -> bytes:
    """Declared fixture boot writes, not an intermediate expected-state table."""
    return b''.join(bytes([0x41+bank])*8192 for bank in range(4))


def append_boot(p) -> None:
    """An original NES subroutine initializes RAM via actual protected writes."""
    p.label('init_cart')
    def store(a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
    store(0x5102,2);store(0x5103,1);store(2,0)
    p.label('cart_bank');p.op('LDA','zp',2);p.op('STA','abs',0x5113)
    p.op('CLC');p.op('ADC','imm',0x41);p.op('STA','zp',3)
    store(0,0);store(1,0x60);p.op('LDY','imm',0)
    p.label('cart_fill');p.op('LDA','zp',3);p.op('STA','iy',0);p.op('INY');p.op('BNE','rel','cart_fill')
    p.op('INC','zp',1);p.op('LDA','zp',1);p.op('CMP','imm',0x80);p.op('BNE','rel','cart_fill')
    p.op('INC','zp',2);p.op('LDA','zp',2);p.op('CMP','imm',4);p.op('BNE','rel','cart_bank')
    store(0x5113,0);store(0x5102,0);store(0x5103,0);p.op('RTS')


def write_code(address: int) -> str:
    if address in (0x5102,0x5103):
        shift='    asl a\n    asl a\n' if address==0x5103 else ''
        mask=3 if address==0x5103 else 12
        return f'''    sep #$20
.a8
    lda GT+6
    and #3
{shift}    sta MR_VALUE
    lda CW_LOCK
    and #{mask}
    ora MR_VALUE
    sta CW_LOCK
'''
    if address==0x5113 or address in (0x5114,0x5115,0x5116):
        # Named labels would conflict across generated instructions; anonymous
        # branches select a shared local forward label for this emitted sequence.
        test='' if address==0x5113 else '    bmi :+\n'
        dest='CW_PAGE' if address==0x5113 else f'MB_REG+{REGISTERS.index(address)}'
        remap='' if address==0x5113 else '    jsr MapperRemap\n'
        final='    and #3\n' if address==0x5113 else ''
        return f'''    sep #$20
.a8
    lda GT+6
{test}    and #4
    beq :+
    lda #5
    sta GT+14
    jmp fault
:
    lda GT+6
{final}    sta {dest}
{remap}'''
    from mmc5_timeline import write_code as base
    return base(address)


def access(name: str,mode: str,operand: int) -> str:
    from mmc5_timeline import access as base
    text=base(name,mode,operand)
    if name in WRITES:
        old='''    rep #$10
.i16
    ldx MR_ADDR
    lda MR_VALUE
    sta $0000,x
'''
        if text.count(old)!=1:raise ValueError('RAM commit anchor changed')
        text=text.replace(old,'    jsr CartridgeCommit\n')
    return text


def jump(operand: int) -> str:
    if type(operand) is not int or not (0<=operand<0x2000 or 0x6000<=operand<=0xFFFF):
        raise ValueError('Indirect pointer outside admitted RAM/ROM')
    high=(operand&0xFF00)|((operand+1)&255)
    return f'''    rep #$30
.a16
.i16
    lda #${operand:04X}
    jsr MapperRead
.a8
    sta MR_VALUE
    rep #$20
.a16
    lda #${high:04X}
    jsr MapperRead
.a8
    sta MR_VALUE+1
    lda GT+14
    beq :+
    jmp fault
:
    lda MR_VALUE
    sta GT+4
    lda MR_VALUE+1
    sta GT+5
    rep #$30
.a16
.i16
    jmp retire
'''


def prepare_native(out: Path,driver: str) -> str:
    from build_viewer import ROOT
    kernel=(ROOT/'snes/src/mmc5_prg.inc').read_text()
    # Retain the proven ROM and internal-RAM paths; replace only mapper selection
    # and the operand resolver for this explicit cartridge-RAM profile.
    kernel=kernel[:kernel.index('.proc TimelineResolveMMC5')]
    kernel=kernel.replace('one:\n    bmi rom\n    lda #$FF','one:\n    bmi rom\n    and #3\n    ora #$80')
    kernel=kernel.replace('    cmp #$8000\n    bcc invalid','''    cmp #$6000
    bcc invalid
    cmp #$8000
    bcs :+
    sep #$20
.a8
    lda CW_PAGE
    ora #$80
    rts
:
.a16''',1)
    kernel=kernel.replace('    cmp #$FF\n    bne done','    rts',1)
    # MapperRead now dispatches typed slots; high bit means cartridge RAM.
    needle='''    jsr MapperBank
    sta MB_BANK
    lda GT+14'''
    if kernel.count(needle)!=1:raise ValueError('Mapper read anchor changed')
    kernel=kernel.replace(needle,'''    jsr MapperBank
    sta MB_BANK
    bpl :+
    lda GT+14
    bne :+
    rep #$20
.a16
    lda MB_CHECK
    jsr CartridgePointer
    phd
    rep #$20
.a16
    lda #MPTR
    tcd
    sep #$20
.a8
    lda [$00]
    pld
    rts
:
    lda GT+14''')
    extra=(ROOT/'snes/src/mmc5_wram.inc').read_text()
    (out/'mmc5_prg.inc').write_text('CW_LOCK=$1876\nCW_PAGE=$1877\nCW_KIND=$1859\n'+kernel+extra)
    # The 32-KiB initialization can span a host frame before normal host setup.
    # Initialize fault metadata before that loop; never interpret power-on bytes
    # as an observed runtime failure, and do not suppress a later real fault.
    driver=driver.replace('    stz $420C','''    stz $420C
    ldx #0
cartridge_early_host_state:
    stz $1D00,x
    inx
    cpx #32
    bne cartridge_early_host_state''')
    driver=driver.replace('    jsr MapperInit','    jsr MapperInit\n    jsr CartridgeInit')
    # RAM can supply data and pointers but never unvalidated translated code.
    driver=driver.replace('    sta MB_CURRENT\n    lda GT+14','''    sta MB_CURRENT
    bpl :+
    lda #5
    sta GT+14
:
    lda GT+14''')
    needle='''    sta $1C18
    ldx $1B02'''
    if driver.count(needle)!=1:raise ValueError('Mapping header anchor changed')
    driver=driver.replace(needle,'''    sta $1C18
    lda CW_PAGE
    ora #$80
    sta $1C19
    lda CW_LOCK
    sta $1C1A
    lda CW_PAGE
    sta $1C1B
    ldx $1B02''')
    return driver


def create_nes(out: Path,plan: dict) -> Path:
    from mmc5_timeline import create_nes as base
    return base(out,plan,cartridge_ram=True)


def create_native(out: Path,plan: dict,initial: bytes,**kwargs) -> Path:
    from mmc5_timeline import create_native as base
    return base(out,plan,initial,cartridge_ram=True,**kwargs)
