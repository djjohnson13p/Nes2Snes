"""Blanked PPU nametable transfers on the protected MMC5 CPU-I/O timeline.

Only absolute LDA/STA PPU accesses and nametable/fill-register writes are added.
Rendering, NMI enable, CHR/palette/OAM and ExRAM-as-nametable remain refused.
This profile proves register/memory state, not pixel rendering or PPU deadlines.
"""
from pathlib import Path
from mmc5_cpu_io import replace_once

PROFILE = 'mmc5-ppu-blank'
PPU_BYTES = 16
CIRAM_BYTES = 2048


def validate(plan: dict) -> dict:
    from mmc5_timeline import validate as base
    return base(plan,cartridge_ram=True,cpu_io=True,ppu_blank=True)


def initial_ciram() -> bytes:
    return bytes([0x3C])*1024 + bytes([0xC3])*1024


def initial_ppu() -> bytes:
    # CTRL,MASK,w,x,t,v,read-buffer,I/O latch,NT map,fill tile,fill attribute,padding.
    return bytes.fromhex('00000000002001203c00441102000000')


def boot_code() -> bytes:
    """Original instructions initialize memory through actual PPU/MMC5 ports."""
    from native_fixture import Program
    p=Program(0xF000)
    def put(a,v):p.op('LDA','imm',v);p.op('STA','abs',a)
    put(0x2000,0);put(0x2001,0)
    p.op('LDA','abs',0x2002)  # establish the shared write phase, not a native input
    put(0x5105,0x44);put(0x5106,0x11);put(0x5107,2)
    for page,value in ((0x20,0x3C),(0x24,0xC3)):
        put(0x2006,page);put(0x2006,0)
        p.op('LDY','imm',4);p.op('LDX','imm',0);p.op('LDA','imm',value)
        p.label(f'fill_{page}');p.op('STA','abs',0x2007);p.op('INX');p.op('BNE','rel',f'fill_{page}')
        p.op('DEY');p.op('BNE','rel',f'fill_{page}')
    put(0x2005,0);put(0x2005,0);put(0x2006,0x20);put(0x2006,0)
    p.op('LDA','abs',0x2007)  # buffer gets initialized from CIRAM, independent of old buffer
    put(0x2002,0)            # defined I/O latch without reading vblank status
    p.op('RTS')
    code=p.finish()
    if len(code)>512:raise ValueError('Blank-PPU boot helper exceeds reserved region')
    return code


def register_code(name: str,address: int) -> str:
    if name not in ('LDA','STA') or type(address) is not int:
        raise ValueError('Require admitted absolute register operation')
    if 0x2000 <= address < 0x4000:
        reg=address&7
        if name=='LDA':
            if reg in (2,3,4):return '    jmp PpuUnsupported\n'
            call='PpuDataRead' if reg==7 else 'PpuLatchRead'
            return f'''    jsr {call}
.a8
    sta MR_VALUE
    jsr load_guest
.a8
.i8
    lda MR_VALUE
    jsr save_guest
'''
        routine={0:'PpuControl',1:'PpuMask',2:'PpuLatchWrite',5:'PpuScroll',6:'PpuAddress',7:'PpuDataWrite'}.get(reg)
        return f'    jsr {routine}\n' if routine else '    jmp PpuUnsupported\n'
    if name=='STA' and address in (0x5105,0x5106,0x5107):
        return f"    jsr {dict(zip((0x5105,0x5106,0x5107),('PpuMap','PpuFillTile','PpuFillAttr')))[address]}\n"
    raise ValueError('Unsupported blank-PPU register')


def prepare_native(out: Path,driver: str) -> str:
    from build_viewer import ROOT
    (out/'mmc5_ppu_blank.inc').write_bytes((ROOT/'snes/src/mmc5_ppu_blank.inc').read_bytes())
    driver=replace_once(driver,'.include "mmc5_prg.inc"','.include "mmc5_prg.inc"\n.include "mmc5_ppu_blank.inc"')
    driver=replace_once(driver,'    jsr ExInit','    jsr ExInit\n    jsr PpuInit')
    driver=replace_once(driver,'capture:\n    rep #$10','capture:\n    jsr PpuCapture\n.a8\n    rep #$10')
    return driver


def extend_host(out: Path,driver: str) -> str:
    """Protect the new 16-byte PPU state with each nested host stack frame."""
    p=out/'timeline_host_nmi.inc';text=p.read_text()
    text=replace_once(text,'    cpx #32\n    bne save_capture','    cpx #48\n    bne save_capture')
    text=replace_once(text,'    ldx #30\nrestore_capture:','    ldx #46\nrestore_capture:')
    p.write_text(text)
    return replace_once(driver,'    cpx #32\n    bne poison_capture','    cpx #48\n    bne poison_capture')


def create_nes(out:Path,plan:dict)->Path:
    from mmc5_timeline import create_nes as base
    return base(out,plan,cartridge_ram=True,cpu_io=True,ppu_blank=True)


def create_native(out:Path,plan:dict,initial:bytes,**options)->Path:
    from mmc5_timeline import create_native as base
    return base(out,plan,initial,cartridge_ram=True,cpu_io=True,ppu_blank=True,**options)
