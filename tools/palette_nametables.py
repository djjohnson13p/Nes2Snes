"""Blanked MMC5 nametable behavior verified with the Nestopia endpoint oracle.

This specializes only the palette adapter. Older FCEUmm-observed profiles retain
both their code and their explicitly recorded reference disagreements. ExRAM
modes 0/1 are still refused by the inherited CPU-I/O register handler.
"""
from pathlib import Path
from mmc5_cpu_io import replace_once


def prepare_native(out: Path) -> None:
    """Use documented color bits and mode-2/3 zero reads without new scratch."""
    p = out/'mmc5_ppu_blank.inc'
    text = p.read_text()
    if text.count('.proc PpuMap\n') != 1:
        raise ValueError('Changed nametable mapping routine')
    start = text.index('.proc PpuMap\n')
    end = text.index('.endproc', start) + len('.endproc')
    text = text[:start] + '''.proc PpuMap
    sep #$20
.a8
    lda GT+6
    sta PV+10
    rts
.endproc''' + text[end:]
    text = replace_once(text, '''    cmp #4
    bcc :+
    ; Pinned FCEUmm does not mask upper bits; do not adopt its discrepancy.
    jmp PpuUnsupported
:
    sta PV+12''', '''    ; Only the low two written bits choose the four replicated palette fields.
    and #3
    sta PV+12''')
    text = replace_once(text, '    cmp #2\n    beq unsupported',
                        '    cmp #2\n    beq zero_source')
    text = replace_once(text, 'unsupported:\n    jmp PpuUnsupported', '''zero_source:
    ; Source 2 is disconnected from CPU ExRAM in the admitted modes 2/3.
    lda #0
    rts
unsupported:
    jmp PpuUnsupported''')
    text = replace_once(text, '    cmp #3\n    beq ignored',
                        '    cmp #2\n    bne :+\n    jmp PpuUnsupported\n:\n    cmp #3\n    beq ignored')
    ppu_text = text
    p = out/'palette_timeline.inc'
    text = p.read_text()
    text = replace_once(text, '''    cmp #2
    bne :+
    jmp PpuUnsupported
:
    cmp #3''', '''    cmp #2
    bne :+
    lda #0
    rts
:
    cmp #3''')
    (out/'mmc5_ppu_blank.inc').write_text(ppu_text)
    p.write_text(text)
