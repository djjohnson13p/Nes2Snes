#!/usr/bin/env python3
"""Repeatable early-game speed sample for the experimental CV3 bridge.

Counts emulated SNES frames per guest NMI; host-machine wall time is not used as
console performance. This bounded route is not a full-game verification. Output
RAM/screenshots are input-derived and belong only in ignored build directories.
"""
from __future__ import annotations
import argparse
import bisect
import ctypes as C
import hashlib
import json
from pathlib import Path
from libretro_runner import Runner


def word(memory: bytes, address: int) -> int:
    return int.from_bytes(memory[address:address + 2], 'little')


def benchmark(core: Path, rom: Path, out: Path, sample_frames: int = 120, labels: Path | None = None) -> dict:
    if sample_frames <= 0:
        raise ValueError('sample_frames must be positive')
    out.mkdir(parents=True, exist_ok=True)
    r = Runner(core, rom)
    records = []
    profile = labels is not None
    symbols=[]
    if profile:
        for line in labels.read_text().splitlines():
            parts=line.split()
            if len(parts)==3 and parts[0]=='al' and not parts[2].startswith('.@'):
                symbols.append((int(parts[1],16)&0xffff,parts[2].lstrip('.')))
        symbols=sorted(set(symbols))
        if not symbols:raise ValueError('No ca65 symbols found')
        r.lib.retro_n2s_profile_reset.argtypes=[]
        r.lib.retro_n2s_profile_reset.restype=None
        r.lib.retro_n2s_profile_host.argtypes=[]
        r.lib.retro_n2s_profile_host.restype=C.POINTER(C.c_uint64)
        r.lib.retro_n2s_profile_guest.argtypes=[]
        r.lib.retro_n2s_profile_guest.restype=C.POINTER(C.c_uint64)
        r.lib.retro_n2s_profile_traps.argtypes=[]
        r.lib.retro_n2s_profile_traps.restype=C.POINTER(C.c_uint64)
    def profile_result():
        addresses=[a for a,_ in symbols]
        counts=r.lib.retro_n2s_profile_host()
        groups={}
        for pc in range(65536):
            if not counts[pc]:continue
            index=bisect.bisect_right(addresses,pc)-1
            name=symbols[index][1] if index>=0 else 'before_first_symbol'
            groups[name]=groups.get(name,0)+counts[pc]
        from opcodes6502 import OPS
        traps=r.lib.retro_n2s_profile_traps()
        return dict(traps={f'{i:02X} '+str(OPS.get(i)):traps[i] for i in range(256) if traps[i]},
                    host_instruction_count=sum(groups.values()),
                    guest_instruction_count=sum(r.lib.retro_n2s_profile_guest()[:256]),
                    top_host_routines=sorted(groups.items(),key=lambda kv:-kv[1])[:25],
                    caution='Instruction frequencies, not cycle or elapsed-time percentages.')
    def tick(buttons=()):
        r.run(1, buttons)
        m = r.memory()
        if len(m) < 0x964:
            raise RuntimeError('Native bridge WRAM diagnostics missing')
        if m[0x90f]:
            raise RuntimeError(f'Bridge fault {m[0x90f]} at '
                               f'${m[0x90e]:02X}:{word(m, 0x90c):04X}')
        return m
    def advance(count, buttons=(), label=None):
        m = r.memory()
        start_g = word(m, 0x906)
        start_h = r.frames
        start_cop = int.from_bytes(m[0x960:0x964], 'little')
        if profile and label:r.lib.retro_n2s_profile_reset()
        for _ in range(max(600, count * 40)):
            m = tick(buttons)
            delta = (word(m, 0x906) - start_g) & 0xffff
            if delta >= count:
                break
        else:
            raise RuntimeError(f'Guest stalled during {label or "startup"}')
        result = dict(label=label, guest_frames=delta, snes_frames=r.frames-start_h,
                      snes_frames_per_guest_frame=(r.frames-start_h)/delta,
                      cop_calls=(int.from_bytes(m[0x960:0x964], 'little')-start_cop)&0xffffffff,
                      game_state=m[0x18], guest_frame=word(m,0x906),
                      fault=m[0x90f])
        if label:
            if profile:result['profile']=profile_result()
            records.append(result)
            r.save_png(out / (label+'.png'))
            (out / (label+'.ram')).write_bytes(m)
            print(json.dumps(result), flush=True)
        return m
    try:
        # Establish first guest NMI, then pace input in guest-frame units.
        for _ in range(1000):
            m = tick()
            if word(m,0x906):
                break
        else:
            raise RuntimeError('Guest never enabled NMI')
        advance(120)
        for _ in range(10):
            if r.memory()[0x18] == 4:
                break
            advance(2, ('start',))
            advance(145)
        else:
            raise RuntimeError('Adaptive startup did not reach CV3 main state 4')
        advance(60, label='stage-idle')
        advance(sample_frames, ('right',), 'walk-right')
        advance(25, ('right','a'), 'jump-right')
        advance(25, ('b',), 'attack')
        advance(60, label='settle')
        result = dict(sfc_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                      core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                      records=records, total_snes_frames=r.frames,
                      definition='SNES video frames divided by guest NMI count; not wall time, full-game coverage or gameplay equivalence proof.')
        (out / 'benchmark.json').write_text(json.dumps(result, indent=2)+'\n')
        return result
    finally:
        r.close()

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--labels',type=Path,help='Use an optional instrumented Snes9x core and ca65 label file')
    p.add_argument('--sample-frames',type=int,default=120)
    a=p.parse_args()
    benchmark(a.core,a.rom,a.out,a.sample_frames,a.labels)
