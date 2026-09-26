#!/usr/bin/env python3
"""Reproducible original-input event, envelope and fallback regression matrix."""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(nes_core:Path,snes_core:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    def run(name,*args):
        subprocess.run([sys.executable,str(ROOT/'tools'/name),*map(str,args)],check=True)
    lengths=[];envelopes=[]
    for name,fixture_flags,build_flags in [('direct',[],[]),('generic',[],['--no-direct-calls','--no-quick-io']),('c0',['--force-c0'],[])]:
        folder=out/('length-'+name)
        run('apu_counter_fixture.py','--out',folder,*fixture_flags)
        run('build_native.py','--rom',folder/'fixture.nes','--trace',folder,'--out',folder/'snes','--experimental-audio','--audio-counters',*build_flags)
        run('verify_native_cpu.py','--nes-core',nes_core,'--snes-core',snes_core,'--fixture',folder,'--out',folder/'verification')
        lengths.append(dict(case=name,**json.loads((folder/'verification/cpu-verification.json').read_text())))
    fixture=out/'envelope-input';run('apu_envelope_fixture.py','--out',fixture)
    for name,flags in [('direct',[]),('generic',['--no-direct-calls','--no-quick-io']),('nested-nmi',['--stress-nmi-restore'])]:
        folder=out/('envelope-'+name)
        run('build_native.py','--rom',fixture/'fixture.nes','--trace',fixture,'--out',folder,'--experimental-audio','--audio-counters',*flags)
        run('verify_apu_envelopes.py','--core',snes_core,'--rom',folder/'native-prototype.sfc','--fixture',fixture,'--out',folder/'verification')
        envelopes.append(dict(case=name,**json.loads((folder/'verification/envelope-verification.json').read_text())))
    result=dict(passed=True,length_oracle=lengths,envelope_contract=envelopes,
                scope='Original data. Independent NES length/status oracle and quantized envelope contract. Not complete APU fidelity.')
    (out/'apu-matrix.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('nes-core','snes-core','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(verify(a.nes_core,a.snes_core,a.out),indent=2))
