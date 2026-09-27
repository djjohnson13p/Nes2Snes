"""NES interrupt entry at an instruction boundary with an already sampled request.

This is NOT pin sampling or an event-deadline model. A caller must have resolved
subcycle polling (including taken branches), NMI edges and DMA/DMC before calling.
The completed opcode and pre/post P must be from original guest execution.
BRK is deliberately excluded: its return PC, B bit and hijacking need a separate
sequence. Status bytes here retain raw P; pushed P clears B and sets the unused bit.
"""
from dataclasses import dataclass
from opcodes6502 import OPS

SUPPORTED = frozenset(OPS) - {0x00}
DELAYED_I = frozenset((0x28, 0x58, 0x78))


def byte(value: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError(f'{name} must be an unsigned byte')


@dataclass(frozen=True)
class Boundary:
    opcode: int
    before_p: int
    after_p: int
    irq: bool
    nmi: bool
    s: int
    pc: int
    irq_vector: int
    nmi_vector: int

    def validate(self):
        for key in ('opcode', 'before_p', 'after_p', 's'):
            byte(getattr(self, key), key)
        if self.opcode not in SUPPORTED:
            raise ValueError('BRK and undocumented instructions require another entry path')
        for key in ('irq', 'nmi'):
            if type(getattr(self, key)) is not bool:
                raise ValueError('Interrupt requests must be sampled booleans')
        for key in ('pc', 'irq_vector', 'nmi_vector'):
            value = getattr(self, key)
            if type(value) is not int or not 0 <= value <= 65535:
                raise ValueError(f'{key} must be a 16-bit address')

    def record(self) -> bytes:
        self.validate()
        return (bytes((self.opcode, self.before_p, self.after_p, self.irq, self.nmi, self.s))
                + self.pc.to_bytes(2, 'little') + bytes(4)
                + self.irq_vector.to_bytes(2, 'little')
                + self.nmi_vector.to_bytes(2, 'little'))


def enter(boundary: Boundary, stack: bytes) -> tuple[bytes, bytes]:
    """Return updated descriptor and stack, without changing the supplied inputs.

    Descriptor bytes 8..11 are decision (0/1/2), cost, status, reserved.
    The NMI latch is consumed only by NMI entry. IRQ level is never cleared here.
    No request means zero cycles, no stack write and unchanged PC/P/S.
    """
    data = bytearray(boundary.record())
    if not isinstance(stack, bytes) or len(stack) != 256:
        raise ValueError('Require the complete original 256-byte stack page')
    result = bytearray(stack)
    polled_p = boundary.before_p if boundary.opcode in DELAYED_I else boundary.after_p
    kind = 2 if boundary.nmi else 1 if boundary.irq and not polled_p & 4 else 0
    if kind:
        s = boundary.s
        for value in (boundary.pc >> 8, boundary.pc & 255, (boundary.after_p & 0xEF) | 0x20):
            result[s] = value
            s = (s - 1) & 255
        data[2] |= 4
        data[4] = 0 if kind == 2 else data[4]
        data[5] = s
        vector = boundary.nmi_vector if kind == 2 else boundary.irq_vector
        data[6:8] = vector.to_bytes(2, 'little')
        data[8:10] = bytes((kind, 7))
    return bytes(data), bytes(result)


def native_tables() -> str:
    # Classification only, never expected CPU or stack outputs.
    values = [0 if op not in SUPPORTED else 2 if op in DELAYED_I else 1 for op in range(256)]
    return 'InterruptOpcodeClass:\n' + '\n'.join(
        '    .byte ' + ','.join(map(str, values[i:i+16])) for i in range(0, 256, 16)) + '\n'
