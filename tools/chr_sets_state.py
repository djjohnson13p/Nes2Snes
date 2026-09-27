"""Read actual pinned Nestopia A/B bank registers; never predict read outputs."""
from oam_state import _chunks, nestopia_oam
from palette_state import decode, decode_mmc5
from verify_ppu_blank import exact_hex


def decode_sets(data):
    state = decode(data, sprite_16=True)
    state.update(decode_mmc5(data, sprite_16=True))
    if bytes.fromhex(state['ppu_state'])[0] & 0xE0 != 0x20:
        raise ValueError('The CHR-set endpoint requires blanked 8x16 mode')
    root = _chunks(data[8:8+int.from_bytes(data[4:8], 'little')])
    mm5 = _chunks(_chunks(_chunks(root[b'IMG\0'])[b'MPR\0'])[b'MM5\0'])
    reg = mm5[b'REG\0']
    if len(reg) != 32 or reg[22] & 0x7C:
        raise ValueError('Malformed CHR-set mapper serialization')
    # SubSave packs each register's own high bits at distinct two-bit positions.
    banks = [(reg[7+i] | (((reg[19+i//4] >> (2*(i%4))) & 3) << 8)) for i in range(8)]
    banks += [(reg[15+i] | (((reg[21] >> (2*i)) & 3) << 8)) for i in range(4)]
    image = bytes(((reg[0] >> 2) & 3, reg[22] & 3, reg[22] >> 7))
    image += b''.join(v.to_bytes(2, 'little') for v in banks)
    oam, address, latch = nestopia_oam(data)
    if latch != bytes.fromhex(state['ppu_state'])[-1] or any(oam[i]&0x1C for i in range(2, 256, 4)):
        raise ValueError('Invalid shared OAM endpoint')
    state.update(chr_set_registers=image.hex(), oam=oam.hex(), oam_address=bytes((address,)).hex())
    return state


def native_registers(state):
    b = exact_hex(state.get('chr_set_b'), 9, 'native B registers')
    cr = exact_hex(state.get('ppu_chr_context'), 28, 'native CHR context')[16:]
    rows = state.get('chr_records')
    count = state.get('completed_steps')
    if not isinstance(rows, list) or type(count) is not int or not 1 <= count <= len(rows):
        raise ValueError('Missing retired CHR-set record')
    record = exact_hex(rows[count-1], 48, 'retired CHR sets')
    if b[8] > 1 or any(b[i] > 3 for i in (1,3,5,7)) or cr[10] > 3 or record[0] > 3:
        raise ValueError('Native bank register outside ten-bit range')
    a = b''.join(bytes((cr[i], (cr[8+i//4] >> (2*(i%4))) & 3)) for i in range(8))
    if record[1] != cr[10] or record[2:18] != a or record[34:43] != b or any(record[43:]):
        raise ValueError('Final CHR-set registers differ from retired state')
    return bytes((record[0], cr[10], b[8])) + a + b[:8]
