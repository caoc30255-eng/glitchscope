"""Explicit HRP1 bus only; no physical addresses, clock/Overlay/reset changes."""

def word(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('Unsigned DWORD required')
    return value


class CH0RXProfileDriver:
    def __init__(self, bus):
        self.bus = bus
        self.last_seq = 0
        if self.read(0) != 0x48525031:
            raise RuntimeError('HRP1 real UART profile endpoint required; no writes')

    def read(self, address):
        return word(self.bus.read(address))

    def apply(self, *, d, s):
        if type(d) is not int or type(s) is not int or d not in (1, 2, 3, 4) or not -2 <= s <= 3-d:
            raise ValueError('Illegal experiment d/s')
        # d=1 allows up to +2; d=2 to +1; d=3 to 0; d=4 to -1.
        status = self.read(4)
        if status & 0x38 or not status & 4:
            raise RuntimeError('Capture held, RX busy or profile fault; no restaging')
        before_seq = 0
        if status & 1:
            for address in (0x10, 0x14, 8):
                self.read(address)
            before_seq = self.read(8)
            if self.read(0x4c) != 7:
                raise RuntimeError('Previous profile not completely delivered')
        self.bus.write(0x30, d)
        self.bus.write(0x34, s & 0xffffffff)
        self.bus.write(0x38, 1)
        actual_d, actual_s, seq = (self.read(a) for a in (0x10, 0x14, 8))
        if (actual_d, actual_s) != (d, s & 0xffffffff) or seq != before_seq + 1 or seq <= self.last_seq or not seq:
            raise RuntimeError('Actual applied profile differs or sequence did not advance')
        if self.read(0x4c) != 7 or self.read(4) & 0x3b != 3:
            raise RuntimeError('No fully delivered actual idle dual-RX profile')
        self.last_seq = seq
        return {'d': d, 's': s, 'profile_seq': seq,
                'RX_profile_verified': True, 'source': 'HRP1 applied d/s + actual RX idle',
                'complete_START_admission': False}
