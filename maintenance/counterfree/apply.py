"""One-use, hash-checked source transfer. Never copies ROMs or build outputs."""
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

root = Path.cwd().resolve()
manifest = json.loads((root/'maintenance/counterfree/manifest.json').read_text())
subprocess.run(['git', 'merge-base', '--is-ancestor', manifest['base'], 'HEAD'], check=True)
pending = {}
for entry in manifest['files']:
    name = entry['path']
    parts = PurePosixPath(name).parts
    if name != 'README.md' and (not parts or parts[0] not in ('docs', 'snes', 'tools', 'tests')):
        raise ValueError('Unsupported source path: '+name)
    if '..' in parts or PurePosixPath(name).is_absolute() or name in pending:
        raise ValueError('Unsafe or duplicate path: '+name)
    path = root/name
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError('Source symlink is not allowed: '+name)
    if entry['before'] is None:
        if path.exists():
            raise ValueError('New source already exists: '+name)
        if entry['payload'] != 'maintenance/counterfree/'+name:
            raise ValueError('Incorrect staged path: '+name)
        result = (root/entry['payload']).read_bytes()
    else:
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != entry['before']:
            raise ValueError('Before hash mismatch: '+name)
        edits = entry['edits']
        end = 0
        for first, last, text in edits:
            if not (end <= first <= last <= len(original)) or not isinstance(text, str):
                raise ValueError('Invalid byte edit: '+name)
            end = last
        result = original
        for first, last, text in reversed(edits):
            result = result[:first]+text.encode('utf-8')+result[last:]
    result.decode('utf-8')
    if hashlib.sha256(result).hexdigest() != entry['after']:
        raise ValueError('After hash mismatch: '+name)
    pending[name] = result
if len(pending) != 14:
    raise ValueError('Expected exactly fourteen source files')
for name, content in pending.items():
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
subprocess.run(['git', 'add', '--', *pending], check=True)
print('All fourteen source files match the locally tested hashes.')
