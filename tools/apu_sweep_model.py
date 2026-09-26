"""Pulse sweep contract layered on the existing quantized counter model.

This is not a cycle-accurate APU. Period registers are written independently of
sweep state; length activity and sweep muting are separate conditions.
"""
from dataclasses import dataclass, field
from apu_model import Counters

@dataclass
class SweepCounters(Counters):
    periods: list[int] = field(default_factory=lambda: [0, 0])
    sweep_dividers: list[int] = field(default_factory=lambda: [0, 0])
    sweep_reload: list[int] = field(default_factory=lambda: [0, 0])

    def write(self, address: int, value: int) -> None:
        super().write(address, value)
        if 0x4000 <= address < 0x4008:
            c, reg = divmod(address - 0x4000, 4)
            if reg == 1:
                self.sweep_reload[c] = 1
            elif reg == 2:
                self.periods[c] = (self.periods[c] & 0x700) | value
            elif reg == 3:
                self.periods[c] = (self.periods[c] & 0xff) | ((value & 7) << 8)

    def target(self, channel: int) -> int:
        if channel not in (0, 1):
            raise ValueError('Sweep applies only to pulse channels')
        period = self.periods[channel]
        control = self.regs[channel * 4 + 1]
        change = period >> (control & 7)
        if control & 8:
            return (period - change - (channel == 0)) & 0x7ff
        return period + change

    def muted(self, channel: int) -> bool:
        control = self.regs[channel * 4 + 1]
        return self.periods[channel] < 8 or (not control & 8 and self.target(channel) > 0x7ff)

    def half(self) -> None:
        super().half()
        for c in (0, 1):
            control = self.regs[c * 4 + 1]
            if self.sweep_dividers[c] == 0 and control & 0x80 and control & 7 and not self.muted(c):
                self.periods[c] = self.target(c)
            if self.sweep_dividers[c] == 0 or self.sweep_reload[c]:
                self.sweep_dividers[c] = (control >> 4) & 7
                self.sweep_reload[c] = 0
            else:
                self.sweep_dividers[c] -= 1

    def volume(self, channel: int) -> int:
        value = super().volume(channel)
        return 0 if channel in (0, 1) and self.muted(channel) else value
