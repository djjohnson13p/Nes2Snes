"""Checked Python interface for the read-only native idle observer.

Tick counts are instruction *visits*, not elapsed cycles or a speed estimate.
Do not load a save state, reset the core, or change games during measurement.
"""
from __future__ import annotations
import ctypes as C


class Record(C.Structure):
    _fields_ = [('ticks', C.c_uint64), ('host_frame', C.c_uint64),
                ('sample', C.c_uint64), ('pc', C.c_uint16), ('bank', C.c_uint16),
                ('values', C.c_uint8 * 16), ('reserved', C.c_uint8 * 4)]


def validate_config(tick_pc, sample_pc, addresses, capacity):
    for pc in (tick_pc, sample_pc):
        if type(pc) is not int or not 0x8000 <= pc <= 0xffff:
            raise ValueError('Require cartridge instruction addresses')
    if tick_pc == sample_pc:
        raise ValueError('Tick and sample instruction must differ')
    if not isinstance(addresses, (list, tuple)) or not 1 <= len(addresses) <= 16 or any(
            type(a) is not int or not 0 <= a < 2048 for a in addresses):
        raise ValueError('Require 1..16 common-RAM byte addresses')
    if len(set(addresses)) != len(addresses):
        raise ValueError('Duplicate observer RAM address')
    if type(capacity) is not int or not 1 <= capacity <= 32768:
        raise ValueError('Capacity must be 1..32768')


class Observer:
    def __init__(self, library, tick_pc: int, sample_pc: int,
                 addresses: tuple[int, ...], capacity: int = 32768):
        validate_config(tick_pc, sample_pc, addresses, capacity)
        self.lib, self.addresses = library, tuple(addresses)
        self.tick_pc, self.sample_pc, self.frame = tick_pc, sample_pc, 0
        self.lib.retro_n2s_idle_configure.argtypes = [C.c_uint32, C.c_uint32,
                                                    C.POINTER(C.c_uint16), C.c_uint32, C.c_uint32]
        self.lib.retro_n2s_idle_configure.restype = C.c_int
        self.lib.retro_n2s_idle_status.argtypes = [C.c_uint]
        self.lib.retro_n2s_idle_status.restype = C.c_uint64
        self.lib.retro_n2s_idle_frame.argtypes = [C.c_uint64]
        self.lib.retro_n2s_idle_frame.restype = None
        self.lib.retro_n2s_idle_data.argtypes = []
        self.lib.retro_n2s_idle_data.restype = C.POINTER(Record)
        self.lib.retro_n2s_idle_disable.argtypes = []
        self.lib.retro_n2s_idle_disable.restype = None
        if C.sizeof(Record) != 48 or self.lib.retro_n2s_idle_status(4) != 48:
            raise RuntimeError('Observer record ABI mismatch')
        data = (C.c_uint16 * len(addresses))(*addresses)
        if not self.lib.retro_n2s_idle_configure(tick_pc, sample_pc, data, len(data), capacity):
            raise RuntimeError('Observer configuration failed')

    def before_frame(self, frame: int) -> None:
        if type(frame) is not int or not self.frame < frame <= 2000000:
            raise ValueError('Require strictly increasing bounded host frames')
        self.frame = frame
        self.lib.retro_n2s_idle_frame(frame)

    def finish(self) -> dict:
        self.lib.retro_n2s_idle_disable()
        count, samples, ticks, overflow = [int(self.lib.retro_n2s_idle_status(i)) for i in range(4)]
        if overflow or count != samples:
            raise RuntimeError('Observer overflow: incomplete evidence is not accepted')
        if not count:
            raise RuntimeError('Observer recorded no matching sample instruction')
        data = self.lib.retro_n2s_idle_data()
        if not data:
            raise RuntimeError('Observer records are unavailable')
        rows, previous_ticks, previous_frame = [], 0, 0
        for i in range(count):
            row = data[i]
            if row.sample != i+1 or row.pc != self.sample_pc or row.ticks < previous_ticks or not previous_frame <= row.host_frame <= self.frame:
                raise RuntimeError('Invalid observer event ordering')
            rows.append(dict(sample=int(row.sample), pc=int(row.pc), bank=int(row.bank),
                             host_frame=int(row.host_frame), ticks=int(row.ticks),
                             ticks_since_previous_sample=int(row.ticks)-previous_ticks,
                             ram={f'{a:04x}': int(row.values[j]) for j,a in enumerate(self.addresses)}))
            previous_ticks, previous_frame = int(row.ticks), int(row.host_frame)
        return dict(complete=True, tick_pc=self.tick_pc, sample_pc=self.sample_pc,
                    addresses=list(self.addresses), samples=samples, ticks=ticks,
                    overflow=False, first_interval_is_partial=True, records=rows,
                    scope='Direct common-RAM snapshots before selected cartridge instructions. Ticks are instruction visits, not cycles; no RNG seed or guest state is changed. NES bank field is unavailable (0); SNES bank is the execution mapping.')
