#!/usr/bin/env python3
"""Integrate two small source edits only when the exact baseline matches.

This is a one-time source integration step, not a ROM or binary upload.
All input and output hashes are checked before either file is written.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
BEFORE = {
    'tools/build_native.py': '230c9e08e389efbeebd3487e445c11e1440b6f20',
    'tools/verify_native_cpu.py': '4b6c7459e66161d09c4c60a0ddca485811c5bc48',
}
AFTER = {
    'tools/build_native.py': '3f84ad50916de1bcae935ec9a2dd475fa666fd5273aaddf61887883c4c6804cf',
    'tools/verify_native_cpu.py': '8ee794db2e8e278bfe579e73383025cb4969d11ae9ca0f8bb290e57a80a14514',
}

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one source anchor: {old[:90]!r}')
    return text.replace(old, new, 1)

def apply():
    source = {}
    for name, expected in BEFORE.items():
        raw = (ROOT/name).read_bytes()
        actual = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if actual != expected:
            raise ValueError(f'{name}: baseline changed; refusing to overwrite')
        source[name] = raw.decode('utf-8')
    s = source['tools/build_native.py']
    s = once(s, 'import native_controller\n', 'import native_controller\nimport native_dispatch\n')
    s = once(s, 'fill_cache_fix:bool=False):', 'fill_cache_fix:bool=False,native_inline_dispatch:bool=False):')
    s = once(s, "    (assets/'direct-stubs.inc').write_text(direct_source + poll_source)",
        "    dispatch_sites, dispatch_source = native_dispatch.plan(rom.prg, counts) if native_inline_dispatch and direct else ([], '')\n"
        "    (assets/'direct-stubs.inc').write_text(direct_source + poll_source + dispatch_source)")
    s = once(s, '    direct_code = native_controller.apply(direct_code, poll_sites, symbols)',
        '    direct_code = native_controller.apply(direct_code, poll_sites, symbols)\n'
        '    direct_code = native_dispatch.apply(direct_code, dispatch_sites, symbols)')
    s = once(s, "'native_controller_poll':bool(poll_sites)",
        "'native_inline_dispatch':bool(dispatch_sites),'native_dispatch_sites':dispatch_sites,'native_controller_poll':bool(poll_sites)")
    s = once(s, "    p.add_argument('--native-controller',",
        "    p.add_argument('--native-inline-dispatch',action='store_true',help='Guarded whole inline-table dispatch replacement')\n"
        "    p.add_argument('--native-controller',")
    s = once(s, 'native_poll=a.native_controller,', 'native_poll=a.native_controller,native_inline_dispatch=a.native_inline_dispatch,')
    source['tools/build_native.py'] = s
    source['tools/verify_native_cpu.py'] = once(source['tools/verify_native_cpu.py'],
        "('indexed_dummy_io_reads',0x998)", "('indexed_dummy_io_reads',0x998),('native_dispatch_calls',0x9B0)")
    for name, text in source.items():
        compile(text, name, 'exec')
        if hashlib.sha256(text.encode()).hexdigest() != AFTER[name]:
            raise ValueError(f'{name}: output checksum differs from the locally tested source')
    for name, text in source.items():
        (ROOT/name).write_text(text, encoding='utf-8')
    print('Integrated exactly tested source edits; new runtime option stays disabled by default.')

if __name__ == '__main__':
    apply()
