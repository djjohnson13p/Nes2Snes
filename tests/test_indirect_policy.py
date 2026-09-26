"""Historical equality remains strict when explicitly requested."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import verify_indirect_x as check


class IndirectPolicyTests(unittest.TestCase):
    def exercise(self, root, previous):
        def fixture(folder):
            folder.mkdir(parents=True, exist_ok=True)
        def build(rom, trace, out):
            out.mkdir(parents=True, exist_ok=True)
            (out/'native-prototype.sfc').write_bytes(b'current-source')
        def old_build(command, **kwargs):
            out = Path(command[command.index('--out') + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out/'native-prototype.sfc').write_bytes(previous)
        with patch.object(check, 'create', fixture), patch.object(check, 'native_fixture', fixture), \
             patch.object(check, 'build', build), patch.object(check.subprocess, 'run', old_build):
            return check.historical_identity(root/'previous', root)

    def test_explicit_historical_identity_still_passes_equal_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = self.exercise(Path(folder), b'current-source')
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row['matches_baseline'] for row in rows))

    def test_explicit_historical_identity_rejects_one_changed_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'default ROM changed'):
                self.exercise(Path(folder), b'current-sourcf')


if __name__ == '__main__':
    unittest.main()
