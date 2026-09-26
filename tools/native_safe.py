"""Statically proven same-width native substitutions for the 8-bit guest ABI.

Only original RAM accesses are selected. No observed register ranges or inferred
branch targets are used: each replacement is safe for every 8-bit index. The
bridge ABI keeps D=0 and M=X=1 while executing guest instructions.
"""
from __future__ import annotations
from opcodes6502 import OPS


def replacement(opcode: int, operand: int) -> tuple[int, str] | None:
    """Return native operand and proof name, or None for the ordinary handler."""
    item = OPS.get(opcode)
    if item is None:
        return None
    name, mode, size = item
    if not isinstance(operand, int) or not 0 <= operand < (1 << (8 * (size - 1))):
        raise ValueError('Operand does not fit the original instruction width')
    if name not in {"LDA","LDX","LDY","STA","STX","STY","AND","ORA","EOR","ADC","SBC","CMP","CPX","CPY","BIT","ASL","LSR","ROL","ROR","INC","DEC"}:
        return None
    if mode in ('zpx', 'zpy') and operand == 0:
        return 0, 'zero_base_plus_8bit_index'
    if mode == 'abs' and 0x800 <= operand < 0x2000:
        return operand & 0x7ff, 'constant_internal_ram_mirror'
    if mode in ('absx', 'absy') and 0x800 <= operand <= 0x1f00 and (operand & 0x7ff) <= 0x700:
        return operand & 0x7ff, 'internal_ram_mirror_no_page_crossing'
    return None


def apply(prg: bytes, code: bytes, sites: list[dict]) -> tuple[bytes, list[dict], list[dict]]:
    """Replace only entries already classified as intercepted instructions."""
    if len(code) != len(prg):
        raise ValueError('Executable and original program lengths differ')
    out = bytearray(code)
    proven, remaining = [], []
    for site in sites:
        pos = site['prg_offset']
        opcode = prg[pos]
        name, mode, size = OPS[opcode]
        operand = int.from_bytes(prg[pos + 1:pos + size], 'little')
        choice = replacement(opcode, operand)
        if choice is None:
            remaining.append(site)
            continue
        if code[pos:pos + 2] != bytes((2, opcode)):
            raise ValueError('Safe native substitution did not start at a classified COP.')
        native_operand, proof = choice
        out[pos:pos + size] = bytes((opcode,)) + native_operand.to_bytes(size - 1, 'little')
        proven.append(dict(prg_offset=pos, opcode=opcode, operand=operand,
                           native_operand=native_operand, proof=proof))
    return bytes(out), proven, remaining
