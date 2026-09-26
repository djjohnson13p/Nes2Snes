"""Plan same-size JSR veneers for explicitly supported absolute guest accesses.

Veneers run in reserved WRAM $1000-$17FF, mirrored in execution banks $A1-$BF.
Execution bank $C0 deliberately retains COP: that bank has no low WRAM mirror.
No original game code is included in this module; generated veneers are private.
"""
from __future__ import annotations
from typing import Iterable

STORE_OPS = {0x8D: 'A', 0x8E: 'X', 0x8C: 'Y'}
RAM_START = 0x1000
RAM_END = 0x1800


def handler_kind(opcode: int, address: int) -> tuple[str, int] | None:
    """Whitelist bridge semantics, not a claim to implement every NES register."""
    if opcode in STORE_OPS:
        if 0x2000 <= address < 0x4000:
            return 'write', address & 7
        if address in (0x4014, 0x4016, 0x5203, 0x5204):
            return 'write', {0x4014: 8, 0x4016: 9, 0x5203: 10, 0x5204: 11}[address]
        # The bridge currently models these as backing RAM. Live PRG selectors
        # are excluded; they change the return bank and still use verified COP.
        if 0x5100 <= address < 0x512C and address not in (0x5115, 0x5116, 0x5117):
            return 'mapper', address
        if 0x4000 <= address < 0x4014 or address == 0x4015:
            return 'backing', address
    elif opcode == 0xAD:
        if 0x2000 <= address < 0x4000 and address & 7 == 2:
            return 'read', 0
        if address in (0x4016, 0x4017, 0x5204):
            return 'read', {0x4016: 1, 0x4017: 2, 0x5204: 3}[address]
    return None


def label(opcode: int, address: int) -> str:
    return f'Direct_{opcode:02X}_{address:04X}'


def plan(prg: bytes, sites: Iterable[dict], simple: bool = False) -> tuple[list[dict], str]:
    selected = []
    entries = {}
    for site in sites:
        offset = site['prg_offset']
        if site['mode'] != 'abs':
            continue
        opcode = prg[offset]
        address = int.from_bytes(prg[offset + 1:offset + 3], 'little')
        kind = handler_kind(opcode, address)
        if kind is not None:
            selected.append(dict(prg_offset=offset, opcode=opcode, address=address,
                                 label=label(opcode, address), kind=kind[0]))
            entries[opcode, address] = kind
    lines = ['; Generated from classified absolute sites. Input-derived: keep private.',
             '.segment "STUBS"', '.a8', '.i8']
    for (opcode, address), (kind, value) in sorted(entries.items()):
        lines.append(label(opcode, address) + ':')
        if kind == 'write':
            target = 'DirectSimpleWrite' if simple and value in (0, 1, 2, 3, 5, 6, 10, 11) else 'DirectWrite'
            lines += ['    php', '    phx', f'    ldx #${value * 2:02X}',
                      f'    jsl $800000+{target}{STORE_OPS[opcode]}',
                      '    plx', '    plp', '    rts']
        elif kind == 'read':
            target = ('DirectReadStatus', 'DirectReadJoy', 'DirectReadJoy2', 'DirectReadIrq')[value]
            lines += [f'    jsl $800000+{target}', '    rts']
        else:
            # NMI defers guest execution while a WRAM veneer is active, so
            # compound stores cannot be split across a live bank change.
            # Preserve all guest flags and the accumulator explicitly.
            lines += ['    php', '    pha']
            if opcode != 0x8D:
                lines.append('    txa' if opcode == 0x8E else '    tya')
            lines += [f'    sta f:$7E{address:04X}']
            if kind == 'mapper' and address >= 0x5120:
                lines += [f'    lda #${address & 8:02X}', '    sta LASTCHR']
            lines += ['    pla', '    plp', '    rts']
    # Ensure ld65 creates the segment even for a fixture without eligible sites.
    if not entries:
        lines.append('    rts')
    lines.append('.segment "CODE"')
    return selected, '\n'.join(lines) + '\n'


def apply(code: bytes, sites: list[dict], symbols: dict[str, int]) -> bytes:
    result = bytearray(code)
    for site in sites:
        address = symbols[site['label']]
        if not RAM_START <= address < RAM_END:
            raise ValueError(f'Direct-call veneer is outside reserved WRAM: ${address:04X}')
        pos = site['prg_offset']
        if result[pos:pos + 2] != bytes((0x02, site['opcode'])):
            raise ValueError('Direct-call replacement must start at a classified COP instruction')
        result[pos:pos + 3] = bytes((0x20, address & 255, address >> 8))
    return bytes(result)
