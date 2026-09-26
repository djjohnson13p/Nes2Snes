"""Plan same-size JSR veneers for explicitly supported absolute guest accesses.

Veneers run in reserved WRAM $1000-$17FF, mirrored in execution banks $A1-$BF.
Execution bank $C0 deliberately retains COP: that bank has no low WRAM mirror.
Live selectors optionally extend the JSR frame and return with RTL into the new
mapping. No game code is included; generated veneers remain private.
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


def plan(prg: bytes, sites: Iterable[dict], simple: bool = False, bank_switches: bool = False, stress_banks: bool = False, audio_counters: bool = False) -> tuple[list[dict], str]:
    selected = []
    entries = {}
    for site in sites:
        offset = site['prg_offset']
        if site['mode'] != 'abs':
            continue
        opcode = prg[offset]
        address = int.from_bytes(prg[offset + 1:offset + 3], 'little')
        kind = handler_kind(opcode, address)
        if audio_counters and opcode in STORE_OPS and (0x4000 <= address < 0x4014 or address in (0x4015,0x4017)):
            kind = ("apu", address & 0x1f)
        if bank_switches and opcode in STORE_OPS and address in (0x5115, 0x5116, 0x5117):
            kind = ("bank", address)
        if kind is not None:
            selected.append(dict(prg_offset=offset, opcode=opcode, address=address,
                                 label=label(opcode, address), kind=kind[0]))
            entries[opcode, address] = kind
    lines = ['; Generated from classified absolute sites. Input-derived: keep private.',
             '.segment "STUBS"', '.a8', '.i8']
    for (opcode, address), (kind, value) in sorted(entries.items()):
        lines.append(label(opcode, address) + ':')
        if kind == 'bank':
            lines += bank_veneer(opcode, address, stress_banks)
        elif kind == 'apu':
            lines += ['    php', '    phx', f'    ldx #${value:02X}',
                      f'    jsl $800000+DirectApu{STORE_OPS[opcode]}',
                      '    plx', '    plp', '    rts']
        elif kind == 'write':
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


def bank_veneer(opcode: int, address: int, stress: bool = False) -> list[str]:
    """A same-bank JSR enters WRAM; RTL leaves into the *new* ROM mapping.

    Preserve full A (including B), all guest P flags, X/Y/D and stack balance.
    DBR intentionally changes with the mapper. Host NMI must defer while the
    saved guest PC is inside a WRAM veneer, even after CODEBANK has changed.
    """
    if opcode not in STORE_OPS or address not in (0x5115, 0x5116, 0x5117):
        raise ValueError('Unsupported direct bank store')
    body = ['    php', '    rep #$20', '.a16', '    pha',
            '    inc $0988', '    bne :+', '    inc $098A', ':',
            '    sep #$20', '.a8']
    if opcode != 0x8D:
        body.append('    txa' if opcode == 0x8E else '    tya')
    if address == 0x5115:
        body += ['    sta f:$7E5115', '    and #$1E', '    lsr a',
                 '    sta TMP', '    lda SLOT', '    and #$10',
                 '    ora TMP', '    sta SLOT']
    elif address == 0x5116:
        body += ['    sta VAL', '    and #$1F', '    cmp #$1E',
                 '    beq @thirty', '    cmp #$07', '    beq @seven',
                 '    jml $800000+DirectBankFault', '@seven:',
                 '    lda SLOT', '    ora #$10', '    bra @slot',
                 '@thirty:', '    lda SLOT', '    and #$0F', '@slot:',
                 '    sta SLOT', '    lda VAL', '    sta f:$7E5116']
    else:
        body += ['    sta VAL', '    and #$1F', '    cmp #$1F',
                 '    beq @fixed', '    jml $800000+DirectBankFault',
                 '@fixed:', '    lda VAL', '    sta f:$7E5117']
    body += ['    lda SLOT', '    clc', '    adc #$81', '    sta RAWBANK',
             '    clc', '    adc #$20', '    sta CODEBANK']
    if stress:
        body += ['    phx', '    rep #$10', '.i16', '    ldx #$FFFF',
                 '@nmi_window:', '    dex', '    bne @nmi_window',
                 '    sep #$10', '.i8', '    plx']
    body += ['    lda RAWBANK', '    pha', '    plb',
             '; Insert new PBR above JSR return, keeping full A and P intact.',
             '; Stack after dummy push: dummy,Alo,Ahi,P,retlo,rethi.',
             '    pha', '    rep #$20', '.a16', '    lda 2,s', '    sta 1,s',
             '    lda 4,s', '    sta 3,s', '    sep #$20', '.a8',
             '    lda 6,s', '    sta 5,s', '    lda CODEBANK', '    sta 6,s',
             '    rep #$20', '.a16', '    pla', '    plp', '.a8', '.i8', '    rtl']
    return body
