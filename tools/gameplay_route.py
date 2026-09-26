#!/usr/bin/env python3
"""Bounded CV3 gameplay route and optional evidence-only NES trace extension.

This visits early rooms; reaching the frame budget does not prove level
completion or correctness. Generated images, states and traces are game-derived:
keep them private in ignored build directories. The original ROM is read-only.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
from pathlib import Path
from libretro_runner import Runner
from rom import Rom

PATTERN=((40,('right',)),(25,('right','a')),(25,('right','b')),(10,()))


def validate_actions(value:object)->list[dict]:
    """Validate an optional bounded tail of named, per-logical-frame inputs.

    Names become output basenames; path separators and duplicate names are
    forbidden. Only ordinary NES controls are accepted, not emulator turbo.
    """
    if not isinstance(value,list) or not 1<=len(value)<=512:
        raise ValueError('Action script must contain 1..512 actions')
    result=[];names=set();total=0
    allowed={'a','b','start','select','left','right','up','down'}
    for action in value:
        if not isinstance(action,dict) or set(action)!={'name','updates','buttons'}:
            raise ValueError('Each action requires exactly name, updates and buttons')
        name=action['name'];n=action['updates'];buttons=action['buttons']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name) or name in names:
            raise ValueError('Action names must be unique safe basenames of at most 64 characters')
        if type(n) is not int or not 1<=n<=600:
            raise ValueError('Each action requires 1..600 logical updates')
        if not isinstance(buttons,list) or any(not isinstance(b,str) or b not in allowed for b in buttons):
            raise ValueError('Unknown button in action script')
        if len(buttons)!=len(set(buttons)) or ({'left','right'}<=set(buttons)) or ({'up','down'}<=set(buttons)):
            raise ValueError('Duplicate or contradictory buttons in action script')
        total+=n
        if total>100000:raise ValueError('Action script exceeds 100000 logical updates')
        names.add(name);result.append(dict(name=name,updates=n,buttons=list(buttons)))
    return result


def merge_trace(base:Path,out:Path,rom:Rom,counts:bytes,pcs:bytes,palette:bytes,route:dict)->dict:
    meta=json.loads((base/'trace-summary.json').read_text())
    if meta['rom_sha256']!=rom.metadata()['sha256']:
        raise ValueError('Base trace belongs to another ROM')
    n=len(rom.prg)
    old=(base/'counts.u32').read_bytes();oldpc=(base/'cpu-address.u16').read_bytes()
    if len(counts)!=n*4 or len(pcs)!=n*2 or len(old)!=n*4 or len(oldpc)!=n*2 or len(palette)!=192:
        raise ValueError('Probe or base trace has an unexpected size')
    a=struct.unpack(f'<{n}I',old);b=struct.unpack(f'<{n}I',counts)
    x=struct.unpack(f'<{n}H',oldpc);y=struct.unpack(f'<{n}H',pcs)
    if any(i and j and i!=j for i,j in zip(x,y)):
        raise ValueError('A physical instruction ran at multiple CPU slots; mapping analysis required')
    merged=[min(0xffffffff,i+j) for i,j in zip(a,b)]
    out.mkdir(parents=True,exist_ok=True)
    (out/'counts.u32').write_bytes(struct.pack(f'<{n}I',*merged))
    (out/'cpu-address.u16').write_bytes(struct.pack(f'<{n}H',*[i or j for i,j in zip(x,y)]))
    (out/'rgb-palette.bin').write_bytes(palette)
    extension=dict(route=route,new_observed_sites=sum(j>0 and i==0 for i,j in zip(a,b)),
                   observed_sites=sum(i>0 for i in merged),coverage_complete=False)
    meta['route_extensions']=meta.get('route_extensions',[])+[extension]
    meta['observed_instruction_entry_points']=extension['observed_sites']
    meta['observed_instruction_executions']=sum(merged)
    meta['coverage_is_complete']=False
    meta['io_summary_scope']='Retained base-pass I/O summary; only execution arrays were extended'
    (out/'trace-summary.json').write_text(json.dumps(meta,indent=2)+'\n')
    return extension


def run(core:Path,rom_path:Path,out:Path,platform:str,steps:int=100,base_trace:Path|None=None,actions:list[dict]|None=None)->dict:
    if platform not in ('nes','snes') or not 1<=steps<=1000:
        raise ValueError('Require nes/snes and 1..1000 route steps')
    actions=validate_actions(actions) if actions is not None else []
    if base_trace and platform!='nes':
        raise ValueError('Only the instrumented NES oracle supplies new code observations')
    out.mkdir(parents=True,exist_ok=True)
    r=Runner(core,rom_path);records=[];tail_records=[];current_action='startup'
    input_segments=[];emulator_calls=0
    def host_run(count:int,buttons:tuple[str,...]=())->None:
        nonlocal emulator_calls
        r.run(count,buttons);emulator_calls+=count
        b=list(buttons)
        if input_segments and input_segments[-1]['buttons']==b:
            input_segments[-1]['frames']+=count
        else:input_segments.append(dict(frames=count,buttons=b))
    report=dict(platform=platform,rom_sha256=hashlib.sha256(rom_path.read_bytes()).hexdigest(),
                core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),steps_requested=steps,
                pattern=[dict(updates=n,buttons=list(b)) for n,b in PATTERN],
                tail_actions=actions,
                scope='Bounded live-controller early-game route; not all-level or NES/SNES equivalence proof')
    try:
        if platform=='nes':
            nes=Rom.read(rom_path)
            if nes.mapper!=5 or len(nes.prg)!=0x40000:
                raise ValueError('This route currently targets the supplied MMC5 CV3 layout')
            nmi=int.from_bytes(nes.prg[-6:-4],'little')
            if not 0xe000<=nmi<=0xffff:raise ValueError('NMI must be in the fixed PRG bank')
            r.lib.retro_n2s_size.argtypes=[C.c_uint];r.lib.retro_n2s_size.restype=C.c_size_t
            r.lib.retro_n2s_data.argtypes=[C.c_uint];r.lib.retro_n2s_data.restype=C.c_void_p
            host_run(1)
            pointer=C.cast(r.lib.retro_n2s_data(0),C.POINTER(C.c_uint32))
            if r.lib.retro_n2s_size(0)!=0x100000 or not pointer:raise RuntimeError('NES probe unavailable')
            clock=lambda: int(pointer[0x3e000+nmi-0xe000])
        else:
            clock=lambda: int.from_bytes(r.memory()[0x906:0x908],'little')
        def advance(count:int,buttons:tuple[str,...]=())->None:
            initial=clock()
            for _ in range(max(600,count*50)):
                host_run(1,buttons);m=r.memory()
                if platform=='snes' and m[0x90f]:
                    report['fault']=dict(code=m[0x90f],bank=m[0x90e],pc=int.from_bytes(m[0x90c:0x90e],'little'))
                    raise RuntimeError('Native bridge rejected an unsupported execution path')
                if (clock()-initial)&0xffff>=count:return
            raise RuntimeError('Logical clock stopped progressing')
        # Match the previously documented per-platform live startup adapters.
        if platform=='nes':
            host_run(120)
        else:
            for _ in range(1000):
                host_run(1)
                if clock():break
            else:raise RuntimeError('Native guest did not enable NMI')
            advance(120)
        for _ in range(10):
            if r.memory()[0x18]==4:break
            advance(2,('start',));advance(145)
        else:raise RuntimeError('Did not reach the main-game state')
        report['start_logical_frame']=clock()
        for step in range(steps):
            for count,buttons in PATTERN:
                current_action=f'step {step}: {buttons}'
                advance(count,buttons)
            records.append(dict(step=step,emulator_frames=r.frames,emulator_calls=emulator_calls,logical_frame=clock(),game_state=r.memory()[0x18]))
            if step%10==0 or step==steps-1:
                r.save_png(out/f'step-{step:03d}.png')
                (out/f'step-{step:03d}.state').write_bytes(r.state())
                print(json.dumps(records[-1]),flush=True)
        for i,action in enumerate(actions):
            current_action='tail '+action['name']
            advance(action['updates'],tuple(action['buttons']))
            memory=r.memory();stem='tail-'+action['name']
            r.save_png(out/(stem+'.png'))
            (out/(stem+'.state')).write_bytes(r.state())
            (out/(stem+'.ram')).write_bytes(memory)
            tail_records.append(dict(index=i,name=action['name'],emulator_frames=r.frames,emulator_calls=emulator_calls,
                                     logical_frame=clock(),game_state=memory[0x18],
                                     candidate_player_x=memory[0x438],candidate_player_y=memory[0x41c]))
            print(json.dumps(tail_records[-1]),flush=True)
        report['status']='completed_budget'
    except Exception as exc:
        report.update(status='failed',error=str(exc),action=current_action)
        if r.frame:r.save_png(out/'failure.png')
        (out/'failure.ram').write_bytes(r.memory())
    finally:
        report.update(records=records,tail_records=tail_records,input_segments=input_segments,total_emulator_calls=emulator_calls,total_emulator_frames=r.frames)
        if base_trace and report.get('status')=='completed_budget':
            arrays={kind:C.string_at(r.lib.retro_n2s_data(kind),r.lib.retro_n2s_size(kind)) for kind in (0,1,14)}
            report['trace_extension']=merge_trace(base_trace,out/'trace',nes,arrays[0],arrays[1],arrays[14],dict(steps=steps,pattern=report['pattern'],actions=actions,total_emulator_frames=r.frames))
        (out/'route-report.json').write_text(json.dumps(report,indent=2)+'\n')
        r.close()
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('core','rom','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--platform',choices=['nes','snes'],required=True)
    p.add_argument('--steps',type=int,default=100)
    p.add_argument('--base-trace',type=Path)
    p.add_argument('--actions',type=Path,help='JSON array of named bounded actions after the repeated route')
    a=p.parse_args();actions=json.loads(a.actions.read_text()) if a.actions else None
    result=run(a.core,a.rom,a.out,a.platform,a.steps,a.base_trace,actions)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
    raise SystemExit(result['status']!='completed_budget')
