#!/usr/bin/env python3
"""Apply an exact, source-only checkpoint diff; reject stale or mixed baselines."""
from pathlib import Path
import base64
import gzip
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ALLOWED = {'snes/src/native.s', 'snes/src/native_ppudata.inc', 'README.md',
           'docs/engineering-status.md', 'docs/palette-reads.md',
           'docs/palette-reads-verification.json', 'tools/palette_read_fixture.py',
           'tools/verify_palette_reads.py', 'tests/test_palette_reads.py'}


def apply() -> bool:
    manifest = json.loads((HERE/'manifest.json').read_text())
    before, after = manifest['before'], manifest['after']
    if set(before) != ALLOWED or set(after) != ALLOWED:
        raise ValueError('Unexpected checkpoint file set')
    hashes = {name: (hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                     if (ROOT/name).exists() else None) for name in ALLOWED}
    if hashes == after:
        print('Exact tested integration already present')
        return False
    if hashes != before:
        raise ValueError('Baseline differs; refusing stale or mixed source overwrite')
    encoded = (HERE/'source.patch.gz.b64').read_text().strip()
    patch = gzip.decompress(base64.b64decode(encoded, validate=True))
    if hashlib.sha256(patch).hexdigest() != manifest['patch_sha256']:
        raise ValueError('Source diff checksum mismatch')
    names = {line.split()[2].removeprefix('a/') for line in patch.decode().splitlines()
             if line.startswith('diff --git ')}
    if names != ALLOWED:
        raise ValueError('Source diff changes unexpected paths')
    subprocess.run(['git', 'apply', '--check', '-'], cwd=ROOT, input=patch, check=True)
    subprocess.run(['git', 'apply', '-'], cwd=ROOT, input=patch, check=True)
    hashes = {name: (hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                     if (ROOT/name).exists() else None) for name in ALLOWED}
    if hashes != after:
        raise ValueError('Integrated source differs from locally tested bytes')
    print('Integrated checksum-verified palette-read source changes')
    return True


if __name__ == '__main__':
    apply()
