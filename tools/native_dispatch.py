"""Recognize a classified inline-table dispatch routine, retaining its body.

Only existing JSR operands targeting the fixed final PRG bank are changed.
Generated wrappers remain private. The runtime checks NMI context and table
address bounds; unsupported contexts tail-jump to the original routine.
"""
from __future__ import annotations
from opcodes6502 import OPS

PATTERN = (
    ('ASL','acc',0), ('STY','zp',3), ('TAY','imp',0), ('INY','imp',0),
    ('PLA','imp',0), ('STA','zp',0), ('PLA','imp',0), ('STA','zp',1),
    ('LDA','iy',0), ('STA','zp',2), ('INY','imp',0), ('LDA','iy',0),
    ('LDY','zp',3), ('STA','zp',3), ('JMP','ind',2),
)

def matches(prg: bytes, counts: list[int], offset: int) -> bool:
    if len(prg) != len(counts):
        raise ValueError('Classification size differs from PRG')
    for name, mode, operand in PATTERN:
        if not 0 <= offset < len(prg) or not counts[offset]:
            return False
        op = OPS.get(prg[offset])
        if op is None or op[:2] != (name, mode):
            return False
        size = op[2]
        if offset + size > len(prg) or any(counts[offset+1:offset+size]):
            return False
        if int.from_bytes(prg[offset+1:offset+size], 'little') != operand:
            return False
        offset += size
    return True

def plan(prg: bytes, counts: list[int]) -> tuple[list[dict], str]:
    if len(prg) != 0x40000 or len(counts) != len(prg):
        raise ValueError('Expected classified 256-KiB PRG')
    sites = []
    targets = set()
    for i, count in enumerate(counts):
        if not count or prg[i] != 0x20 or i + 3 > len(prg) or any(counts[i+1:i+3]):
            continue
        address = int.from_bytes(prg[i+1:i+3], 'little')
        if not 0xE000 <= address < 0xFFFA:
            continue
        if not matches(prg, counts, 0x3E000 + address - 0xE000):
            continue
        label = f'NativeInlineDispatch_{address:04X}'
        sites.append(dict(prg_offset=i, original_target=address, label=label))
        targets.add(address)
    lines = ['; Input-derived call wrappers; keep private.', '.segment "STUBS"']
    for address in sorted(targets):
        lines += [f'NativeInlineDispatch_{address:04X}:', '.scope',
                  f'OriginalDispatch = ${address:04X}', '.include "native_dispatch_body.inc"', '.endscope']
    lines += ['.segment "CODE"']
    return sites, '\n'.join(lines) + '\n'

def apply(code: bytes, sites: list[dict], symbols: dict[str,int]) -> bytes:
    result = bytearray(code)
    for site in sites:
        i, target = site['prg_offset'], site['original_target']
        address = symbols[site['label']]
        if not 0x1000 <= address < 0x1800:
            raise ValueError('Wrapper outside reserved WRAM')
        if result[i:i+3] != bytes((0x20, target & 255, target >> 8)):
            raise ValueError('Dispatch replacement requires an unchanged classified JSR')
        result[i:i+3] = bytes((0x20, address & 255, address >> 8))
    return bytes(result)
