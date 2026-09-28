"""Explicit blanked 8x16 MMC5 A/B CHR selection, composed with OAM/palettes.

Bank size stays fixed at boot. The previous profiles remain unchanged. B-bank
state is guest mapper memory, outside the host callback's writable contract.
"""
from pathlib import Path
from build_viewer import ROOT
from native_fixture import Program
from mmc5_cpu_io import replace_once
from mmc5_timeline import fragments, reassemble
from opcodes6502 import OPS
import oam_ports

PROFILE = 'mmc5-chr-sets-blank'
B_ADDRESS = 0x5A00


def underlying(plan):
    if not isinstance(plan, dict) or plan.get('memory_model') != PROFILE:
        raise ValueError('Explicit CHR-set profile required')
    result = dict(plan, memory_model=oam_ports.PROFILE)
    oam_ports.validate(result)
    return result


def validate(plan):
    underlying(plan)
    return plan


def initial(plan):
    from verify_oam_ports import initial as previous
    return previous(underlying(plan))


def boot_code(mode):
    previous = oam_ports.boot_code(mode)
    if not previous or previous[-1] != 0x60:
        raise ValueError('Changed original initialization return')
    p = Program(0xF000)
    p.op('LDA', 'imm', 0)
    for address in range(0x5128, 0x512C):
        p.op('STA', 'abs', address)
    p.op('STA', 'abs', 0x5120)  # Establish last-set A using an ordinary write.
    p.op('LDA', 'imm', 0x20)
    p.op('STA', 'abs', 0x2000)
    p.op('RTS')
    result = previous[:-1] + p.finish()
    if len(result) > 512:
        raise ValueError('CHR-set initialization exceeds reserved helper')
    return result


def create_nes(out, plan):
    source = underlying(plan)
    path = oam_ports.create_nes(out, source)
    data = bytearray(path.read_bytes())
    code = boot_code(source['chr_mode'])
    offset = 16 + (source['prg_banks']-1)*8192 + 0x1000
    data[offset:offset+len(code)] = code
    path.write_bytes(data)
    return path


def register_b(address):
    if type(address) is not int or not 0x5128 <= address <= 0x512B:
        raise ValueError('Require a set-B register address')
    offset = 2*(address-0x5128)
    return f'''    sep #$20
.a8
    lda GT+6
    sta f:CS_B+{offset}
    lda CR+10
    sta f:CS_B+{offset+1}
    lda #1
    sta f:CS_LAST
'''


def create_native(out, plan, initial_state, **options):
    source = underlying(plan)
    oam_ports.create_native(out, source, initial_state, **options)
    raw = create_nes(out/'original', plan).read_bytes()
    (out/'original-prg.bin').write_bytes(raw[16:16+source['prg_banks']*8192])
    (out/'chr_sets.inc').write_bytes((ROOT/'snes/src/chr_sets.inc').read_bytes())
    p = out/'fixture.s'
    text = replace_once(p.read_text(), '    jsr OamInit', '    jsr OamInit\n    jsr ChrSetsInit')
    text = replace_once(text, '.include "oam_ports.inc"', '.include "oam_ports.inc"\n.include "chr_sets.inc"')
    text = replace_once(text, '    jsr OamCapture', '    jsr OamCapture\n    jsr ChrSetsCapture')
    p.write_text(text)
    p = out/'mmc5_chr_blank.inc'
    p.write_text(replace_once(p.read_text(), '.proc ChrBank\n', '.proc ChrBankA\n'))
    p = out/'mmc5_ppu_blank.inc'
    # Only this profile accepts and REQUIRES bit 5. No live sprite-mode change,
    # PPU master/slave mode or PPU NMI enable is silently admitted.
    p.write_text(replace_once(p.read_text(), '    and #$E0\n    beq :+',
                              '    and #$E0\n    cmp #$20\n    beq :+'))
    p = out/'program.inc'; text = p.read_text()
    for part in fragments(source):
        code = bytes.fromhex(part['code']); pos = 0
        while pos < len(code):
            op = code[pos]; size = OPS[op][2]
            address = int.from_bytes(code[pos+1:pos+size], 'little')
            if op == 0x8D and 0x5120 <= address <= 0x512B:
                label = f'ins_b{part["bank"]}_{part["origin"]+pos:04x}:\n'
                begin = text.index(label)+len(label)
                end = text.index('    jmp retire\n', begin)+len('    jmp retire\n')
                body = text[begin:end]
                if address >= 0x5128:
                    body = replace_once(body, '    jmp PpuUnsupported\n', register_b(address))
                else:
                    # The selected set changes on every admitted bank write,
                    # including an unchanged value or a register inactive in this size.
                    anchor = '    sta GT+4\n    jmp retire\n'
                    body = replace_once(body, anchor,
                        '    sta GT+4\n    sep #$20\n.a8\n    lda #0\n    sta f:CS_LAST\n'
                        '    rep #$30\n.a16\n.i16\n    jmp retire\n')
                text = text[:begin]+body+text[end:]
            pos += size
    p.write_text(text)
    return reassemble(out)
