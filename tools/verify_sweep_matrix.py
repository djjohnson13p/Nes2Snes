#!/usr/bin/env python3
"""Complete original-input sweep matrix; each emulator run is a fresh process."""
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def verify(nes_core:Path,snes_core:Path,out:Path,skip_oracle:bool=False)->dict:
    out.mkdir(parents=True,exist_ok=True)
    def run(name,*args):
        subprocess.run([sys.executable,str(ROOT/'tools'/name),*map(str,args)],check=True)
    rows=[]
    run('apu_sweep_fixture.py','--out',out/'input')
    for name,flags in [('direct',[]),('generic',['--no-direct-calls','--no-quick-io']),('nested-nmi',['--stress-nmi-restore'])]:
        folder=out/name
        run('build_native.py','--rom',out/'input/fixture.nes','--trace',out/'input','--out',folder,
            '--experimental-audio','--audio-counters','--audio-sweep',*flags)
        run('verify_apu_sweep.py','--core',snes_core,'--rom',folder/'native-prototype.sfc',
            '--fixture',out/'input','--out',folder/'verification')
        rows.append(dict(mode=name,**json.loads((folder/'verification/sweep-verification.json').read_text())))
    lengths=[]
    for name,fixture_flags,flags in [('direct',[],[]),('generic',[],['--no-direct-calls','--no-quick-io']),('c0',['--force-c0'],[])]:
        folder=out/('length-'+name)
        run('apu_counter_fixture.py','--out',folder,*fixture_flags)
        run('build_native.py','--rom',folder/'fixture.nes','--trace',folder,'--out',folder/'snes',
            '--experimental-audio','--audio-counters','--audio-sweep',*flags)
        run('verify_native_cpu.py','--nes-core',nes_core,'--snes-core',snes_core,'--fixture',folder,'--out',folder/'verification')
        lengths.append(dict(mode=name,**json.loads((folder/'verification/cpu-verification.json').read_text())))
    oracle=None
    if not skip_oracle:
        run('verify_sweep_oracle.py','--nes-core',nes_core,'--snes-core',snes_core,'--out',out/'oracle')
        oracle=json.loads((out/'oracle/sweep-oracle.json').read_text())
    report=dict(passed=True,quantized_sweep=rows,length_and_store_regressions=lengths,independent_period_oracle=oracle,
                scope='Sweep event semantics and bounded audio output; not exact APU timing or whole-game fidelity.')
    (out/'sweep-matrix.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('nes-core','snes-core','out'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--skip-oracle',action='store_true',help='Local split run only; default matrix includes independent oracle')
    a=p.parse_args();print(json.dumps(verify(a.nes_core,a.snes_core,a.out,a.skip_oracle),indent=2))
