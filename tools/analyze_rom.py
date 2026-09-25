#!/usr/bin/env python3
"""Validate/extract a ROM; optionally generate trace-guided matching bank sources.

Unobserved bytes are retained as byte tables, not guessed to be either code or
semantic data. A byte-identical rebuild establishes preservation, not complete
reverse engineering and certainly not an SNES port.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
from rom import Rom,sha256
from graphics import nes_to_snes,snes_to_nes
from opcodes6502 import OPS,REGISTERS,format_instruction
from build_viewer import tool


def extract(rom:Rom,out:Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    (out/'prg.bin').write_bytes(rom.prg);(out/'chr.bin').write_bytes(rom.chr)
    if rom.trainer:(out/'trainer.bin').write_bytes(rom.trainer)
    for bpp in (2,4):
        converted=nes_to_snes(rom.chr,bpp)
        assert snes_to_nes(converted,bpp)==rom.chr
        (out/f'chr.snes{bpp}bpp').write_bytes(converted)
    banks=out/'banks';banks.mkdir(exist_ok=True)
    for i in range(0,len(rom.prg),8192):
        (banks/f'prg-{i//8192:02X}.bin').write_bytes(rom.prg[i:i+8192])
    meta=rom.metadata()
    meta['chr_conversion_roundtrip']={'2bpp':True,'4bpp':True}
    (out/'rom-analysis.json').write_text(json.dumps(meta,indent=2)+'\n')
    return meta


def matching_disassembly(rom:Rom,trace:Path,out:Path) -> dict:
    summary=json.loads((trace/'trace-summary.json').read_text())
    if summary['rom_sha256'] != sha256(rom.raw):
        raise ValueError('Trace belongs to a different ROM. Refusing to classify bytes.')
    if len(rom.prg)%8192:raise ValueError('This bank workflow requires complete 8 KiB PRG banks.')
    counts_raw=(trace/'counts.u32').read_bytes();pcs_raw=(trace/'cpu-address.u16').read_bytes()
    if len(counts_raw)!=len(rom.prg)*4 or len(pcs_raw)!=len(rom.prg)*2:
        raise ValueError('Trace dimensions do not match the ROM.')
    counts=struct.unpack('<'+'I'*len(rom.prg),counts_raw)
    pcs=struct.unpack('<'+'H'*len(rom.prg),pcs_raw)
    out.mkdir(parents=True,exist_ok=True)
    verified=[];rebuilt=[];observed_bytes=0;unsupported=[]
    for bank,offset in enumerate(range(0,len(rom.prg),8192)):
        data=rom.prg[offset:offset+8192]
        bases={pcs[offset+j]-j for j in range(8192) if counts[offset+j]}
        if len(bases)>1:raise ValueError(f'Bank {bank:02X} executed at multiple addresses; split its views first.')
        base=next(iter(bases)) if bases else (0xE000 if offset+8192==len(rom.prg) else
                                             0xC000 if offset+16384==len(rom.prg) else
                                             0x8000+(bank%2)*8192)
        marks=bytearray(8192)
        for j in range(8192):
            if not counts[offset+j]:continue
            op=OPS.get(data[j])
            if not op:
                unsupported.append({'prg_offset':offset+j,'opcode':data[j]});continue
            length=op[2]
            if j+length>8192:raise ValueError('Observed instruction crosses a PRG-bank boundary.')
            marks[j:j+length]=bytes([1])*length
        observed_bytes+=sum(marks)
        name=f'bank-{bank:02X}'
        binary=out/(name+'.bin');binary.write_bytes(data)
        info=[f'GLOBAL {{ STARTADDR ${base:04X}; CPU "6502"; COMMENTS 4; }};']
        start=0
        for end in range(1,8193):
            if end==8192 or marks[end]!=marks[start]:
                kind='Code' if marks[start] else 'ByteTable'
                info.append(f'RANGE {{ START ${base+start:04X}; END ${base+end-1:04X}; TYPE {kind}; }};')
                start=end
        for addr,label in REGISTERS.items():
            info.append(f'LABEL {{ NAME "{label}"; ADDR ${addr:04X}; }};')
        if bank==len(rom.prg)//8192-1 and base==0xE000:
            for label,addr in zip(('Nmi','Reset','Irq'),struct.unpack('<HHH',rom.prg[-6:])):
                info.append(f'LABEL {{ NAME "{label}"; ADDR ${addr:04X}; }};')
        (out/(name+'.info')).write_text('\n'.join(info)+'\n')
        subprocess.run([tool('da65'),'-i',str(out/(name+'.info')),'-o',str(out/(name+'.s')),str(binary)],check=True)
        subprocess.run([tool('ca65'),'-o',str(out/(name+'.o')),str(out/(name+'.s'))],check=True)
        cfg=f'MEMORY {{ R: start = ${base:04X}, size = $2000, file = %O; }}\nSEGMENTS {{ CODE: load = R, type = ro; }}\n'
        (out/(name+'.cfg')).write_text(cfg)
        rebuilt_path=out/(name+'-rebuilt.bin')
        subprocess.run([tool('ld65'),'-C',str(out/(name+'.cfg')),'-o',str(rebuilt_path),str(out/(name+'.o'))],check=True)
        reassembled=rebuilt_path.read_bytes()
        if reassembled!=data:raise ValueError(f'Reassembly mismatch in bank {bank:02X}.')
        rebuilt.append(reassembled)
        verified.append({'bank':bank,'cpu_base':f'${base:04X}','address_observed':bool(bases),
                         'observed_code_bytes':sum(marks),'sha256':sha256(data),'matching':True})
    whole=rom.header+rom.trainer+b''.join(rebuilt)+rom.chr+rom.trailing
    assert whole==rom.raw
    (out/'rebuilt.nes').write_bytes(whole)
    result={'rom_sha256':sha256(rom.raw),'reassembled_sha256':sha256(whole),
            'byte_identical':True,'prg_banks_verified':len(verified),
            'observed_code_bytes':observed_bytes,'unclassified_bytes':len(rom.prg)-observed_bytes,
            'unsupported_observed_opcodes':unsupported,'banks':verified,
            'complete_semantic_disassembly':False,'playable_snes_port':False}
    (out/'rebuild-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    listing=['; Observed hardware-access instruction sites only. Not complete game coverage.']
    for site in summary['io_sites']:
        off=int(site['prg_offset'],16);pc=int(site['cpu_address'][1:],16)
        listing.append(f"; PRG {off:06X} CPU ${pc:04X} count={site['execution_count']} "
                       f"observed={site['min_address']}..{site['max_address']}\n"
                       +format_instruction(rom.prg[off:off+3],pc))
    (out/'hardware-sites.txt').write_text('\n'.join(listing)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom',type=Path);p.add_argument('--out',type=Path,default=Path('build/analysis'))
    p.add_argument('--trace',type=Path);args=p.parse_args()
    try:
        rom=Rom.read(args.rom);meta=extract(rom,args.out)
        print(json.dumps(meta,indent=2))
        if args.trace:
            result=matching_disassembly(rom,args.trace,args.out/'disassembly')
            print(json.dumps({k:v for k,v in result.items() if k!='banks'},indent=2))
    except (ValueError,OSError,RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'Analysis failed: {exc}',file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
