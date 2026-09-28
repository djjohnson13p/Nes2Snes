"""Guarded live CHR-size changes over the published A/B transfer adapter.

Hardware documentation and Nestopia disagree on stale-register interpretation.
This profile admits pattern accesses only after all active registers in the
selected set have been rewritten since the last actual mode change. It does
not infer missing hardware latch bits or use expected intermediate endpoints.
"""
from build_viewer import ROOT
from mmc5_cpu_io import replace_once
from mmc5_timeline import fragments, reassemble
from opcodes6502 import OPS
import chr_sets

PROFILE = 'mmc5-chr-rewrite-blank'
POLICY_ADDRESS = 0x5A09


def underlying(plan):
    if not isinstance(plan, dict) or plan.get('memory_model') != PROFILE:
        raise ValueError('Explicit rewrite-gated CHR profile required')
    result = dict(plan, memory_model=chr_sets.PROFILE)
    chr_sets.validate(result)
    return result


def validate(plan):
    underlying(plan)
    return plan


def initial(plan):
    return chr_sets.initial(underlying(plan))


def create_nes(out, plan):
    return chr_sets.create_nes(out, underlying(plan))


def create_native(out, plan, initial_state, **options):
    source = underlying(plan)
    chr_sets.create_native(out, source, initial_state, **options)
    (out/'chr_mode_rewrite.inc').write_bytes((ROOT/'snes/src/chr_mode_rewrite.inc').read_bytes())
    p = out/'fixture.s'; text = p.read_text()
    text = replace_once(text, '    jsr ChrSetsInit', '    jsr ChrSetsInit\n    jsr ChrLiveInit')
    text = replace_once(text, '.include "chr_sets.inc"', '.include "chr_sets.inc"\n.include "chr_mode_rewrite.inc"')
    text = replace_once(text, '    jsr ChrSetsCapture', '    jsr ChrSetsCapture\n    jsr ChrLiveCapture')
    p.write_text(text)
    p = out/'chr_sets.inc'
    p.write_text(replace_once(p.read_text(), '.proc ChrBank\n', '.proc ChrFixedBank\n'))
    p = out/'mmc5_chr_blank.inc'; text = p.read_text()
    text = replace_once(text, '.proc ChrModeWrite\n', '.proc ChrFixedModeWrite\n')
    text = replace_once(text, 'pattern:\n', 'pattern:\n    jsr ChrLiveReadCheck\n    lda PV+6\n')
    text = replace_once(text, '    lda #ChrMode\n    sta f:$7E5200,x',
                        '    lda f:CL_MODE\n    sta f:$7E5200,x')
    p.write_text(text)
    p = out/'program.inc'; text = p.read_text()
    for part in fragments(source):
        code = bytes.fromhex(part['code']); pos = 0
        while pos < len(code):
            op = code[pos]; size = OPS[op][2]
            address = int.from_bytes(code[pos+1:pos+size], 'little')
            if op == 0x8D and 0x5120 <= address <= 0x512B:
                label = f'ins_b{part["bank"]}_{part["origin"]+pos:04x}:\n'
                start = text.index(label)+len(label)
                end = text.index('    jmp retire\n', start)+len('    jmp retire\n')
                body = text[start:end]
                body = replace_once(body, '    jmp retire\n',
                    '    rep #$30\n.a16\n.i16\n    lda f:CL_VALID\n'
                    f'    ora #${1 << (address-0x5120):04X}\n    sta f:CL_VALID\n    jmp retire\n')
                text = text[:start]+body+text[end:]
            pos += size
    p.write_text(text)
    return reassemble(out)
