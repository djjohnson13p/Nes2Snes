#!/usr/bin/env python3
"""Integrate reviewed renderer options into exactly the checked baseline.

All source preconditions and resulting hashes are checked before any writes.
No game data, binary payloads, network calls or credentials are handled here.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
BEFORE = {
    'snes/src/native_video.inc': '4ef07bbf0737366a1b1981a142577926b8564f41',
    'tools/build_native.py': '0dfe26a32c7f01a01c809be38db4fc7ce45f1a63',
}
AFTER = {
    'snes/src/native_video.inc': '108a439f3d313a5df5f81bdce1b10e2b5c3762f864389a14f7bc5c53c2edad56',
    'tools/build_native.py': '0f14b098169002229d8a3680b3d54f5e6dbfbbdac6b30086ccb24bb0da619087',
}

def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Expected one source anchor: ' + repr(old[:100]))
    return text.replace(old, new, 1)

def apply() -> None:
    texts = {}
    for name, expected in BEFORE.items():
        data = (ROOT/name).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob != expected:
            raise ValueError(f'{name}: baseline changed; refusing to overwrite it')
        texts[name] = data.decode('utf-8')
    video = texts['snes/src/native_video.inc']
    video = once(video, '\nRenderFrame:\n', '\n.include "native_fill_cache.inc"\n\nRenderFrame:\n')
    video = once(video, '    jsr SelectBgBanks\n    ; Dirty physical',
        '    jsr SelectBgBanks\n.if USE_FILL_CACHE_FIX\n    jsr UpdateFillCache\n.endif\n    ; Dirty physical')
    video = once(video, '    jsr UploadCharacters\n    jsr UploadNametables\n',
        '    jsr UploadCharacters\n.if USE_COALESCED_NT_DMA\n    jsr UploadNametablesCoalesced\n.else\n    jsr UploadNametables\n.endif\n')
    video = once(video, '\nUploadNametables:\n', '\n.include "native_nametable_dma.inc"\n\nUploadNametables:\n')
    video = once(video, 'ConvertNametable:\n.a16\n.i16\n',
        'ConvertNametable:\n.a16\n.i16\n.if USE_FILL_CACHE_FIX\n'
        '    ; Fill registers can change without a routing or physical nametable write.\n'
        '    lda VROUTE\n    cmp #$0003\n    bne :+\n    lda FILL_CHANGED\n'
        '    and #$00FF\n    bne @needed\n:\n.endif\n')
    video = once(video, '    cmp #$0003\n    beq @next\n',
        '    cmp #$0003\n.if USE_FILL_CACHE_FIX\n    bne :+\n    lda FILL_CHANGED\n'
        '    and #$00FF\n    beq @next\n    bra @convert\n:\n.else\n    beq @next\n.endif\n')
    texts['snes/src/native_video.inc'] = video
    source = texts['tools/build_native.py']
    source = once(source, 'quick_indirect_x:bool=False):',
        'quick_indirect_x:bool=False,coalesced_nt_dma:bool=False,fill_cache_fix:bool=False):')
    source = once(source, "write_text(f'USE_QUICK_INDIRECT_X=",
        "write_text(f'USE_FILL_CACHE_FIX={int(fill_cache_fix)}\\nUSE_COALESCED_NT_DMA={int(coalesced_nt_dma)}\\nUSE_QUICK_INDIRECT_X=")
    source = once(source, "'native_controller_poll':bool(poll_sites),",
        "'fill_cache_fix':fill_cache_fix,'coalesced_nametable_dma':coalesced_nt_dma,'native_controller_poll':bool(poll_sites),")
    source = once(source, "    p.add_argument('--quick-indirect-x',",
        "    p.add_argument('--fix-fill-cache',action='store_true',help='Invalidate cached fill backgrounds when the mapper tile or color changes')\n"
        "    p.add_argument('--coalesced-nametable-dma',action='store_true',help='Group contiguous changed background rows without copying clean rows')\n"
        "    p.add_argument('--quick-indirect-x',")
    source = once(source, 'quick_indirect_x=a.quick_indirect_x);',
        'quick_indirect_x=a.quick_indirect_x,coalesced_nt_dma=a.coalesced_nametable_dma,fill_cache_fix=a.fix_fill_cache);')
    compile(source, 'tools/build_native.py', 'exec')
    texts['tools/build_native.py'] = source
    for name, text in texts.items():
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != AFTER[name]:
            raise ValueError(f'{name}: resulting source does not match the tested candidate')
    for name, text in texts.items():
        (ROOT/name).write_text(text, encoding='utf-8')
    print('Integrated both optional renderer paths with exact source hashes.')

if __name__ == '__main__':
    apply()
