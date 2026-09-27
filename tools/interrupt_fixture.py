"""Independent boundary fixtures: original NES dispatch versus native SNES entry.

NES input contains opcodes, operands and external request selections, not predicted
interrupt results. Native input uses PRE-entry registers/stack captured from the
original instruction, never that core's resulting interrupt frame or destination.
"""
from pathlib import Path
import subprocess
from guest_cycle_fixture import create_nes, NATIVE_DRIVER
from guest_cycle_fixture import cases as cycle_cases
from build_viewer import ROOT, tool, finalize_rom, validate_sfc
from interrupt_boundary import native_tables


def cases() -> list[dict]:
    # Two different real pre-instruction flag patterns per opcode.
    rows=[]
    for original in cycle_cases():
        if original['opcode']==0 or int(original['name'].split('-')[1])>1:
            continue
        for irq,nmi in ((False,False),(True,False),(False,True),(True,True)):
            rows.append(dict(original,name=f"{original['name']}-{int(irq)}{int(nmi)}",
                             irq=irq,nmi=nmi,initial_s=255))
    for s in range(256):
        for irq,nmi in ((True,False),(False,True)):
            rows.append(dict(name=f'stack-{s:03d}-{int(nmi)}',opcode=0xEA,pc=0x8100,
                             operand=0,p=0xF3,x=3,y=3,pointer=0x0200,
                             irq=irq,nmi=nmi,initial_s=s))
    return rows


def nes_fixture(out: Path, row: dict) -> Path:
    rom=create_nes(out,row)
    data=bytearray(rom.read_bytes())
    # Fixture reset is SEI,CLD,LDX #$FF,TXS. Select original guest S in the code,
    # not with a host memory/register write. Stop routines do not use the stack.
    pos=16+0x6000
    if data[pos:pos+5]!=bytes.fromhex('78d8a2ff9a'):
        raise ValueError('Unexpected authored reset sequence')
    data[pos+3]=row['initial_s']
    # Distinct explicit vectors distinguish priority without inferring it from P.
    for address in (0xE200,0xE300):
        offset=16+address-0x8000
        data[offset:offset+7]=bytes((0xA9,0x5A,0x85,0x7E,0x4C,(address+4)&255,(address+4)>>8))
    data[16+0x7FFA:16+0x7FFC]=(0xE300).to_bytes(2,'little')
    data[16+0x7FFE:16+0x8000]=(0xE200).to_bytes(2,'little')
    rom.write_bytes(data);return rom


def native_fixture(out: Path, inputs: list[tuple[bytes,bytes]], kernel: str|None=None) -> Path:
    if not 1<=len(inputs)<=64 or any(len(d)!=16 or len(s)!=256 for d,s in inputs):
        raise ValueError('Require 1..64 descriptor and whole-stack inputs')
    out.mkdir(parents=True,exist_ok=True)
    (out/'inputs.bin').write_bytes(b''.join(d+s for d,s in inputs))
    # Reuse the proven standalone caller-context driver; this is not the bridge.
    source=NATIVE_DRIVER.replace('GuestInstructionCycles','GuestInterruptBoundary')
    source=source.replace('guest_cycles.inc','guest_interrupt.inc').replace('$1840','$1860')
    source=source.replace('cpy #14','cpy #16')
    source=source.replace('    stx $1B00\n', '''    ldy #0
copy_stack:
    lda f:Inputs,x
    sta $0100,y
    inx
    iny
    cpy #256
    bne copy_stack
    stx $1B00
''')
    source=source.replace('    ldy #0\nsave_context:', '''    ldy #0
save_stack:
    lda $0100,y
    sta f:$7E4000,x
    inx
    iny
    cpy #256
    bne save_stack
    ldy #0
save_context:''')
    (out/'fixture.s').write_text(f'CASE_COUNT={len(inputs)}\n'+source)
    (out/'guest_interrupt.inc').write_text(kernel if kernel is not None else (ROOT/'snes/src/guest_interrupt.inc').read_text())
    (out/'tables.inc').write_text(native_tables())
    subprocess.run([tool('ca65'),'-g','-I',str(out),'--bin-include-dir',str(out),'-o',str(out/'fixture.o'),str(out/'fixture.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),'-o',str(out/'fixture.bin'),str(out/'fixture.o')],check=True)
    image=finalize_rom((out/'fixture.bin').read_bytes(),b'');validate_sfc(image)
    rom=out/'fixture.sfc';rom.write_bytes(image);return rom
