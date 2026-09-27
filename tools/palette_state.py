"""Read unmodified pinned Nestopia's serialized palette/PPU state.

REG layouts follow NstCpu.cpp and NstPpu.cpp at 8f00f500. This only decodes
recorded state; it does not execute or correct emulator behavior.
"""
import zlib
from oam_state import _chunks


def unpack(data: bytes, size: int) -> bytes:
    if not isinstance(data,bytes) or not data:raise ValueError('Missing NST memory chunk')
    if data[0]==0:
        result=data[1:]
    elif data[0]==1:
        d=zlib.decompressobj()
        try:result=d.decompress(data[1:],size+1)
        except zlib.error as exc:raise ValueError('Invalid NST compression') from exc
        if not d.eof or d.unconsumed_tail or d.unused_data:raise ValueError('Incomplete or overlong NST memory')
    else:raise ValueError('Unknown NST compression')
    if len(result)!=size:raise ValueError('Incorrect NST memory length')
    return result


def decode(data: bytes) -> dict:
    if not isinstance(data,bytes) or not 8<=len(data)<=8*1024*1024 or data[:4]!=b'NST\x1a':
        raise ValueError('Require a bounded NST state')
    end=8+int.from_bytes(data[4:8],'little')
    if end>len(data) or len(data)-end not in (0,8,12):raise ValueError('Invalid NST root/footer')
    root=_chunks(data[8:end]);ppu=_chunks(root.get(b'PPU\0',b''));cpu=_chunks(root.get(b'CPU\0',b''))
    reg=ppu.get(b'REG\0',b'');cr=cpu.get(b'REG\0',b'')
    if len(reg)!=11 or len(cr)!=7:raise ValueError('Missing or incorrect register chunks')
    if reg[0]&0xE0 or reg[1]&0x18:raise ValueError('Rendering/NMI/sprite mode outside blanked profile')
    if reg[4]&0x80 or reg[6]&0x80 or reg[7]&0xF0:
        raise ValueError('Invalid serialized PPU address or write-phase bits')
    # Status vblank and OAM are outside this profile; no CPU output masking.
    state=bytes((reg[0],reg[1],(reg[7]>>3)&1,reg[7]&7,reg[5],reg[6],
                 reg[3],reg[4],reg[9],reg[10]))
    palette=unpack(ppu.get(b'PAL\0',b''),32)
    # Nestopia retains the written byte in palette.ram, and applies COLOR=$3F
    # when using it. Decode physical six-bit storage, retaining raw bytes too.
    if any(palette[i]!=palette[i+16] for i in (0,4,8,12)):raise ValueError('Palette alias state inconsistent')
    return dict(cpu_ram=unpack(cpu.get(b'RAM\0',b''),2048).hex(),
                cpu_registers=bytes((cr[0],cr[1],cr[3],cr[4],cr[5],cr[6]|0x30,cr[2])).hex(),
                ppu_state=state.hex(),palette_storage=palette.hex(),
                palette=bytes(v&63 for v in palette).hex(),ciram=unpack(ppu.get(b'NMT\0',b''),2048).hex())
