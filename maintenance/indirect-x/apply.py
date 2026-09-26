#!/usr/bin/env python3
"""One-time, source-only integration for the reviewed indirect-X candidate.

Refuse a different baseline instead of overwriting concurrent source changes.
No ROMs, credentials, or game-derived data are handled here.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]

def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f'Expected one source anchor: {old[:100]!r}')
    return text.replace(old, new, 1)

def apply() -> None:
    expected = {
        'snes/src/native.s': '8a215503e59476dca23ff6e997ca4db77cd366f3',
        'tools/build_native.py': '4c5d3080e7efadae4e6a2bb29780a56868a81f49',
    }
    source = {}
    for name, sha in expected.items():
        data = (ROOT/name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != sha:
            raise ValueError(f'{name}: baseline changed; expected {sha}, got {actual}')
        source[name] = data.decode('utf-8')
    source['snes/src/native.s'] = replace_once(source['snes/src/native.s'],
        '.include "native_indexed.inc"',
        '.include "native_indirect_x.inc"\n.include "native_indexed.inc"')
    s = source['tools/build_native.py']
    s = replace_once(s, 'native_poll:bool=False):',
                    'native_poll:bool=False,quick_indirect_x:bool=False):')
    s = replace_once(s, "write_text(f'USE_NATIVE_CONTROLLER=",
                    "write_text(f'USE_QUICK_INDIRECT_X={int(quick_indirect_x and quick_indirect)}\\nUSE_NATIVE_CONTROLLER=")
    s = replace_once(s, "        elif quick_io and mode=='abs' and name in ('LDA','STA'):",
        "        elif quick_indirect_x and quick_indirect and mode=='ix' and name in ('LDA','CMP','SBC','ADC','AND','ORA','EOR'):\n"
        "            quick.append('Quick'+name+'_IX')\n"
        "        elif quick_io and mode=='abs' and name in ('LDA','STA'):")
    s = replace_once(s, "'quick_indirect_reads':quick_indirect,",
        "'quick_indirect_reads':quick_indirect,'quick_indirect_x':bool(quick_indirect_x and quick_indirect),")
    s = replace_once(s, "    p.add_argument('--native-controller',",
        "    p.add_argument('--quick-indirect-x',action='store_true',help='Opt-in range-checked (zero-page,X) reads; --no-quick-indirect disables it')\n"
        "    p.add_argument('--native-controller',")
    s = replace_once(s, 'native_poll=a.native_controller);',
                    'native_poll=a.native_controller,quick_indirect_x=a.quick_indirect_x);')
    compile(s, 'tools/build_native.py', 'exec')
    source['tools/build_native.py'] = s
    for name, text in source.items():
        (ROOT/name).write_text(text, encoding='utf-8')
    print('Applied two checked source edits; option remains disabled by default.')

if __name__ == '__main__':
    apply()
