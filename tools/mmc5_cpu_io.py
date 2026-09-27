"""CPU-only MMC5 ExRAM modes 2/3 and the unsigned multiplier.

Explicitly extends single-chip PRG RAM. Rendering-dependent ExRAM modes, PPU
access, open bus and other I/O remain guarded; this is not a graphics renderer.
"""
from pathlib import Path

PROFILE = 'mmc5-cpu-io'
EXRAM_BYTES = 1024


def validate(plan: dict) -> dict:
    from mmc5_timeline import validate as base
    return base(plan, cartridge_ram=True, cpu_io=True)


def initial_exram() -> bytes:
    return bytes([0xA5]) * EXRAM_BYTES


def append_boot(p) -> None:
    """Original NES code establishes initial ExRAM and multiplier state."""
    def put(address, value):
        p.op('LDA','imm',value);p.op('STA','abs',address)
    p.label('init_exram');put(0x5104,2)
    p.op('LDA','imm',0xA5);p.op('LDX','imm',0);p.label('fill_exram')
    for a in range(0x5C00,0x6000,256):p.op('STA','absx',a)
    p.op('INX');p.op('BNE','rel','fill_exram')
    put(0x5104,3);put(0x5205,0);put(0x5206,0);p.op('RTS')


def register_code(name: str, address: int) -> str:
    if address == 0x5104 and name == 'STA':
        return '''    sep #$20
.a8
    lda GT+6
    and #3
    cmp #2
    bcs :+
    lda #5
    sta GT+14
    jmp fault
:
    sta EX_MODE
'''
    if address not in (0x5205,0x5206) or name not in ('LDA','STA'):
        raise ValueError('Unsupported CPU-I/O register operation')
    part=address-0x5205
    if name=='STA':
        return f'''    sep #$20
.a8
    lda GT+6
    sta EX_MUL+{part}
    jsr ExMultiply
'''
    return f'''    jsr load_guest
.a8
.i8
    lda EX_PRODUCT+{part}
    jsr save_guest
'''


def jump(operand: int) -> str:
    if type(operand) is not int or not (operand < 0x2000 or 0x5C00 <= operand <= 65535) or operand < 0:
        raise ValueError('Unsupported indirect pointer address')
    # The extended MapperRead below admits ExRAM as well as existing RAM/ROM.
    from mmc5_wram import jump as old
    if operand>=0x6000 or operand<0x2000:return old(operand)
    high=(operand&0xFF00)|((operand+1)&255)
    return old(0x6000).replace('#$6000',f'#${operand:04X}').replace('#$6001',f'#${high:04X}')


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old)!=1:raise ValueError('CPU I/O integration anchor changed')
    return text.replace(old,new,1)


def prepare_native(out: Path, driver: str) -> str:
    from build_viewer import ROOT
    path=out/'mmc5_prg.inc';text=path.read_text()
    # The multiplier and mode occupy previously reserved bytes within protected GT.
    text='EX_MODE=$18D8\nEX_MUL=$18D9\nEX_PRODUCT=$18DC\n'+text
    text=replace_once(text,'    lda CW_KIND\n    bne cartridge', '''    lda CW_KIND
    cmp #2
    bne :+
    jmp ExCommit
:
    cmp #0
    bne cartridge''')
    # The preliminary indexed region may be ExRAM; no read is performed here.
    text=replace_once(text,'    cmp #$6000\n    bcs :+\n    jmp outside\n:\n    jsr MapperBank', '''    cmp #$5C00
    bcs :+
    jmp outside
:
    cmp #$6000
    bcc ex_preliminary
    jsr MapperBank''')
    text=replace_once(text,'    lda MR_BASE\nadd_index:', '''ex_preliminary:
    lda MR_BASE
add_index:''')
    # ExRAM access does not use PRG-RAM page registers or write-protect bits.
    text=replace_once(text,'check:\n    cmp #$2000\n    bcc mapped', '''check:
    cmp #$5C00
    bcc regular_target
    cmp #$6000
    bcs regular_target
    jsr ExRead
.a8
    sta MR_VALUE
    rep #$30
.a16
.i16
    rts
regular_target:
    cmp #$2000
    bcc mapped''')
    # Indirect jump pointer bytes use the same mapped ExRAM storage.
    text=replace_once(text,'.proc MapperRead\n.a16\n.i16\n    sta MB_CHECK', '''.proc MapperRead
.a16
.i16
    cmp #$5C00
    bcc not_exram
    cmp #$6000
    bcs not_exram
    jmp ExRead
not_exram:
    sta MB_CHECK''')
    text += '\n'+(ROOT/'snes/src/mmc5_cpu_io.inc').read_text()
    path.write_text(text)
    driver=replace_once(driver,'    jsr CartridgeInit','    jsr CartridgeInit\n    jsr ExInit')
    driver=replace_once(driver,'    sta $1C1B\n    ldx $1B02', '''    sta $1C1B
    lda EX_MODE
    sta $1C1C
    lda EX_MUL
    sta $1C1D
    lda EX_MUL+1
    sta $1C1E
    ldx $1B02''')
    return driver


def create_nes(out: Path, plan: dict) -> Path:
    from mmc5_timeline import create_nes as base
    return base(out,plan,cartridge_ram=True,cpu_io=True)


def create_native(out: Path, plan: dict, initial: bytes, **options) -> Path:
    from mmc5_timeline import create_native as base
    return base(out,plan,initial,cartridge_ram=True,cpu_io=True,**options)
