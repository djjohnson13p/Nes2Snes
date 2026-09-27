"""Explicit immutable NROM-256 data reads on the experimental native timeline.

The 32-KiB original cartridge image is kept at SNES $01:8000, separate from
translated execution in bank zero. No mapper writes, bus conflicts, open bus,
PPU/APU side effects or dynamic bank changes are represented by this profile.
"""
from timeline_ram import access as ram_access, WRITES


def validate_data(plan: dict) -> None:
    if plan.get('memory_model') != 'nrom-32k':
        if 'rom_data' in plan:
            raise ValueError('ROM data requires the nrom-32k profile')
        return
    patches = plan.get('rom_data')
    if not isinstance(patches, list) or len(patches) > 64:
        raise ValueError('Require a bounded explicit ROM data list')
    origin = plan['origin']; limit = origin + len(bytes.fromhex(plan['code']))
    if origin < 0xE100 and limit > 0xE000:
        raise ValueError('Program overlaps the authored boot region')
    used = set(); total = 0
    for patch in patches:
        if not isinstance(patch, dict) or set(patch) != {'address', 'bytes'}:
            raise ValueError('Unknown ROM data fields')
        address, text = patch['address'], patch['bytes']
        if type(address) is not int or not 0x8000 <= address < 0xFFFA:
            raise ValueError('ROM data address outside cartridge data region')
        if not isinstance(text, str) or not 0 < len(text) <= 8192:
            raise ValueError('Invalid ROM data encoding')
        raw = bytes.fromhex(text); end = address + len(raw)
        if not raw or end > 0xFFFA or (address < limit and end > origin) or (address < 0xE100 and end > 0xE000):
            raise ValueError('ROM data overlaps code, boot or vectors')
        cells = set(range(address, end))
        if cells & used:
            raise ValueError('ROM data ranges overlap')
        used |= cells; total += len(raw)
        if total > 4096:
            raise ValueError('Authored ROM data exceeds profile budget')


def access(name: str, mode: str, operand: int) -> str:
    text = ram_access(name, mode, operand)
    return text.replace('    jsr TimelineResolveRAM',
                        f'    lda #{int(name in WRITES)}\n    sta MR_WRITE\n    jsr TimelineResolveROM')


def jump(operand: int) -> str:
    if type(operand) is not int or not (0 <= operand < 0x2000 or 0x8000 <= operand <= 0xFFFF):
        raise ValueError('Indirect jump pointer must be RAM or immutable cartridge ROM')
    high = (operand & 0xFF00) | ((operand + 1) & 255)
    return f'''    rep #$30
.a16
.i16
    lda #${operand:04X}
    jsr TimelineReadMapped
.a8
    sta MR_VALUE
    rep #$20
.a16
    lda #${high:04X}
    jsr TimelineReadMapped
.a8
    sta GT+5
    lda MR_VALUE
    sta GT+4
    rep #$30
.a16
.i16
    jmp retire
'''
