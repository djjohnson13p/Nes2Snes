"""Explicit palette extension; old profiles and production source are untouched.

The adapter validates the complete CHR contract before specializing its generated
files. The source NES program receives no expected state. Palette boot is authored
port writes; native zero initialization matches that declared boot, not power-on.
"""
from pathlib import Path
from mmc5_chr_blank import validate as chr_validate, create_nes as chr_nes, create_native as chr_native, boot_code as chr_boot
from mmc5_timeline import reassemble
from mmc5_cpu_io import replace_once
from native_fixture import Program
from build_viewer import ROOT

PROFILE = 'mmc5-palette-blank'
PALETTE_ADDRESS = 0x5800


def underlying(plan):
    if not isinstance(plan, dict) or plan.get('memory_model') != PROFILE:
        raise ValueError('Explicit palette profile required')
    result = dict(plan, memory_model='mmc5-chr-blank')
    chr_validate(result)
    if result['events']:
        raise ValueError('Unmodified-reference palette profile requires no request stimuli')
    return result


def validate(plan):
    underlying(plan)
    return plan


def boot_code(mode):
    p = Program(0xF000)
    # Original boot uses real PPU ports to initialize all palette entries.
    p.op('LDA','abs',0x2002)
    for a,v in ((0x2000,0),(0x2001,0),(0x2006,0x3F),(0x2006,0)):
        p.op('LDA','imm',v);p.op('STA','abs',a)
    p.op('LDX','imm',32);p.op('LDA','imm',0)
    p.label('clear');p.op('STA','abs',0x2007);p.op('DEX');p.op('BNE','rel','clear')
    raw=p.finish()+chr_boot(mode)
    if len(raw)>512:raise ValueError('Palette boot exceeds reserved region')
    return raw


def create_nes(out,plan):
    source=underlying(plan);path=chr_nes(out,source);data=bytearray(path.read_bytes())
    boot=boot_code(source['chr_mode']);offset=16+(source['prg_banks']-1)*8192+0x1000
    data[offset:offset+len(boot)]=boot;path.write_bytes(data)
    return path


def create_native(out,plan,initial,**options):
    source=underlying(plan);chr_native(out,source,initial,**options)
    original=create_nes(out/'original',plan).read_bytes()
    (out/'original-prg.bin').write_bytes(original[16:16+source['prg_banks']*8192])
    (out/'palette_timeline.inc').write_bytes((ROOT/'snes/src/palette_timeline.inc').read_bytes())
    driver=out/'fixture.s';text=driver.read_text()
    text=replace_once(text,'    jsr ChrInit','    jsr ChrInit\n    jsr PaletteInit')
    text=replace_once(text,'.include "mmc5_chr_blank.inc"','.include "mmc5_chr_blank.inc"\n.include "palette_timeline.inc"')
    driver.write_text(text)
    program=out/'program.inc';text=program.read_text()
    text=text.replace('    jsr PpuDataRead','    jsr PaletteDataRead').replace('    jsr PpuDataWrite','    jsr PaletteDataWrite')
    program.write_text(text)
    return reassemble(out)
