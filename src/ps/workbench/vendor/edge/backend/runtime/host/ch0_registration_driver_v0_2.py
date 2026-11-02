"""Explicit H0R2 only: separate local/peer epochs and coherent window clock.

No physical addresses, reset, START or complete-admission synthesis.
The caller's bus must propagate non-OK AXI read/write responses.
"""

def unsigned(value, bits=32, minimum=0):
    if type(value) is not int or not minimum <= value < 1 << bits:
        raise ValueError('Unsigned integer out of range')
    return value


class CH0RegistrationDriverV2:
    def __init__(self, bus, *, expected_clock_hz):
        self.bus = bus
        self.clock_hz = unsigned(expected_clock_hz, minimum=1)
        if self.read(0) != 0x48305232:
            raise RuntimeError('H0R2 required; old H0R1 is incompatible, no writes')

    def read(self, address):
        return unsigned(self.bus.read(address))

    def _binding(self):
        values = [self.read(a) for a in range(0x100, 0x140, 4)]
        peer_epoch = self.read(0x170)
        identity = 0
        for value in values[4:12]:
            identity = identity << 32 | value
        return {'epoch': values[0], 'record_id': values[1], 'kind': values[2],
                'request_length': values[3], 'identity': identity, 'peer_epoch': peer_epoch,
                'start': values[12] << 32 | values[13],
                'deadline': values[14] << 32 | values[15]}

    def register(self, *, epoch, peer_epoch, record_id, kind, identity,
                 request_length, delay_ticks, duration_ticks):
        for value in (epoch, peer_epoch, record_id, kind, request_length, delay_ticks, duration_ticks):
            unsigned(value)
        unsigned(identity, 256)
        if not epoch or not peer_epoch or not record_id or kind not in (1, 2, 3) or not 12 <= request_length <= 534 or delay_ticks < 4 or not duration_ticks:
            raise ValueError('Complete explicit namespaces and window required')
        if identity >> 219 or not (identity >> 187) & 0xffffffff or not (identity >> 155) & 0xffffffff or (identity >> 123) & 0xffffffff != peer_epoch or (identity >> 120) & 7 or not (identity >> 88) & 0xffffffff or identity & 255 > 1:
            raise ValueError('Full identity does not match the explicit peer namespace')
        if self.read(4) & 7:
            raise RuntimeError('Existing CH0 resource held/faulted; no restaging')
        for address, value in ((0x30, epoch), (0x34, record_id), (0x38, kind),
                               (0x3c, request_length), (0x40, delay_ticks),
                               (0x44, duration_ticks), (0x48, peer_epoch)):
            self.bus.write(address, value)
        for i in range(8):
            self.bus.write(0x50 + i * 4, identity >> (224 - i * 32) & 0xffffffff)
        self.bus.write(0x70, 1)
        actual = self._binding()
        expected = {'epoch': epoch, 'peer_epoch': peer_epoch, 'record_id': record_id,
                    'kind': kind, 'identity': identity, 'request_length': request_length}
        if any(actual[k] != v for k, v in expected.items()) or actual['deadline'] - actual['start'] != duration_ticks:
            raise RuntimeError('Actual immutable CH0 metadata differs from request')
        if self.read(0x18) != 0x1ffff or self.read(4) & 0x1f != 0x11:
            raise RuntimeError('No fully delivered actual dual-path registration')
        return actual

    def snapshot_window(self, binding, *, minimum_remaining_ticks):
        unsigned(minimum_remaining_ticks, 64, 1)
        if self._binding() != binding or self.read(4) & 0x1f != 0x11:
            raise RuntimeError('Actual binding changed, closed, received bytes or faulted')
        before_seq = 0
        if self.read(0x1a0) & 1:
            old = [self.read(a) for a in range(0x180, 0x1a0, 4)]
            before_seq = old[5]
            if self.read(0x1a4) != 255:
                raise RuntimeError('Old clock snapshot not delivered')
        self.bus.write(0x7c, 1)
        words = [self.read(a) for a in range(0x180, 0x1a0, 4)]
        tick = words[0] << 32 | words[1]
        if words[2:5] != [binding['epoch'], binding['peer_epoch'], binding['record_id']] or words[5] != before_seq + 1 or words[6] != 0x19 or words[7] != self.clock_hz:
            raise RuntimeError('Clock context, freshness, clean open window or rate mismatch')
        if tick < binding['start'] or tick + minimum_remaining_ticks >= binding['deadline']:
            raise RuntimeError('Window not open with required remaining tick margin')
        if self.read(0x1a4) != 255 or self.read(0x1a0) != 3 or self.read(4) & 0x1f != 0x11:
            raise RuntimeError('Clock snapshot no longer live/fully delivered')
        return {'tick': tick, 'epoch': words[2], 'peer_epoch': words[3],
                'record_id': words[4], 'snapshot_seq': words[5], 'clock_hz': words[7],
                'window_open': True, 'source': 'H0R2 coherent actual local clock',
                'complete_START_admission': False}
