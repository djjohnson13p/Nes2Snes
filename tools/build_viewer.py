#!/usr/bin/env python3
"""Build a real native SNES asset-viewer ROM, not a playable game port."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from rom import Rom
from graphics import nes_to_snes, synthetic_chr
from viewer_assets import create_assets

ROOT = Path(__file__).resolve().parents[1]


def tool(name: str) -> str:
    local = ROOT/'.tools'/'bin'/name
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f'{name} not found. Install cc65 and add its bin directory to PATH.')
    return found


def finalize_rom(core: bytes, converted: bytes) -> bytes:
    if len(core) != 32768:
        raise ValueError('Expected one complete 32 KiB LoROM boot bank.')
    size = 1 << max(16, (len(core)+len(converted)-1).bit_length())
    if size > 4*1024*1024:
        raise ValueError('Viewer exceeds its standard 4 MiB LoROM limit.')
    out = bytearray(core + converted)
    out.extend(b'\xff'*(size-len(out)))
    out[0x7FD7] = size.bit_length()-1-10
    # For a power-of-two ROM, complementary checksum bytes always sum to 510.
    out[0x7FDC:0x7FE0] = b'\xff\xff\x00\x00'
    checksum = sum(out) & 0xFFFF
    struct.pack_into('<HH', out, 0x7FDC, checksum ^ 0xFFFF, checksum)
    assert sum(out) & 0xFFFF == checksum
    return bytes(out)


def validate_sfc(raw: bytes) -> dict:
    if len(raw) < 32768 or len(raw) & (len(raw)-1):
        raise ValueError('Expected a headerless, power-of-two SNES ROM.')
    comp, checksum = struct.unpack_from('<HH', raw, 0x7FDC)
    reset = struct.unpack_from('<H', raw, 0x7FFC)[0]
    if comp ^ checksum != 0xFFFF or sum(raw) & 0xFFFF != checksum:
        raise ValueError('SNES checksum mismatch.')
    if raw[0x7FD5] not in (0x20, 0x30) or reset < 0x8000:
        raise ValueError('Invalid LoROM header or reset vector.')
    if (1024 << raw[0x7FD7]) != len(raw):
        raise ValueError('Header ROM-size field does not match the output length.')
    return {'bytes':len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'map':'LoROM', 'checksum':f'{checksum:04X}', 'reset':f'${reset:04X}'}


def build(chr_data: bytes, out: Path, source: str) -> dict:
    if not chr_data or len(chr_data) % 4096:
        raise ValueError('Viewer needs nonempty CHR data in complete 4 KiB pages.')
    pages = len(chr_data)//4096
    if pages > 255:
        raise ValueError('Viewer currently supports at most 255 CHR pages.')
    out.mkdir(parents=True, exist_ok=True)
    assets = out/'viewer-assets'
    create_assets(assets, pages)
    subprocess.run([tool('ca65'), '-g', '-I', str(assets), '--bin-include-dir', str(assets),
                    '-l', str(out/'viewer.lst'), '-o', str(out/'viewer.o'),
                    str(ROOT/'snes/src/viewer.s')], check=True)
    subprocess.run([tool('ld65'), '-C', str(ROOT/'snes/linker/viewer.cfg'),
                    '-m', str(out/'viewer.map'), '-Ln', str(out/'viewer.lbl'),
                    '-o', str(out/'viewer-core.bin'), str(out/'viewer.o')], check=True)
    converted = nes_to_snes(chr_data)
    raw = finalize_rom((out/'viewer-core.bin').read_bytes(), converted)
    rompath = out/'chr-viewer.sfc'
    rompath.write_bytes(raw)
    result = validate_sfc(raw)
    result.update({'output':rompath.name, 'source':source, 'chr_pages':pages,
                   'tiles':len(chr_data)//16, 'playable_game_port':False})
    (out/'viewer-build.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--rom', type=Path)
    g.add_argument('--synthetic', action='store_true')
    p.add_argument('--out', type=Path, default=ROOT/'build/viewer')
    args=p.parse_args()
    try:
        rom=Rom.read(args.rom) if args.rom else None
        result=build(rom.chr if rom else synthetic_chr(), args.out,
                     rom.metadata()['sha256'] if rom else 'procedural test patterns')
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Build failed: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
