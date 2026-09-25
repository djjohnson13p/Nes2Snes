"""Conservative direct-control-flow expansion of an observed MMC5 code map.

Inferred instructions are NOT runtime observations. Indirect targets and unknown
bank mappings remain unresolved. Inline dispatch-table calls are treated as
non-returning when the base trace has never executed their return site.
"""
from collections import deque
from opcodes6502 import OPS

def expand(prg:bytes,counts:list[int],pcs:list[int]):
    starts={i for i,c in enumerate(counts) if c}
    owner=[-1]*len(prg)
    for i in sorted(starts):
        if prg[i] not in OPS:raise ValueError(f'Unsupported observed opcode {i:x}')
        n=OPS[prg[i]][2]
        for j in range(i,i+n):
            if j>=len(prg) or owner[j]!=-1:raise ValueError('Overlapping observed instructions')
            owner[j]=i
    noreturn={int.from_bytes(prg[i+1:i+3],'little') for i in starts
              if prg[i]==0x20 and i+3<len(prg) and not counts[i+3]}
    pending=deque((i,pcs[i]) for i in sorted(starts))
    processed=set();inferred=[];unresolved=[]
    def physical(i,pc,target):
        if target>=0xE000:return 0x3E000+target-0xE000
        if 0x8000<=pc<0xC000 and 0x8000<=target<0xC000:
            return (i//0x4000)*0x4000+target-0x8000
        if 0xC000<=pc<0xE000 and 0xC000<=target<0xE000:
            return (i//0x2000)*0x2000+target-0xC000
        return None
    def queue(i,pc,target):
        dest=physical(i,pc,target)
        if dest is None:
            unresolved.append((i,target));return
        if 0<=dest<len(prg):pending.append((dest,target))
    while pending:
        i,pc=pending.popleft()
        if i in processed:continue
        processed.add(i)
        op=OPS.get(prg[i])
        if not op or op[0] in ('BRK','SED'):continue
        name,mode,n=op
        if i+n>len(prg):continue
        if i not in starts:
            if any(owner[j]>=0 for j in range(i,i+n)):continue
            for j in range(i,i+n):owner[j]=i
            starts.add(i);inferred.append(i);pcs[i]=pc
        if name in ('RTS','RTI'):continue
        target=int.from_bytes(prg[i+1:i+n],'little')
        if mode=='rel':
            queue(i,pc,(pc+2+(target if target<128 else target-256))&65535)
        if name in ('JMP','JSR') and mode=='abs':queue(i,pc,target)
        if name=='JMP' or (name=='JSR' and target in noreturn):continue
        queue(i,pc,(pc+n)&65535)
    result=counts[:]
    for i in inferred:result[i]=-1
    return result,{'statically_inferred_instruction_sites':len(inferred),
                   'inferred_offsets':inferred,'unresolved_direct_edges':len(set(unresolved)),
                   'nonreturning_call_targets':sorted(noreturn)}
