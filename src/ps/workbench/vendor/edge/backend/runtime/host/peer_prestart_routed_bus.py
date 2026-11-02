"""Logical offsets for the NEW H5E1+HPQ1 route; no old-bitstream guessing.

The supplied PeerControlSession handles framing, exact replies and durable RX.
This adapter alone does not produce START admission or do any device reset.
"""
class PeerPrestartRoutedBus:
    READABLE = frozenset((0, 4, 8, 12, *range(0x100, 0x130, 4)))

    def __init__(self, peer, *, observer_base):
        if type(observer_base) is not int or observer_base != 0xd00:
            raise ValueError('Explicit new route base 0xD00 required')
        self.peer = peer
        self.base = observer_base
        # Mandatory first transport probe is address zero, txn=1; HPQ1 follows.
        if peer.read(0) != 0x48354531:
            raise RuntimeError('H5E1 endpoint required; no writes')
        if peer.read(self.base) != 0x48505131:
            raise RuntimeError('New mapped HPQ1 endpoint required; no writes')

    def read(self, offset):
        if type(offset) is not int or offset not in self.READABLE:
            raise ValueError('Unsupported HPQ1 read offset')
        return self.peer.read(self.base + offset)

    def write(self, offset, value):
        if type(offset) is not int or offset not in (0x10, 0x14) or type(value) is not int or value != 1:
            raise ValueError('Only an explicit HPQ1 snapshot command is writable')
        self.peer.write(self.base + offset, value)
