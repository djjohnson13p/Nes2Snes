"""Strict state parsing and original destination-offset fixture contracts."""
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oam_state import nestopia_oam, meaningful_oam
from oam_copy_fixture import create
from verify_oam_offsets import compare_oam, validate_stream


def chunk(tag, data):
    return tag + len(data).to_bytes(4, 'little') + data


def state(data=bytes(range(256)), compressed=False, address=255, latch=0xb7):
    regs = bytes(8) + bytes((address, 0, latch))
    packed = bytes((int(compressed),)) + (zlib.compress(data) if compressed else data)
    return chunk(b'NST\x1a', chunk(b'PPU\0', chunk(b'REG\0', regs) + chunk(b'OAM\0', packed)))


class OamOffsetTests(unittest.TestCase):
    def test_reads_complete_raw_state(self):
        data = bytes(range(256))
        self.assertEqual(nestopia_oam(state()), (data, 255, 0xb7))

    def test_reads_compressed_state(self):
        self.assertEqual(nestopia_oam(state(bytes(256), True))[0], bytes(256))

    def test_accepts_only_documented_frontend_footer_lengths(self):
        for trailer in (bytes(12), bytes(range(12)), bytes(range(8))):
            self.assertEqual(nestopia_oam(state()+trailer), nestopia_oam(state()))
        for trailer in (bytes(13), b'\1', bytes(11), bytes(16)):
            with self.assertRaises(ValueError): nestopia_oam(state()+trailer)

    def test_rejects_bad_header_or_truncated_root(self):
        for data in (b'', b'NST\x1a', state()[:-1], b'BAD!'+state()[4:]):
            with self.assertRaises(ValueError): nestopia_oam(data)

    def test_rejects_duplicate_fields(self):
        regs = chunk(b'REG\0', bytes(11))
        oam = chunk(b'OAM\0', b'\0'+bytes(256))
        for payload in (regs+regs+oam, regs+oam+oam):
            with self.assertRaises(ValueError):
                nestopia_oam(chunk(b'NST\x1a', chunk(b'PPU\0', payload)))

    def test_rejects_missing_fields_and_bad_sizes(self):
        for payload in (b'', chunk(b'REG\0', bytes(10)), chunk(b'OAM\0', b'\0'+bytes(256))):
            with self.assertRaises(ValueError):
                nestopia_oam(chunk(b'NST\x1a', chunk(b'PPU\0', payload)))
        for size in (0, 255, 257):
            with self.assertRaises(ValueError): nestopia_oam(state(bytes(size)))

    def test_rejects_decompression_overrun_and_truncation(self):
        for data in (bytes(257), bytes(100000)):
            with self.assertRaises(ValueError): nestopia_oam(state(data, True))
        regs = chunk(b'REG\0', bytes(11))
        for packed in (b'\2xxx', b'\1invalid', b'\1'+zlib.compress(bytes(256))+b'trailer',
                       b'\1'+zlib.compress(bytes(256))[:-1]):
            with self.assertRaises(ValueError):
                nestopia_oam(chunk(b'NST\x1a', chunk(b'PPU\0', regs+chunk(b'OAM\0', packed))))

    def test_masks_exactly_absent_attribute_bits(self):
        for value in range(256):
            m = meaningful_oam(bytes((value,))*256)
            for i in range(256):
                self.assertEqual(m[i], value & (0xe3 if i % 4 == 2 else 255))

    def test_comparison_keeps_raw_disagreements_visible(self):
        a = bytes(256)
        b = bytes(0x1c if i % 4 == 2 else 0 for i in range(256))
        result = compare_oam(a, b)
        self.assertEqual(result['mismatch_count'], 0)
        self.assertEqual(result['raw_mismatch_count'], 64)
        self.assertEqual(result['meaningful_bits_checked'], 1856)

    def test_comparison_does_not_mask_real_errors(self):
        a = bytes(range(256))
        for i in range(256):
            b = bytearray(a); b[i] ^= 1
            self.assertEqual(compare_oam(a, bytes(b))['mismatch_count'], 1)
        self.assertGreater(compare_oam(a, a[-1:]+a[:-1])['mismatch_count'], 240)

    def test_comparison_rejects_partial_buffers(self):
        for n in (0, 255, 257):
            with self.assertRaises(ValueError): compare_oam(bytes(n), bytes(256))
            with self.assertRaises(ValueError): meaningful_oam(bytes(n))

    def test_stream_rejects_missing_extra_duplicate_and_truncated_records(self):
        rows = [dict(offset=i, oam=bytes(256).hex(), records=bytes(12).hex()) for i in range(256)]
        validate_stream(rows)
        for bad in (rows[:-1], rows+[rows[-1]], rows[:128]+rows[:128], list(reversed(rows))):
            with self.assertRaises(ValueError): validate_stream(bad)
        rows[17] = dict(offset=17, oam=bytes(255).hex(), records=bytes(12).hex())
        with self.assertRaises(ValueError): validate_stream(rows)

    def test_fixture_rejects_invalid_offsets(self):
        with tempfile.TemporaryDirectory() as t:
            for n in (-1, 256, True, 1.5, '1'):
                with self.assertRaises(ValueError): create(Path(t), oam_address=n)

    def test_fixture_rejects_invalid_modes(self):
        with tempfile.TemporaryDirectory() as t:
            for kw in ({'post_write':256}, {'mutate_source':True, 'page':0x80},
                       {'neutral_latch':1}, {'stream_offsets':1},
                       {'stream_offsets':True, 'post_write':1}):
                with self.assertRaises(ValueError): create(Path(t), **kw)

    def test_stream_fixture_has_bounded_known_code(self):
        with tempfile.TemporaryDirectory() as t:
            m = create(Path(t), stream_offsets=True, neutral_latch=True)
            self.assertTrue(m['stream_offsets'])
            self.assertTrue(m['neutral_latch'])
            self.assertEqual(len(m['records']), 3)
            self.assertLessEqual(m['program_bytes'], 0x1ffa)
            self.assertLessEqual(m['result_end'], 0x780)

    def test_variants_are_reproducible_and_recorded(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t)/'a', Path(t)/'b'
            for p in (a, b): create(p, oam_address=255, post_write=0xad, mutate_source=True)
            self.assertEqual((a/'fixture.nes').read_bytes(), (b/'fixture.nes').read_bytes())
            import json
            meta = json.loads((a/'trace-summary.json').read_text())
            self.assertEqual(meta['oam_address'], 255)
            self.assertEqual(len(meta['records']), 4)


if __name__ == '__main__': unittest.main()
