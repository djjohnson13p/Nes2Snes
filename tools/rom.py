"""Strict, dependency-free iNES/NES 2.0 parsing; never changes the input ROM."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
import zlib


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def nes2_size(low: int, high: int, unit: int) -> int:
    if high != 15:
        return ((high << 8) | low) * unit
    exponent, multiplier = low >> 2, ((low & 3) * 2 + 1)
    return (1 << exponent) * multiplier


@dataclass(frozen=True)
class Rom:
    raw: bytes
    header: bytes
    trainer: bytes
    prg: bytes
    chr: bytes
    trailing: bytes
    mapper: int
    submapper: int
    nes2: bool

    @classmethod
    def parse(cls, raw: bytes) -> 'Rom':
        if len(raw) < 16 or raw[:4] != b'NES\x1a':
            raise ValueError('Not an iNES/NES 2.0 ROM: expected a 16-byte NES header.')
        h = raw[:16]
        if h[7] & 12 not in (0, 8):
            raise ValueError('Unrecognized or archaic header variant; refusing to guess.')
        nes2 = (h[7] & 12) == 8
        mapper = (h[6] >> 4) | (h[7] & 240)
        submapper = 0
        if nes2:
            mapper |= (h[8] & 15) << 8
            submapper = h[8] >> 4
            psize = nes2_size(h[4], h[9] & 15, 16384)
            csize = nes2_size(h[5], h[9] >> 4, 8192)
        else:
            psize, csize = h[4] * 16384, h[5] * 8192
        if psize == 0:
            raise ValueError('No PRG ROM declared.')
        tsize = 512 if h[6] & 4 else 0
        pstart = 16 + tsize
        cstart = pstart + psize
        end = cstart + csize
        if end > len(raw):
            raise ValueError(f'Truncated ROM: declares {end} bytes, contains {len(raw)}.')
        return cls(raw, h, raw[16:pstart], raw[pstart:cstart], raw[cstart:end],
                   raw[end:], mapper, submapper, nes2)

    @classmethod
    def read(cls, path: str | Path) -> 'Rom':
        return cls.parse(Path(path).read_bytes())

    @property
    def prg_offset(self) -> int:
        return 16 + len(self.trainer)

    def metadata(self) -> dict:
        h = self.header
        warnings = []
        if self.trailing:
            warnings.append('Trailing data is preserved; it is not assumed to be CHR.')
        if not self.chr:
            warnings.append('CHR RAM cartridge: graphics cannot be extracted as CHR ROM.')
        if not self.nes2 and any(h[12:16]):
            warnings.append('Nonzero legacy header padding; mapper identification may need verification.')
        if self.mapper == 5:
            warnings.append('MMC5 controls nametable mapping at runtime; the header mirroring bit is not authoritative.')
        result = {
            'format': 'NES 2.0' if self.nes2 else 'iNES',
            'file_bytes': len(self.raw), 'header_hex': h.hex(),
            'sha256': sha256(self.raw), 'crc32': f'{zlib.crc32(self.raw):08x}',
            'prg_sha256': sha256(self.prg), 'chr_sha256': sha256(self.chr),
            'payload_sha256': sha256(self.prg + self.chr),
            'mapper': self.mapper, 'submapper': self.submapper,
            'trainer_bytes': len(self.trainer), 'prg_offset': self.prg_offset,
            'prg_bytes': len(self.prg), 'chr_offset': self.prg_offset + len(self.prg),
            'chr_bytes': len(self.chr), 'trailing_bytes': len(self.trailing),
            'prg_8k_banks': len(self.prg) // 8192,
            'chr_1k_banks': len(self.chr) // 1024,
            'chr_tiles': len(self.chr) // 16,
            'battery_flag': bool(h[6] & 2), 'warnings': warnings,
        }
        if self.nes2:
            result['timing'] = ['NTSC', 'PAL', 'multi-region', 'Dendy'][h[12] & 3]
            for byte, names in [(10, ('prg_ram_bytes', 'prg_nvram_bytes')),
                                (11, ('chr_ram_bytes', 'chr_nvram_bytes'))]:
                for shift, name in zip((0, 4), names):
                    n = (h[byte] >> shift) & 15
                    result[name] = (64 << n) if n else 0
        # These are file-tail words, not universal CPU vectors for arbitrary mappers.
        if len(self.prg) >= 6:
            result['prg_tail_vector_words'] = dict(zip(
                ('nmi', 'reset', 'irq'), (f'${n:04X}' for n in struct.unpack('<HHH', self.prg[-6:]))))
            result['vector_mapping_assumption'] = (
                'MMC5 final 8 KiB PRG bank at $E000-$FFFF on reset; reassess after bank writes.'
                if self.mapper == 5 else 'Unverified for this mapper; these are only the final six PRG bytes.')
        return result
