"""Generate original diagnostic font/layout assets for the SNES viewer."""
import struct
from pathlib import Path
from graphics import encode_nes_tile, nes_to_snes

# Small original 5x7 diagnostic alphabet. Each row is a 5-bit mask.
GLYPHS = {
 'A':[14,17,17,31,17,17,17], 'B':[30,17,17,30,17,17,30],
 'C':[14,17,16,16,16,17,14], 'D':[30,17,17,17,17,17,30],
 'E':[31,16,16,30,16,16,31], 'F':[31,16,16,30,16,16,16],
 'G':[14,17,16,23,17,17,15], 'H':[17,17,17,31,17,17,17],
 'I':[14,4,4,4,4,4,14], 'J':[7,2,2,2,2,18,12],
 'K':[17,18,20,24,20,18,17], 'L':[16,16,16,16,16,16,31],
 'M':[17,27,21,21,17,17,17], 'N':[17,25,21,19,17,17,17],
 'O':[14,17,17,17,17,17,14], 'P':[30,17,17,30,16,16,16],
 'Q':[14,17,17,17,21,18,13], 'R':[30,17,17,30,20,18,17],
 'S':[15,16,16,14,1,1,30], 'T':[31,4,4,4,4,4,4],
 'U':[17,17,17,17,17,17,14], 'V':[17,17,17,17,17,10,4],
 'W':[17,17,17,21,21,21,10], 'X':[17,17,10,4,10,17,17],
 'Y':[17,17,10,4,4,4,4], 'Z':[31,1,2,4,8,16,31],
 '0':[14,17,19,21,25,17,14], '1':[4,12,4,4,4,4,14],
 '2':[14,17,1,2,4,8,31], '3':[30,1,1,14,1,1,30],
 '4':[2,6,10,18,31,2,2], '5':[31,16,16,30,1,1,30],
 '6':[14,16,16,30,17,17,14], '7':[31,1,2,4,8,8,8],
 '8':[14,17,17,14,17,17,14], '9':[14,17,17,15,1,1,14],
 ':':[0,4,4,0,4,4,0], '/':[1,1,2,4,8,16,16],
 '-':[0,0,0,31,0,0,0], '.':[0,0,0,0,0,6,6],
 '+':[0,4,4,31,4,4,0], '=':[0,31,0,31,0,0,0],
}


def create_assets(out: Path, pages: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    font = bytearray()
    for code in range(32, 96):
        glyph = GLYPHS.get(chr(code), [0]*7)
        pixels = [[0]*8 for _ in range(8)]
        for y, mask in enumerate(glyph):
            for x in range(5):
                pixels[y][x+1] = 3 if mask & (1 << (4-x)) else 0
        font.extend(encode_nes_tile(pixels))
    (out/'font.2bpp').write_bytes(nes_to_snes(bytes(font)))
    tilemap = [256] * 1024  # blank font tile, not CHR tile zero
    def text(row, string):
        x = (32-len(string))//2
        for n, c in enumerate(string):
            tilemap[row*32+x+n] = 256 + ord(c) - 32
    text(1, 'NES2SNES')
    text(3, 'CHR CONVERSION TEST')
    for y in range(16):
        for x in range(16):
            tilemap[(y+5)*32 + x+8] = y*16+x
    text(22, 'PAGE 00 / '+f'{pages-1:02X}')
    # The zero-based page digits must match the source's VRAM address $12CF.
    assert tilemap[22*32+15] == 256+ord('0')-32
    text(24, 'L/R: PAGE   B: PALETTE')
    text(26, 'NOT A PLAYABLE PORT')
    (out/'tilemap.bin').write_bytes(struct.pack('<1024H', *tilemap))
    (out/'config.inc').write_text(f'PAGE_COUNT = {pages}\n', encoding='utf-8')
