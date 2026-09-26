"""Recognize a complete, classified serial-controller polling idiom.

Only near JSR call sites change. The original body and all other entries stay
intact. A WRAM wrapper checks the runtime preconditions and otherwise tail-jumps
to the original routine. No addresses of a commercial game are hard-coded.
"""
from __future__ import annotations
from opcodes6502 import OPS

# Eight serial reads into two adjacent zero-page bytes. Scratch locations 4/5
# require the native fast path to restrict X to 0..2; all other X use the body.
PATTERN = (
    ('LDY','imm',1), ('STY','abs',0x4016), ('DEY','imp',0),
    ('STY','abs',0x4016), ('LDY','imm',8),
    ('LDA','abs',0x4016), ('STA','zp',4), ('LSR','acc',0),
    ('ORA','zp',4), ('LSR','acc',0), ('ROL','zpx',0),
    ('LDA','abs',0x4017), ('STA','zp',5), ('LSR','acc',0),
    ('ORA','zp',5), ('LSR','acc',0), ('ROL','zpx',1),
    ('DEY','imp',0), ('BNE','rel',0xE7), ('RTS','imp',0),
)


def matches(prg: bytes, counts: list[int], offset: int) -> bool:
    if len(counts) != len(prg):
        raise ValueError('Classification size differs from PRG')
    for name, mode, value in PATTERN:
        if offset < 0 or offset >= len(prg) or not counts[offset]:return False
        op=OPS.get(prg[offset])
        if not op or op[:2] != (name,mode):return False
        size=op[2]
        if offset+size>len(prg) or any(counts[offset+1:offset+size]):return False
        if int.from_bytes(prg[offset+1:offset+size],'little') != value:return False
        offset+=size
    return True


def plan(prg:bytes, counts:list[int]) -> tuple[list[dict],str]:
    if len(prg)!=0x40000 or len(counts)!=len(prg):
        raise ValueError('Expected classified 256-KiB PRG')
    sites=[];targets=set()
    for i,c in enumerate(counts):
        if not c or prg[i]!=0x20 or i+3>len(prg) or any(counts[i+1:i+3]):continue
        address=int.from_bytes(prg[i+1:i+3],'little')
        # This bridge has a fixed final 8 KiB bank in every supported mapping.
        if not 0xe000<=address<0xfffa:continue
        if not matches(prg,counts,0x3e000+address-0xe000):continue
        label=f'NativeController_{address:04X}'
        sites.append(dict(prg_offset=i,original_target=address,label=label))
        targets.add(address)
    lines=['; Generated controller wrappers; original bodies remain intact.',
           '.segment "STUBS"','.a8','.i8']
    for address in sorted(targets):
        lines += [f'NativeController_{address:04X}:','    php','    pha',
                  '    lda RUNNING','    cmp #$01','    bne @fallback',
                  '    cpx #$03','    bcs @fallback','    pla','    plp',
                  '    jsl $800000+NativeControllerPoll','    rts','@fallback:',
                  '    pla','    plp',f'    jmp ${address:04X}']
    lines += ['.segment "CODE"']
    return sites,'\n'.join(lines)+'\n'


def apply(code:bytes, sites:list[dict], symbols:dict[str,int]) -> bytes:
    result=bytearray(code)
    for site in sites:
        i=site['prg_offset'];target=site['original_target'];address=symbols[site['label']]
        if not 0x1000<=address<0x1800:raise ValueError('Wrapper outside reserved WRAM')
        if result[i:i+3] != bytes((0x20,target&255,target>>8)):
            raise ValueError('Controller replacement must be an unchanged classified JSR')
        result[i:i+3]=bytes((0x20,address&255,address>>8))
    return bytes(result)
