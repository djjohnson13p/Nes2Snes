#!/usr/bin/env python3
"""Extract address-only classification metadata from a separately built reference.

No program bytes, source text, graphics or audio are emitted. The whole-PRG hash
must match a user's local input before any of these classification hints are used.
A reference disassembly can include junk decoded as instructions; these are hints,
not execution coverage or a proof that every listed instruction is reachable.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

REFERENCE_REPO='https://github.com/vinheim3/castlevania3-disasm'
REFERENCE_COMMIT='3272648f2bbf95f6cb11d947feca73b852a99f10'
WLA_COMMIT='91c52b1f4ef3cc8ba3c0638f7536539579af6a9f'
MNEMONICS=set('ADC AND ASL BCC BCS BEQ BIT BMI BNE BPL BRK BVC BVS CLC CLD CLI CLV CMP CPX CPY DEC DEX DEY EOR INC INX INY JMP JSR LDA LDX LDY LSR NOP ORA PHA PHP PLA PLP ROL ROR RTI RTS SBC SEC SED SEI STA STX STY TAX TAY TSX TXA TXS TYA'.split())
PREFIX=re.compile(r'^\s*(\d+)\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]{4})\s+((?:[0-9A-F]{2}\s+)+)(.*)$')
SOURCE=re.compile(r'^\s*(?:[A-Za-z_@.][\w@.]*:\s*)?([A-Za-z]{3})(?:[.\s]|$)')

def extract(reference:Path,out:Path)->dict:
    data=(reference/'castlevania3.bin').read_bytes()
    if len(data)!=262144:raise ValueError(f'Unexpected reference PRG size {len(data)}')
    entries={};source_files=set();conflicts=[]
    for listing in sorted(reference.rglob('*.lst')):
        for line in listing.read_text(errors='strict').splitlines():
            m=PREFIX.match(line)
            if not m:continue
            line_number,bank,slot,pc,offset,hex_bytes,source=m.groups()
            ins=SOURCE.match(source.split(';',1)[0])
            if not ins or ins.group(1).upper() not in MNEMONICS:continue
            raw=bytes.fromhex(hex_bytes)
            if not 1<=len(raw)<=3:continue
            physical=int(bank,16)*8192+int(offset,16)
            if data[physical:physical+len(raw)]!=raw:raise ValueError('Listing/binary byte mismatch')
            item=[physical,int(pc,16),len(raw)]
            if physical in entries and entries[physical]!=item:conflicts.append(physical)
            entries[physical]=item;source_files.add(str(listing.relative_to(reference)))
    if conflicts:raise ValueError(f'Conflicting listing addresses: {len(conflicts)}')
    if len(entries)<1000:raise ValueError(f'Too few instruction hints: {len(entries)}')
    result={'reference_repository':REFERENCE_REPO,'reference_commit':REFERENCE_COMMIT,
            'assembler_commit':WLA_COMMIT,'prg_sha256':hashlib.sha256(data).hexdigest(),
            'prg_size':len(data),'record_format':['prg_offset','cpu_address','length'],
            'instruction_hints':sorted(entries.values()),'listing_file_count':len(source_files),
            'contains_game_bytes':False,'runtime_coverage':False,
            'note':'Classification hints from the credited reference, not complete semantic recovery. Validate the whole PRG hash and observed instruction overlap first.'}
    out.mkdir(parents=True,exist_ok=True)
    (out/'reference-map.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    symbols=reference/'castlevania3.sym'
    if symbols.exists():(out/'reference-symbols.sym').write_bytes(symbols.read_bytes())
    print(json.dumps({k:v for k,v in result.items() if k!='instruction_hints'}|{'instruction_hint_count':len(entries)},indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();extract(a.reference,a.out)
