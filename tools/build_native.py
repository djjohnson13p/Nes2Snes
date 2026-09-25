#!/usr/bin/env python3
"""Build an experimental trace-bounded native 65C816 execution bridge.

Original ROM/data and generated derivatives stay in build/. This is NOT a
universal converter. Unclassified code paths trap instead of executing guesses.
"""
from __future__ import annotations
import argparse, json, struct, subprocess, hashlib
from pathlib import Path
from rom import Rom
from opcodes6502 import OPS
from build_viewer import ROOT, tool, finalize_rom, validate_sfc
from graphics import nes_to_snes
from native_cfg import expand

OPERATIONS = {'LDA':1,'LDX':2,'LDY':3,'STA':4,'STX':5,'STY':6,
              'AND':7,'ORA':8,'EOR':9,'ADC':10,'SBC':11,'CMP':12,
              'CPX':13,'CPY':14,'BIT':15,'ASL':16,'LSR':17,'ROL':18,
              'ROR':19,'INC':20,'DEC':21}
MODES={'zp':0,'zpx':1,'zpy':2,'abs':3,'absx':4,'absy':5,'ix':6,'iy':7}

def classify_patch(prg:bytes, counts:list[int]):
    if len(counts)!=len(prg): raise ValueError('Trace size does not match PRG.')
    covered=bytearray(len(prg)); patched=bytearray(len(prg)); sites=[]; skipped=[]
    for i,count in enumerate(counts):
        if not count:continue
        if prg[i] not in OPS:raise ValueError(f'Unsupported opcode at ${i:06X}')
        name,mode,n=OPS[prg[i]]
        if i+n>len(prg) or any(counts[i+1:i+n]):raise ValueError(f'Overlapping or truncated code at ${i:06X}')
        covered[i:i+n]=b'\x01'*n;patched[i:i+n]=prg[i:i+n]
        addr=int.from_bytes(prg[i+1:i+n],'little')
        intercept=(name in OPERATIONS and (mode in ('zpx','zpy','ix','iy') or
                    (mode in ('abs','absx','absy') and (0x0800<=addr<0x8000 or
                     (mode!='abs' and addr>=0xFF01)))))
        if name=='TXS':
            # The traced reset sets X=$FF. Bootstrap already established $01FF.
            # Other stack replacements need a separate, explicit translation.
            if i<2 or prg[i-2:i]!=b'\xa2\xff':raise ValueError('Non-reset TXS needs translation.')
            patched[i]=0xEA;skipped.append(i)
        elif name in ('SED','BRK'):
            raise ValueError(f'{name} needs an explicit semantic translation at ${i:06X}')
        elif name=='JMP' and mode=='ind' and addr&255==255:
            raise ValueError('NMOS indirect-JMP page-wrap case needs translation.')
        elif intercept:
            if n<2:raise AssertionError('COP requires two bytes.')
            patched[i:i+2]=bytes((0x02,prg[i]))
            sites.append({'prg_offset':i,'opcode':prg[i],'operation':name,'mode':mode})
    return bytes(patched), {'observed_instruction_sites':sum(bool(x) for x in counts),
        'classified_code_bytes':sum(covered),'trap_sites':sites,'reset_txs_nop_offsets':skipped,
        'unclassified_execution':'BRK fail-closed trap; raw data remains intact'}

