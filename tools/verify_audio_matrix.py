#!/usr/bin/env python3
"""Build and run original four-voice, mute, fallback and nested-NMI fixtures."""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(core:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    def run(tool,*args):subprocess.run([sys.executable,str(ROOT/'tools'/tool),*map(str,args)],check=True)
    fixture=out/'input';run('audio_fixture.py','--out',fixture)
    cases=[('audio', ['--experimental-audio']),('silent',[]),
           ('legacy',['--experimental-audio','--no-direct-calls','--no-unrolled-objects']),
           ('nested-nmi',['--experimental-audio','--stress-nmi-restore'])]
    results=[]
    for name,flags in cases:
        build=out/name
        run('build_native.py','--rom',fixture/'fixture.nes','--trace',fixture,'--out',build,*flags)
        run('verify_audio.py','--core',core,'--rom',build/'native-prototype.sfc','--fixture',fixture,
            '--out',build/'verification',*(['--expect-silent'] if name=='silent' else []))
        results.append(dict(name=name,**json.loads((build/'verification/audio-verification.json').read_text())))
    result=dict(passed=True,cases=results,scope='Original procedural input only; not full NES APU fidelity.')
    (out/'matrix-verification.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--core',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(verify(a.core,a.out),indent=2))
