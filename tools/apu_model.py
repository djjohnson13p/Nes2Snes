"""Reference for the explicit, frame-quantized audio-counter contract.

Not an NES emulator. CPU-cycle timing, IRQ, sweep, DMC and noise waveform are
outside this model. Register writes are events, including identical values.
"""
from dataclasses import dataclass,field
LENGTHS=(10,254,20,2,40,4,80,6,160,8,60,10,14,12,26,14,
         12,16,24,18,48,20,96,22,192,24,72,26,16,28,32,30)
@dataclass
class Counters:
    regs:list[int]=field(default_factory=lambda:[0]*24)
    lengths:list[int]=field(default_factory=lambda:[0]*4)
    decay:list[int]=field(default_factory=lambda:[0]*4)
    divider:list[int]=field(default_factory=lambda:[0]*4)
    restart:list[int]=field(default_factory=lambda:[0]*4)
    linear:int=0
    reload:int=0
    phase:int=0
    quarters:int=0
    halves:int=0
    frames:int=0
    writes:int=0
    def write(self,address:int,value:int)->None:
        if not (0x4000<=address<=0x4017 and address not in (0x4014,0x4016)) or not 0<=value<=255:
            raise ValueError('Not an audio register byte')
        index=address-0x4000;self.regs[index]=value;self.writes+=1
        if index==0x15:
            self.lengths=[length if value&(1<<c) else 0 for c,length in enumerate(self.lengths)]
        elif index==0x17:
            self.phase=0
            if value&128:self.half();self.quarter()
        elif index<16 and index%4==3:
            channel=index//4
            if channel==2:self.reload=1
            else:self.restart[channel]=1
            if self.regs[0x15]&(1<<channel):self.lengths[channel]=LENGTHS[value>>3]
    def quarter(self)->None:
        self.quarters+=1
        for c in (0,1,3):
            period=self.regs[c*4]&15
            if self.restart[c]:
                self.restart[c]=0;self.decay[c]=15;self.divider[c]=period
            elif self.divider[c]:self.divider[c]-=1
            else:
                self.divider[c]=period
                if self.decay[c]:self.decay[c]-=1
                elif self.regs[c*4]&32:self.decay[c]=15
        self.linear=(self.regs[8]&127) if self.reload else max(0,self.linear-1)
        if not self.regs[8]&128:self.reload=0
    def half(self)->None:
        self.halves+=1
        for c in range(4):
            if self.lengths[c] and not self.regs[c*4]&(128 if c==2 else 32):self.lengths[c]-=1
    def frame(self)->None:
        for _ in range(4):
            five=bool(self.regs[23]&128)
            if self.phase in ((1,4) if five else (1,3)):self.half()
            if not five or self.phase!=3:self.quarter()
            self.phase=(self.phase+1)%(5 if five else 4)
        self.frames+=1
    def volume(self,c:int)->int:
        if c not in (0,1,2,3):raise ValueError('Invalid voice')
        if not self.lengths[c] or not self.regs[21]&(1<<c):return 0
        if c==2:return 66 if self.linear else 0
        raw=(self.regs[c*4]&15) if self.regs[c*4]&16 else self.decay[c]
        return raw*(4 if c==3 else 6)
