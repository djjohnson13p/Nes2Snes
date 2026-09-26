"""Same-revision default-option checks must fail on changed output or settings."""
from functools import wraps
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import verify_default_options as check


class DefaultOptionTests(unittest.TestCase):
    def exercise(self, root, *, changed=False, enabled=False, empty=False):
        @wraps(check.build)
        def fake_build(rom, trace, out, **options):
            out.mkdir(parents=True, exist_ok=True)
            data = b'' if empty else b'current revision'
            if changed and options:
                data += b'!'
            (out/'native-prototype.sfc').write_bytes(data)
            return {key: enabled for key in check.OPTIONS.values()}

        def create(out):
            out.mkdir(parents=True, exist_ok=True)

        with patch.object(check, 'build', fake_build), patch.dict(
                check.FIXTURES, {name: create for name in check.FIXTURES}):
            return check.run(root)

    def test_same_revision_identity_is_explicitly_scoped(self):
        with tempfile.TemporaryDirectory() as name:
            result = self.exercise(Path(name))
            self.assertTrue(result['passed'])
            self.assertFalse(result['historical_binary_identity_claimed'])
            self.assertEqual(len(result['results']), 3)
            self.assertTrue((Path(name)/'identity.json').is_file())

    def test_changed_byte_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(RuntimeError, 'options differ'):
                self.exercise(Path(name), changed=True)
            self.assertFalse((Path(name)/'identity.json').exists())

    def test_enabled_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(RuntimeError, 'path was enabled'):
                self.exercise(Path(name), enabled=True)

    def test_empty_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(RuntimeError, 'options differ'):
                self.exercise(Path(name), empty=True)

    def test_empty_duplicate_and_unknown_selection_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            for fixtures in ((), ('cpu', 'cpu'), ('unknown',)):
                with self.assertRaises(ValueError):
                    check.run(Path(name), fixtures)

    def test_changed_default_is_rejected_before_building(self):
        def changed_build(*args, native_inline_dispatch=True,
                          coalesced_nt_dma=False, fill_cache_fix=False):
            raise AssertionError('Must not build with a changed default')
        with patch.object(check, 'build', changed_build):
            with self.assertRaisesRegex(RuntimeError, 'disabled by default'):
                check.run(Path('unused'))


if __name__ == '__main__':
    unittest.main()
