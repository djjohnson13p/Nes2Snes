"""RAM-only OAM DMA on the protected blanked timeline.

A real original-program DMA synchronizes the authored boot to a known get/put
phase. Native time zero is that declared entry phase, not a reference timestamp.
Only absolute STA $4014, internal-RAM sources, forced blank and no guest requests
are admitted. DMC, external-source bus effects and rendering remain unsupported.
"""
from native_fixture import Program
from build_viewer import ROOT
from mmc5_cpu_io import replace_once
from mmc5_timeline import fragments, reassemble
from opcodes6502 import OPS
import chr_mode_rewrite as previous

PROFILE = 'mmc5-oam-dma-ram'
STATE_ADDRESS = 0x5B00
LOG_ADDRESS = 0x6000
SYNC_PC = 0xF200


def masked_code(code):
    """Replace only decoded absolute DMA stores for the inherited validator."""
    if not isinstance(code,bytes):raise ValueError('Require immutable instruction bytes')
    data=bytearray(code);pos=0
    while pos<len(data):
        if data[pos] not in OPS:raise ValueError('Unknown instruction')
        size=OPS[data[pos]][2]
        if pos+size>len(data):raise ValueError('Truncated instruction')
        if size==3 and data[pos:pos+3]==b'\x8d\x14\x40':
            data[pos+1:pos+3]=b'\x02\x20'
        pos+=size
    return bytes(data)


def underlying(plan):
    if not isinstance(plan, dict) or plan.get('memory_model') != PROFILE:
        raise ValueError('Explicit RAM-DMA profile required')
    if not isinstance(plan.get('bank_code'),list):raise ValueError('Require a bank-code list')
    result = dict(plan, memory_model=previous.PROFILE)
    result['bank_code'] = [dict(p) for p in plan['bank_code']]
    for part in [result]+result['bank_code']:
        part['code']=masked_code(bytes.fromhex(part['code'])).hex()
    previous.validate(result)
    # The timing observer records logical PCs, not mapper-qualified instruction
    # identities. Refuse overlapping CPU ranges rather than guessing the bank.
    intervals=[]
    for part in fragments(result):
        start=part['origin'];end=start+len(bytes.fromhex(part['code']))
        if any(start<b and end>a for a,b in intervals):
            raise ValueError('DMA timing requires unambiguous CPU instruction ranges')
        intervals.append((start,end))
    # Extra original boot helper, separate from code and the inherited PPU helper.
    for part in fragments(result):
        if part['bank']==result['prg_banks']-1 and part['origin']<SYNC_PC+64 and part['origin']+len(bytes.fromhex(part['code']))>SYNC_PC:
            raise ValueError('Code overlaps phase-synchronization boot helper')
    for item in result['bank_data']:
        if item['bank']==result['prg_banks']-1 and item['offset']<0x1240 and item['offset']+len(bytes.fromhex(item['bytes']))>0x1200:
            raise ValueError('Data overlaps phase-synchronization boot helper')
    return result


def validate(plan):
    underlying(plan)
    return plan


def initial(plan):
    return previous.initial(underlying(plan))


def sync_code(plan):
    p=Program(SYNC_PC)
    for address,value in ((0x2003,0),(0x4014,7),(0x2002,0x20)):
        p.op('LDA','imm',value);p.op('STA','abs',address)
    # After the synchronizing transfer the next opcode fetch is a GET.
    # This tail is 20 cycles; X/Y/S and the declared initial P/A are restored.
    p.op('LDA','imm',0x24);p.op('PHA');p.op('LDA','imm',plan['a']);p.op('PLP')
    p.op('JMP','abs',plan['origin'])
    return p.finish()


def create_nes(out,plan):
    source=underlying(plan);path=previous.create_nes(out,source)
    raw=bytearray(path.read_bytes());bank=16+(plan['prg_banks']-1)*8192
    boot=bytes(raw[bank:bank+256]);needle=b'\x4c'+plan['origin'].to_bytes(2,'little')
    if boot.count(needle)!=1:raise ValueError('Original boot entry anchor changed')
    at=bank+boot.index(needle);raw[at:at+3]=b'\x4c'+SYNC_PC.to_bytes(2,'little')
    sync=sync_code(plan);raw[bank+0x1200:bank+0x1200+len(sync)]=sync
    for part in fragments(plan):
        at=16+part['bank']*8192+(part['origin']&8191);code=bytes.fromhex(part['code'])
        raw[at:at+len(code)]=code
    path.write_bytes(raw);return path


def create_native(out,plan,initial_state,**options):
    source=underlying(plan);previous.create_native(out,source,initial_state,**options)
    raw=create_nes(out/'original',plan).read_bytes()
    (out/'original-prg.bin').write_bytes(raw[16:16+plan['prg_banks']*8192])
    (out/'oam_dma_timeline.inc').write_bytes((ROOT/'snes/src/oam_dma_timeline.inc').read_bytes())
    path=out/'fixture.s';text=path.read_text()
    text=replace_once(text,'    jsr ChrLiveInit','    jsr ChrLiveInit\n    jsr OamDmaInit')
    text=replace_once(text,'.include "chr_mode_rewrite.inc"','.include "chr_mode_rewrite.inc"\n.include "oam_dma_timeline.inc"')
    text=replace_once(text,'    jsr ChrLiveCapture','    jsr ChrLiveCapture\n    jsr OamDmaCapture')
    path.write_text(text)
    path=out/'program.inc';text=path.read_text()
    for part in fragments(plan):
        code=bytes.fromhex(part['code']);pos=0
        while pos<len(code):
            size=OPS[code[pos]][2]
            if code[pos:pos+3]==b'\x8d\x14\x40':
                label=f'ins_b{part["bank"]}_{part["origin"]+pos:04x}:\n'
                a=text.index(label)+len(label);b=text.index('    jmp retire\n',a)+len('    jmp retire\n')
                body=replace_once(text[a:b],'    lda #$2002\n','    lda #$4014\n')
                body=replace_once(body,'    jsr PpuLatchWrite\n','    jsr OamDmaRun\n')
                text=text[:a]+body+text[b:]
            pos+=size
    path.write_text(text);return reassemble(out)
