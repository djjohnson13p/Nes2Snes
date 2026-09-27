"""Blanked CPU CHR-ROM transfers with fixed CHR bank size and set A only.

The bank size is declared at boot and cannot change during the observed window.
This avoids conflating documented size-dependent register latching with the
pinned reference's live size reinterpretation. No rendering or set-B claim.
"""
from functools import lru_cache
from pathlib import Path
from mmc5_cpu_io import replace_once

PROFILE = 'mmc5-chr-blank'
RECORD_BYTES = 48


def validate_options(plan):
    banks, mode = plan.get('chr_banks'), plan.get('chr_mode')
    if type(banks) is not int or not 8 <= banks <= 1024 or banks & (banks-1):
        raise ValueError('Require power-of-two CHR-ROM size: 8..1024 one-KiB banks')
    if type(mode) is not int or not 0 <= mode <= 3:
        raise ValueError('Require a fixed CHR mode in 0..3')


def validate(plan):
    from mmc5_timeline import validate as base
    return base(plan, cartridge_ram=True, cpu_io=True, ppu_blank=True, chr_blank=True)


@lru_cache(maxsize=8)
def chr_image(banks):
    validate_options({'chr_banks': banks, 'chr_mode': 3})
    return bytes(((b*53+(b>>8)*97+i*29+(i>>3))^0xA7)&255
                 for b in range(banks) for i in range(1024))


def boot_code(mode):
    from native_fixture import Program
    from mmc5_ppu_blank import boot_code as previous
    p = Program(0xF000)
    # No reads or expected state: ordinary original mapper writes establish banks.
    p.op('LDA','imm',mode); p.op('STA','abs',0x5101)
    p.op('LDA','imm',0); p.op('STA','abs',0x5130)
    for a in range(0x5120,0x5128): p.op('STA','abs',a)
    # Previous helper contains relative loops only; it may be relocated intact.
    result = p.finish()+previous()
    if len(result)>512: raise ValueError('CHR boot helper exceeds reserved region')
    return result


def register_code(address):
    if address == 0x5101:
        return '    jsr ChrModeWrite\n'
    if address == 0x5130:
        return '    sep #$20\n.a8\n    lda GT+6\n    and #3\n    sta CR+10\n'
    if 0x5128 <= address <= 0x512B:
        return '    jmp PpuUnsupported\n'
    if not 0x5120 <= address <= 0x5127:
        raise ValueError('Unsupported CHR register')
    i = address-0x5120; shift=2*(i%4); mask=255^(3<<shift)
    return (f'    sep #$20\n.a8\n    lda GT+6\n    sta CR+{i}\n'
            '    lda CR+10\n'+ '    asl a\n'*shift +
            f'    sta CR+11\n    lda CR+{8+i//4}\n    and #${mask:02X}\n'
            f'    ora CR+11\n    sta CR+{8+i//4}\n')


def prepare_native(out,driver,plan):
    from build_viewer import ROOT
    (out/'mmc5_chr_blank.inc').write_bytes((ROOT/'snes/src/mmc5_chr_blank.inc').read_bytes())
    p=out/'mmc5_ppu_blank.inc';text=p.read_text()
    # Only the new explicit profile permits pattern data; the old profile is exact.
    if text.count('    jsr PpuResolve')!=2: raise ValueError('Changed PPUDATA anchors')
    text=text.replace('    jsr PpuResolve','    jsr ChrResolve')
    text=replace_once(text,'    and #$C0','    and #$E0') # set A, 8x8 only
    p.write_text(text)
    driver=replace_once(driver,'.include "mmc5_ppu_blank.inc"',
                        '.include "mmc5_ppu_blank.inc"\n.include "mmc5_chr_blank.inc"')
    driver=replace_once(driver,'    jsr PpuInit','    jsr PpuInit\n    jsr ChrInit')
    driver=replace_once(driver,'    jsr PpuCapture','    jsr PpuCapture\n    jsr ChrCapture')
    return f"ChrMode={plan['chr_mode']}\nChrMask={plan['chr_banks']-1}\nChrStartBank={1+plan['prg_banks']//4}\n"+driver


def extend_host(out,driver):
    p=out/'timeline_host_nmi.inc';text=p.read_text()
    text=replace_once(text,'    cpx #48\n    bne save_capture','    cpx #60\n    bne save_capture')
    text=replace_once(text,'    ldx #46\nrestore_capture:','    ldx #58\nrestore_capture:')
    p.write_text(text)
    return replace_once(driver,'    cpx #48\n    bne poison_capture','    cpx #60\n    bne poison_capture')


def create_nes(out,plan):
    from mmc5_timeline import create_nes as base
    return base(out,plan,cartridge_ram=True,cpu_io=True,ppu_blank=True,chr_blank=True)


def create_native(out,plan,initial,**options):
    from mmc5_timeline import create_native as base
    return base(out,plan,initial,cartridge_ram=True,cpu_io=True,ppu_blank=True,chr_blank=True,**options)
