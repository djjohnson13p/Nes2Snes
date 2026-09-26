#!/usr/bin/env python3
"""Attribute emulator master clocks to dispatched PCs on a bounded fixed replay.

Counts include stalls serviced inside instructions. Interrupt-entry costs outside
opcode dispatch are separately reported as unattributed. This is diagnostic
attribution, not an independent gameplay correctness or physical-hardware test.
"""
from __future__ import annotations
import argparse
import bisect
import ctypes as C
import hashlib
import json
from pathlib import Path
from libretro_runner import Runner


def cop_callers(lib, elapsed: int) -> dict:
    """Completed COP spans only; a second overlapping view of the same clocks."""
    import numpy as np
    for name in ("retro_n2s_cop_costs", "retro_n2s_cop_calls"):
        f = getattr(lib, name)
        f.argtypes = [C.c_uint]
        f.restype = C.POINTER(C.c_uint64)
    lib.retro_n2s_cop_status.argtypes = [C.c_uint]
    lib.retro_n2s_cop_status.restype = C.c_uint64
    overlaps = int(lib.retro_n2s_cop_status(0))
    if overlaps:
        raise RuntimeError(f"Overlapping COP spans invalidate attribution: {overlaps}")
    entries = []
    for bank in range(32):
        costs = np.ctypeslib.as_array(lib.retro_n2s_cop_costs(bank), shape=(65536,))
        calls = np.ctypeslib.as_array(lib.retro_n2s_cop_calls(bank), shape=(65536,))
        for pc in np.flatnonzero(calls):
            clocks, count = int(costs[pc]), int(calls[pc])
            entries.append(dict(execution_bank=bank+0xA1, pc=int(pc), calls=count,
                                master_clocks=clocks, mean_master_clocks=clocks/count,
                                percent_of_elapsed=100*clocks/elapsed))
    total = sum(e["master_clocks"] for e in entries)
    if total > elapsed:
        raise RuntimeError("COP span accounting exceeds the measurement interval")
    return dict(scope="Completed COP-to-host-RTI spans, including dispatched nested interrupts and serviced DMA/refresh; excludes partial boundary spans, external interrupt-entry cycles and direct-call veneers. Overlaps the flat PC view: do not sum both.",
                overlapping_starts=overlaps, incomplete_span_at_end=bool(lib.retro_n2s_cop_status(1)),
                incomplete_span_clocks=int(lib.retro_n2s_cop_status(2)),
                completed_calls=sum(e["calls"] for e in entries),
                completed_master_clocks=total, percent_of_elapsed=100*total/elapsed,
                entries=sorted(entries, key=lambda e: (-e["master_clocks"], e["execution_bank"], e["pc"])))


def labels(path: Path) -> list[tuple[int,str]]:
    result=[]
    for line in path.read_text().splitlines():
        f=line.split()
        if len(f)==3 and f[0]=='al' and not f[2].startswith(('.@','.__')):
            result.append((int(f[1],16),f[2].lstrip('.')))
    return sorted(set(result))


def profile(core: Path, rom: Path, symbols: Path, start: int, end: int, out: Path) -> dict:
    if not 0 < start < end < 65536:
        raise ValueError('Require 0 < start < end < 65536')
    r=Runner(core,rom)
    syms=labels(symbols);addresses=[s[0] for s in syms]
    try:
        lib=r.lib
        lib.retro_n2s_cost_reset.argtypes=[];lib.retro_n2s_cost_reset.restype=None
        lib.retro_n2s_cost_elapsed.argtypes=[];lib.retro_n2s_cost_elapsed.restype=C.c_uint64
        for name in ('retro_n2s_cost_data','retro_n2s_cost_instructions'):
            f=getattr(lib,name);f.argtypes=[C.c_uint];f.restype=C.POINTER(C.c_uint64)
        started=False
        for _ in range(30000):
            r.run(1);m=r.memory();g=int.from_bytes(m[0x906:0x908],'little')
            if m[0x90f]:raise RuntimeError('Bridge fault '+m[0x90c:0x910].hex())
            if not started and g>=start:
                lib.retro_n2s_cost_reset();first_host=r.frames;first_game=g;started=True
            if started and g>=end:break
        else:raise RuntimeError('Profile interval not reached')
        total=int(lib.retro_n2s_cost_elapsed());attributed=0;regions=[];hot=[];attribution=[]
        for kind,name in enumerate(('host_runtime','native_guest','wram_veneers')):
            clocks=lib.retro_n2s_cost_data(kind);counts=lib.retro_n2s_cost_instructions(kind)
            amounts={}
            for pc in range(65536):
                c=int(clocks[pc]);n=int(counts[pc])
                if not n:continue
                if kind==0:
                    j=bisect.bisect_right(addresses,pc)-1
                    label=syms[j][1] if j>=0 else 'unlabelled'
                else:label=f'${pc:04X}'
                v=amounts.setdefault(label,[0,0]);v[0]+=c;v[1]+=n
            used=sum(v[0] for v in amounts.values());attributed+=used
            regions.append(dict(region=name,master_clocks=used,percent_of_elapsed=100*used/total))
            attribution.extend(dict(region=name,label=k,master_clocks=v[0],instructions=v[1]) for k,v in sorted(amounts.items()))
            top=sorted(amounts.items(),key=lambda p:p[1][0],reverse=True)[:25]
            hot.append(dict(region=name,entries=[dict(label=k,master_clocks=v[0],instructions=v[1],percent_of_elapsed=100*v[0]/total) for k,v in top]))
        if attributed>total:raise RuntimeError('Clock accounting exceeded elapsed time')
        result=dict(scope=__doc__,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                    diagnostic_core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                    start_game=first_game,end_game=g,host_frames=r.frames-first_host,
                    elapsed_master_clocks=total,attributed_master_clocks=attributed,
                    unattributed_master_clocks=total-attributed,regions=regions,hot=hot,attribution=attribution,
                    boundary='After retro_run at the requested guest counter, not video-callback presentation.',
                    symbols_sha256=hashlib.sha256(symbols.read_bytes()).hexdigest(),
                    cop_callers=cop_callers(lib,total))
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('core','rom','symbols','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--start',type=int,default=916);p.add_argument('--end',type=int,default=1036)
    a=p.parse_args();result=profile(a.core,a.rom,a.symbols,a.start,a.end,a.out)
    print(json.dumps(result,indent=2))
