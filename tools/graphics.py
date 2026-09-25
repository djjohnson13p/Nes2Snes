"""Lossless NES CHR <-> SNES planar tile conversion; no palette guessing."""
from __future__ import annotations
import struct


def nes_to_snes(chr_data: bytes, bpp: int = 2) -> bytes:
    if len(chr_data) % 16:
        raise ValueError('NES CHR must contain whole 16-byte tiles.')
    if bpp not in (2, 4):
        raise ValueError('Only SNES 2bpp and zero-extended 4bpp are supported.')
    out = bytearray()
    for pos in range(0, len(chr_data), 16):
        tile = chr_data[pos:pos + 16]
        for row in range(8):
            out.extend((tile[row], tile[row + 8]))
        if bpp == 4:
            out.extend(bytes(16))
    return bytes(out)


def snes_to_nes(data: bytes, bpp: int = 2) -> bytes:
    if bpp not in (2, 4) or len(data) % (8 * bpp):
        raise ValueError('Invalid SNES tile length or bit depth.')
    out = bytearray()
    for pos in range(0, len(data), 8 * bpp):
        tile = data[pos:pos + 8 * bpp]
        if bpp == 4 and any(tile[16:]):
            raise ValueError('Upper color planes are nonzero; conversion would lose color information.')
        out.extend(tile[:16:2])
        out.extend(tile[1:16:2])
    return bytes(out)


def decode_nes_tile(tile: bytes) -> list[list[int]]:
    if len(tile) != 16:
        raise ValueError('Expected one NES tile.')
    return [[((tile[y] >> (7-x)) & 1) | (((tile[y+8] >> (7-x)) & 1) << 1)
             for x in range(8)] for y in range(8)]


def encode_nes_tile(pixels: list[list[int]]) -> bytes:
    if len(pixels) != 8 or any(len(row) != 8 for row in pixels):
        raise ValueError('Expected an 8x8 pixel matrix.')
    if any(not isinstance(p, int) or not 0 <= p <= 3 for row in pixels for p in row):
        raise ValueError('NES pixel indices must be integers from 0 to 3.')
    return bytes(sum(((pixels[y][x] >> plane) & 1) << (7-x) for x in range(8))
                 for plane in range(2) for y in range(8))


def synthetic_chr(pages: int = 4) -> bytes:
    if not 1 <= pages <= 256:
        raise ValueError('Synthetic CHR requires 1..256 pages.')
    out = bytearray()
    for t in range(pages * 256):
        page, index = divmod(t, 256)
        p = [[((x ^ y ^ index) + page) % 4 for x in range(8)] for y in range(8)]
        # Distinct corners make row/plane/order errors visible.
        p[0][0], p[0][7], p[7][0], p[7][7] = 0, 1, 2, 3
        out.extend(encode_nes_tile(p))
    return bytes(out)


def nametable_to_snes(nametable: bytes, tile_offset: int = 0,
                     palette_offset: int = 0, priority: bool = False) -> bytes:
    """Expand an NES 32x30 nametable+attributes to an SNES 32x32 tilemap.

    This is an offline format conversion, not MMC5 extended-attribute emulation.
    The last two SNES tilemap rows are blank. Color palettes must be supplied
    separately from a verified runtime state.
    """
    if len(nametable) != 1024:
        raise ValueError('Expected 960 tile bytes and 64 attribute bytes.')
    if not 0 <= tile_offset <= 768 or not 0 <= palette_offset <= 4:
        raise ValueError('Tile/palette offsets exceed the SNES tilemap fields.')
    out = bytearray()
    for y in range(32):
        for x in range(32):
            word = 0
            if y < 30:
                attr = nametable[960 + (y // 4) * 8 + x // 4]
                shift = (4 if y & 2 else 0) + (2 if x & 2 else 0)
                palette = ((attr >> shift) & 3) + palette_offset
                word = (nametable[y*32+x] + tile_offset) | (palette << 10)
                if priority:
                    word |= 0x2000
            out.extend(struct.pack('<H', word))
    return bytes(out)
