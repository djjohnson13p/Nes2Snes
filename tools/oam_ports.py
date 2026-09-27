"""Explicit blanked OAM port adapter over the published palette profile.

This uses authored initialization, not power-up assumptions. Older profiles
keep their guards. No sprite rendering, DMA, OAM decay or PPU revision quirks.
"""
from pathlib import Path
from native_fixture import Program
from mmc5_cpu_io import replace_once
from mmc5_timeline import fragments, reassemble
from opcodes6502 import OPS
from build_viewer import ROOT
import palette_timeline as palette

PROFILE = 'mmc5-oam-blank'
OAM_ADDRESS = 0x5900
ADDRESS_REGISTER = 0x1C3B


def underlying(plan):
    if not isinstance(plan, dict) or plan.get('memory_model') != PROFILE:
        raise ValueError('Explicit OAM profile required')
    result = dict(plan, memory_model=palette.PROFILE)
    palette.validate(result)
    return result


def validate(plan):
    underlying(plan)
    return plan


def boot_code(mode):
    p = Program(0xF000)
    p.op('LDA', 'imm', 0)
    p.op('STA', 'abs', 0x2003)
    p.op('LDX', 'imm', 0)
    p.label('clear_oam')
    p.op('STA', 'abs', 0x2004)
    p.op('INX')
    p.op('BNE', 'rel', 'clear_oam')
    code = p.finish() + palette.boot_code(mode)
    if len(code) > 512:
        raise ValueError('OAM initialization exceeds reserved helper region')
    return code


def create_nes(out, plan):
    source = underlying(plan)
    path = palette.create_nes(out, source)
    raw = bytearray(path.read_bytes())
    code = boot_code(source['chr_mode'])
    offset = 16 + (source['prg_banks']-1)*8192 + 0x1000
    raw[offset:offset+len(code)] = code
    path.write_bytes(raw)
    return path


def port_code(opcode, port):
    if opcode not in (0xAD, 0x8D) or port not in (3, 4):
        raise ValueError('Only absolute OAM address/data loads and stores')
    if opcode == 0x8D:
        return '    jsr '+('OamAddressWrite' if port == 3 else 'OamDataWrite')+'\n'
    routine = 'PpuLatchRead' if port == 3 else 'OamDataRead'
    return f'''    jsr {routine}
.a8
    sta MR_VALUE
    jsr load_guest
.a8
.i8
    lda MR_VALUE
    jsr save_guest
'''


def create_native(out, plan, initial, **options):
    source = underlying(plan)
    palette.create_native(out, source, initial, **options)
    raw = create_nes(out/'original', plan).read_bytes()
    (out/'original-prg.bin').write_bytes(raw[16:16+source['prg_banks']*8192])
    (out/'oam_ports.inc').write_bytes((ROOT/'snes/src/oam_ports.inc').read_bytes())
    path = out/'fixture.s'
    driver = replace_once(path.read_text(), '    jsr PaletteInit', '    jsr PaletteInit\n    jsr OamInit')
    driver = replace_once(driver, '.include "palette_timeline.inc"',
                          '.include "palette_timeline.inc"\n.include "oam_ports.inc"')
    driver = replace_once(driver, '    jsr ChrCapture', '    jsr ChrCapture\n    jsr OamCapture')
    path.write_text(driver)
    path = out/'program.inc'
    text = path.read_text()
    # Reclaim CR+11 without growing the nested host stack. The CHR register
    # writer needs a temporary only within that write, so MR_VALUE is reusable.
    text = text.replace('    sta CR+11\n', '    sta MR_VALUE\n')
    text = text.replace('    ora CR+11\n', '    ora MR_VALUE\n')
    for part in fragments(source):
        code = bytes.fromhex(part['code'])
        pos = 0
        while pos < len(code):
            op = code[pos]; size = OPS[op][2]
            address = int.from_bytes(code[pos+1:pos+size], 'little')
            if op in (0xAD, 0x8D) and 0x2000 <= address < 0x4000 and address & 7 in (3, 4):
                label = f'ins_b{part["bank"]}_{part["origin"]+pos:04x}:\n'
                begin = text.index(label)+len(label)
                end = text.index('    jmp retire\n', begin)+len('    jmp retire\n')
                body = replace_once(text[begin:end], '    jmp PpuUnsupported\n', port_code(op, address & 7))
                text = text[:begin] + body + text[end:]
            pos += size
    if 'CR+11' in text:
        raise ValueError('Unconverted CHR temporary aliases OAM address')
    path.write_text(text)
    return reassemble(out)
