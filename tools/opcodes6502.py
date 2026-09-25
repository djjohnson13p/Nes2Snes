"""Documented NMOS 6502 instruction metadata (no unofficial-opcode assumptions)."""
SPEC = '''
00 BRK imp 01 ORA ix 05 ORA zp 06 ASL zp 08 PHP imp 09 ORA imm 0A ASL acc 0D ORA abs 0E ASL abs
10 BPL rel 11 ORA iy 15 ORA zpx 16 ASL zpx 18 CLC imp 19 ORA absy 1D ORA absx 1E ASL absx
20 JSR abs 21 AND ix 24 BIT zp 25 AND zp 26 ROL zp 28 PLP imp 29 AND imm 2A ROL acc 2C BIT abs 2D AND abs 2E ROL abs
30 BMI rel 31 AND iy 35 AND zpx 36 ROL zpx 38 SEC imp 39 AND absy 3D AND absx 3E ROL absx
40 RTI imp 41 EOR ix 45 EOR zp 46 LSR zp 48 PHA imp 49 EOR imm 4A LSR acc 4C JMP abs 4D EOR abs 4E LSR abs
50 BVC rel 51 EOR iy 55 EOR zpx 56 LSR zpx 58 CLI imp 59 EOR absy 5D EOR absx 5E LSR absx
60 RTS imp 61 ADC ix 65 ADC zp 66 ROR zp 68 PLA imp 69 ADC imm 6A ROR acc 6C JMP ind 6D ADC abs 6E ROR abs
70 BVS rel 71 ADC iy 75 ADC zpx 76 ROR zpx 78 SEI imp 79 ADC absy 7D ADC absx 7E ROR absx
81 STA ix 84 STY zp 85 STA zp 86 STX zp 88 DEY imp 8A TXA imp 8C STY abs 8D STA abs 8E STX abs
90 BCC rel 91 STA iy 94 STY zpx 95 STA zpx 96 STX zpy 98 TYA imp 99 STA absy 9A TXS imp 9D STA absx
A0 LDY imm A1 LDA ix A2 LDX imm A4 LDY zp A5 LDA zp A6 LDX zp A8 TAY imp A9 LDA imm AA TAX imp AC LDY abs AD LDA abs AE LDX abs
B0 BCS rel B1 LDA iy B4 LDY zpx B5 LDA zpx B6 LDX zpy B8 CLV imp B9 LDA absy BA TSX imp BC LDY absx BD LDA absx BE LDX absy
C0 CPY imm C1 CMP ix C4 CPY zp C5 CMP zp C6 DEC zp C8 INY imp C9 CMP imm CA DEX imp CC CPY abs CD CMP abs CE DEC abs
D0 BNE rel D1 CMP iy D5 CMP zpx D6 DEC zpx D8 CLD imp D9 CMP absy DD CMP absx DE DEC absx
E0 CPX imm E1 SBC ix E4 CPX zp E5 SBC zp E6 INC zp E8 INX imp E9 SBC imm EA NOP imp EC CPX abs ED SBC abs EE INC abs
F0 BEQ rel F1 SBC iy F5 SBC zpx F6 INC zpx F8 SED imp F9 SBC absy FD SBC absx FE INC absx
'''.split()
LENGTHS={'imp':1,'acc':1,'imm':2,'zp':2,'zpx':2,'zpy':2,'ix':2,'iy':2,'rel':2,
         'abs':3,'absx':3,'absy':3,'ind':3}
OPS={int(SPEC[i],16):(SPEC[i+1],SPEC[i+2],LENGTHS[SPEC[i+2]]) for i in range(0,len(SPEC),3)}
assert len(OPS)==151

REGISTERS={0x2000:'PPUCTRL',0x2001:'PPUMASK',0x2002:'PPUSTATUS',0x2003:'OAMADDR',
           0x2004:'OAMDATA',0x2005:'PPUSCROLL',0x2006:'PPUADDR',0x2007:'PPUDATA',
           0x4014:'OAMDMA',0x4015:'APUSTATUS',0x4016:'JOY1',0x4017:'JOY2_APUFRAME',
           0x5010:'MMC5_PCM_CONTROL',0x5100:'MMC5_PRG_MODE',0x5101:'MMC5_CHR_MODE',
           0x5104:'MMC5_EXRAM_MODE',0x5105:'MMC5_NAMETABLE',0x5106:'MMC5_FILL_TILE',
           0x5107:'MMC5_FILL_ATTR',0x5115:'MMC5_PRG_8000',0x5116:'MMC5_PRG_C000',
           0x5117:'MMC5_PRG_E000',0x5200:'MMC5_SPLIT',0x5203:'MMC5_IRQ_LINE',
           0x5204:'MMC5_IRQ_STATUS',0x5205:'MMC5_MULTIPLY_LOW',0x5206:'MMC5_MULTIPLY_HIGH'}
REGISTERS.update({0x5120+i:f'MMC5_CHR_A{i}' for i in range(8)})
REGISTERS.update({0x5128+i:f'MMC5_CHR_B{i}' for i in range(4)})


def format_instruction(data:bytes, pc:int) -> str:
    op=OPS.get(data[0]) if data else None
    if not op:return '.byte '+','.join(f'${b:02X}' for b in data[:1])
    name,mode,size=op
    if len(data)<size:raise ValueError('Truncated instruction.')
    n=int.from_bytes(data[1:size],'little')
    absolute=REGISTERS.get(n,f'${n:04X}')
    if mode=='imp':arg=''
    elif mode=='acc':arg='a'
    elif mode=='imm':arg=f'#${n:02X}'
    elif mode=='rel':arg=f'${(pc+2+(n if n<128 else n-256))&65535:04X}'
    elif mode=='ix':arg=f'(${n:02X},x)'
    elif mode=='iy':arg=f'(${n:02X}),y'
    elif mode=='ind':arg=f'({absolute})'
    elif mode.startswith('zp'):arg=f'${n:02X}'+(','+mode[-1] if len(mode)>2 else '')
    else:arg=absolute+(','+mode[-1] if len(mode)>3 else '')
    return name.lower()+(' '+arg if arg else '')