def build(rom_path:Path,trace:Path,out:Path):
    rom=Rom.read(rom_path)
    if rom.mapper!=5 or len(rom.prg)!=0x40000 or len(rom.chr)!=0x20000:
        raise ValueError('Current bridge requires mapper 5, 256 KiB PRG, 128 KiB CHR.')
    summary=json.loads((trace/'trace-summary.json').read_text())
    if summary['rom_sha256']!=rom.metadata()['sha256']:raise ValueError('Trace ROM hash mismatch.')
    counts=list(struct.unpack('<262144I',(trace/'counts.u32').read_bytes()))
    pcs=list(struct.unpack("<262144H",(trace/"cpu-address.u16").read_bytes()))
    observed_count=sum(c>0 for c in counts)
    counts,cfg=expand(rom.prg,counts,pcs)
    code,info=classify_patch(rom.prg,counts)
    info["observed_instruction_sites"]=observed_count
    info.update({k:v for k,v in cfg.items() if k!="inferred_offsets"})
    out.mkdir(parents=True,exist_ok=True)
    (out/"cfg-inference.json").write_text(json.dumps(cfg,indent=2)+"\n")
    assets=out/'native-assets';assets.mkdir(exist_ok=True)
    nmi,reset,irq=struct.unpack_from('<HHH',rom.prg,0x3fffa)
    (assets/'config.inc').write_text(f'GUEST_NMI=${nmi:04X}\nGUEST_RESET=${reset:04X}\nGUEST_IRQ=${irq:04X}\n')
    for name,data in [('operation.bin',bytes(OPERATIONS.get(OPS.get(o,('',))[0],0) for o in range(256))),
                      ('mode.bin',bytes(MODES.get(OPS.get(o,('', ''))[1],255) for o in range(256))),
                      ('length.bin',bytes(OPS.get(o,('', '',0))[2] for o in range(256)))]:
        (assets/name).write_bytes(data)
    # All 16 main 16 KiB banks x the two observed C000 banks (30 and 7).
    # Raw data banks $81-$A0; independently patched executable banks $A1-$C0.
    images=[]
    for data in (rom.prg,code):
        for slot in range(32):
            primary=slot&15;c_bank=7 if slot&16 else 30
            images.append(data[primary*0x4000:(primary+1)*0x4000]+data[c_bank*0x2000:(c_bank+1)*0x2000]+data[0x3e000:])
    payload=b''.join(images)
    # Graphics are statically converted once, not decoded on every frame.
    payload+=nes_to_snes(rom.chr,2)+nes_to_snes(rom.chr,4)+rom.chr
    # Capture palette is an emulator RGB choice, not a physical color claim.
    rgb=(trace/'rgb-palette.bin').read_bytes() if (trace/'rgb-palette.bin').exists() else None
    if rgb is None:
        # Original project defaults to captured FCEUmm palette; require explicit input.
        raise ValueError('Trace needs rgb-palette.bin (192 bytes from probe kind 14).')
    if len(rgb)!=192:raise ValueError('Invalid RGB palette length.')
    palette=struct.pack('<64H',*[((rgb[i]>>3)|((rgb[i+1]>>3)<<5)|((rgb[i+2]>>3)<<10)) for i in range(0,192,3)])
    (assets/'palette.bin').write_bytes(palette)
    subprocess.run([tool('ca65'),'-g','-I',str(ROOT/'snes/src'),'-I',str(assets),'--bin-include-dir',str(assets),
                    '-l',str(out/'native.lst'),'-o',str(out/'native.o'),str(ROOT/'snes/src/native.s')],check=True)
    subprocess.run([tool('ld65'),'-C',str(ROOT/'snes/linker/viewer.cfg'),'-Ln',str(out/'native.lbl'),
                    '-m',str(out/'native.map'),'-o',str(out/'native-core.bin'),str(out/'native.o')],check=True)
    raw=finalize_rom((out/'native-core.bin').read_bytes(),payload)
    (out/'native-prototype.sfc').write_bytes(raw)
    info.update(validate_sfc(raw));info.update({'rom_sha256':rom.metadata()['sha256'],
       'renderer':'experimental live PPU bridge','audio_implemented':False,
       'complete_game_port':False,'prg_mode':2,'supported_c000_banks':[30,7],
       'native_execution_banks':32,'notes':'Unclassified code traps; compatibility and timing require validation.'})
    (out/'native-build.json').write_text(json.dumps(info,indent=2)+'\n')
    return info

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--trace',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();s=build(a.rom,a.trace,a.out);print(json.dumps({k:v for k,v in s.items() if k!='trap_sites'},indent=2))
