"""Read independently serialized NES OAM state without interpreting game code.

Nestopia 8f00f500's NST chunks encode PPU/OAM and PPU/REG fields. FCEUmm's
separate FCS parser lives in verify_memory_completion. Only actual OAM bits are
compared: sprite attributes have no storage for bits 2, 3 and 4.
"""
from __future__ import annotations
import zlib


def _chunks(data: bytes) -> dict[bytes, bytes]:
    result = {}
    pos = 0
    while pos < len(data):
        if len(data) - pos < 8:
            raise ValueError('Truncated NST chunk header')
        tag = data[pos:pos+4]
        size = int.from_bytes(data[pos+4:pos+8], 'little')
        pos += 8
        if size > len(data) - pos:
            raise ValueError('Truncated NST chunk payload')
        if tag in result:
            raise ValueError('Duplicate NST chunk')
        result[tag] = data[pos:pos+size]
        pos += size
    return result


def nestopia_oam(data: bytes) -> tuple[bytes, int, int]:
    """Return raw OAM, OAMADDR and the I/O latch from a bounded NST snapshot."""
    if len(data) < 8 or len(data) > 8*1024*1024 or data[:4] != b'NST\x1a':
        raise ValueError('Expected a bounded Nestopia NST snapshot')
    end = 8 + int.from_bytes(data[4:8], 'little')
    # The pinned libretro wrapper appends eight tracked-input bytes plus four
    # reserved audio-pacing bytes. Older states may have an eight-byte footer;
    # bare NST files have none. These are not necessarily zero padding.
    if end > len(data) or len(data)-end not in (0, 8, 12):
        raise ValueError('Truncated NST root or unexpected trailing bytes')
    root = _chunks(data[8:end])
    ppu = _chunks(root.get(b'PPU\0', b''))
    registers = ppu.get(b'REG\0', b'')
    packed = ppu.get(b'OAM\0', b'')
    if len(registers) != 11 or not packed:
        raise ValueError('Missing or incorrectly sized PPU register/OAM state')
    if packed[0] == 0:
        oam = packed[1:]
    elif packed[0] == 1:
        decompressor = zlib.decompressobj()
        try:
            oam = decompressor.decompress(packed[1:], 257)
        except zlib.error as exc:
            raise ValueError('Invalid NST OAM compression') from exc
        if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
            raise ValueError('Overlong, incomplete or concatenated compressed OAM')
    else:
        raise ValueError('Unknown NST compression type')
    if len(oam) != 256:
        raise ValueError('Independent NST OAM buffer must contain 256 bytes')
    return oam, registers[8], registers[10]


def meaningful_oam(data: bytes) -> bytes:
    """Mask only the three physically absent attribute bits, not visual errors."""
    if len(data) != 256:
        raise ValueError('Expected exactly 256 OAM bytes')
    return bytes(v & (0xe3 if i % 4 == 2 else 0xff) for i, v in enumerate(data))
