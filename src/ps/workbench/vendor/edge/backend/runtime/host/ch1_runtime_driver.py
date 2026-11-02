"""H1R1 runtime API. Exclusive, ordered DWORD MMIO access is required.

No board addresses, Overlay loading, reset, or physical-done synthesis.
The transport must raise on failed AXI responses. Poll bounds are operation
bounds, not hardware timeouts. Epoch allocation across resets is caller-owned.
"""
from dataclasses import dataclass


def unsigned(value, bits, name, minimum=0):
    if type(value) is not int or not minimum <= value < (1 << bits):
        raise ValueError(f'{name} must be an unsigned {bits}-bit integer >= {minimum}')
    return value


@dataclass(frozen=True)
class Binding:
    epoch: int
    record_id: int
    kind: int
    identity: int
    start: int
    deadline: int


@dataclass(frozen=True)
class ReleaseTicket:
    binding: Binding
    retire_count_before: int


class CH1RuntimeDriver:
    def __init__(self, mmio, *, poll_limit=1000, system_gate=None):
        self.bus = mmio
        self.system_gate = system_gate
        self.poll_limit = unsigned(poll_limit, 32, 'poll_limit', 1)
        if self._read(0) != 0x48315231:
            raise RuntimeError('Requires H1R1; no writes performed')
        self.last_snapshot = None

    def _read(self, address):
        return unsigned(self.bus.read(address), 32, 'MMIO DWORD')

    def _write(self, address, value):
        self.bus.write(address, unsigned(value, 32, 'MMIO DWORD'))

    def status(self):
        status = self._read(4)
        if status & 8:
            raise RuntimeError(f'Runtime fault {self._read(0x0c)}; evidence retained')
        return status

    def activate_epoch(self, epoch):
        unsigned(epoch, 32, 'epoch', 1)
        if self.status() & (2 | 4 | 32 | 256) or epoch <= self._read(8):
            raise RuntimeError('Epoch requires idle, empty journals and a strictly newer value')
        # A partially delivered old snapshot must be finished before epoch change.
        if self.status() & 16:
            self._snapshot_words()
        self._write(0x30, epoch)
        self._write(0x34, 1)
        if self._read(8) != epoch or not self.status() & 1:
            raise RuntimeError('Epoch activation not confirmed')
        self.last_snapshot = None

    def _snapshot_words(self):
        high, low, epoch, seq = (self._read(a) for a in (0x14, 0x18, 0x1c, 0x20))
        if self._read(0x28) != 15:
            raise RuntimeError('Snapshot was not fully delivered')
        return {'tick': (high << 32) | low, 'epoch': epoch, 'seq': seq}

    def snapshot(self):
        status = self.status()
        if not status & 1:
            raise RuntimeError('Activate an explicitly allocated epoch first')
        old_seq = None
        if status & 16:
            old_seq = self._snapshot_words()['seq']
        self._write(0x10, 1)
        snap = self._snapshot_words()
        if not self.status() & 16 or snap['epoch'] != self._read(8) or not snap['seq']:
            raise RuntimeError('Invalid hardware snapshot')
        if old_seq is not None and snap['seq'] != old_seq + 1:
            raise RuntimeError('Snapshot command did not establish a new snapshot')
        if self.last_snapshot is not None:
            old = self.last_snapshot
            if snap['epoch'] == old['epoch'] and (snap['seq'] <= old['seq'] or snap['tick'] < old['tick']):
                raise RuntimeError('Hardware snapshot regressed')
        self.last_snapshot = snap
        return dict(snap)

    def binding(self):
        status = self.status()
        if not status & 2:
            raise RuntimeError('No live runtime binding')
        epoch = self._read(8)
        record_id, kind = self._read(0x100), self._read(0x104)
        start = (self._read(0x108) << 32) | self._read(0x10c)
        deadline = (self._read(0x110) << 32) | self._read(0x114)
        identity = 0
        for address in range(0x120, 0x140, 4):
            identity = (identity << 32) | self._read(address)
        if not self.status() & 2 or self._read(8) != epoch:
            raise RuntimeError('Binding changed during read')
        return Binding(epoch, record_id, kind, identity, start, deadline)

    def arm(self, *, kind, record_id, identity, delay_ticks, duration_ticks):
        unsigned(kind, 2, 'kind', 1)
        unsigned(record_id, 32, 'record_id', 1)
        unsigned(identity, 256, 'identity')
        unsigned(delay_ticks, 32, 'delay_ticks', 4)
        unsigned(duration_ticks, 32, 'duration_ticks', 1)
        if identity >> 219 or not ((identity >> 187) & 0xffffffff) or not ((identity >> 155) & 0xffffffff) or not ((identity >> 88) & 0xffffffff) or (identity & 255) > 1:
            raise ValueError('Invalid complete ARM identity')
        status = self.status()
        if not status & 1 or status & (2 | 4 | 32 | 256):
            raise RuntimeError('ARM requires active epoch, idle core and empty journals')
        for address, value in ((0x40, kind), (0x44, record_id), (0x48, delay_ticks), (0x4c, duration_ticks)):
            self._write(address, value)
        for index in range(8):
            self._write(0x50 + 4 * index, (identity >> (224 - 32 * index)) & 0xffffffff)
        # Do not automatically retry ARM after an uncertain transport response.
        self._write(0x70, 1)
        for _ in range(self.poll_limit):
            status = self.status()
            if status & 2 and not status & 32:
                result = self.binding()
                if (result.kind, result.record_id, result.identity) != (kind, record_id, identity) or result.deadline - result.start != duration_ticks:
                    raise RuntimeError('ARM binding differs from requested record')
                return result
        raise TimeoutError('ARM acceptance unconfirmed; inspect binding before further commands')

    def request_release(self, binding):
        if self.binding() != binding:
            raise RuntimeError('Release binding mismatch; no command sent')
        status = self.status()
        count = self._read(0x24)
        ticket = ReleaseTicket(binding, count)
        if status & 4:
            return ticket  # Already pending: never rewrite immutable staging.
        if status & (32 | 256) or status & (64 | 128) != (64 | 128):
            raise RuntimeError('Release awaits real core qualification and empty journals')
        self._write(0x80, binding.epoch)
        self._write(0x84, binding.record_id)
        for index in range(8):
            self._write(0x88 + 4 * index, (binding.identity >> (224 - 32 * index)) & 0xffffffff)
        self._write(0xa8, 1)
        # Command delivery is not retirement; ticket also handles immediate retirement.
        self.status()
        return ticket

    def wait_retirement(self, ticket, *, drain_aux=None):
        for _ in range(self.poll_limit):
            if drain_aux is not None:
                drain_aux()
            status = self.status()
            count = self._read(0x24)
            if self._read(8) != ticket.binding.epoch:
                raise RuntimeError('Epoch changed while waiting; retirement unverified')
            delta = (count - ticket.retire_count_before) & 0xffffffff
            if delta == 1 and not status & (2 | 4 | 32 | 64):
                # A second status/count check rejects concurrent changes. Exclusive owner required.
                if self.status() & (2 | 4 | 32 | 64) or self._read(0x24) != count:
                    raise RuntimeError('Retirement state changed during verification')
                if self.system_gate is not None:
                    self.system_gate.verify_retired(ticket.binding, count)
                return {'hardware_retirement_verified': True, 'retire_count': count}
            if delta == 1:
                # Core counter advances before the registered retirement receipt
                # clears controller busy/pending. Poll actual idle; do not retry.
                continue
            if delta or not status & 2:
                raise RuntimeError('Unexpected retirement count or binding loss')
            if self.binding() != ticket.binding:
                raise RuntimeError('Binding changed while waiting')
        raise TimeoutError('Actual retirement not observed; keep evidence and ticket for retry')

    def abort(self):
        self.binding()
        if self.status() & (4 | 32):
            raise RuntimeError('Cannot abort a pending ARM or release')
        self._write(0xb0, 1)
        self.status()
        return {'abort_command_submitted': True, 'hardware_retirement_verified': False}

    def archive_and_request_release(self, archive_driver, *, expected_payload=None):
        """Persist using hardware watermark, then request release when real guard permits.

        A missing physical-done event leaves the durable record held. Retry may
        reuse the existing verified archive. No fake completion is generated.
        """
        bound = self.binding()
        snap = self.snapshot()
        if snap['epoch'] != bound.epoch:
            raise RuntimeError('Snapshot epoch differs from binding')
        saved = archive_driver.archive_current(watermark_epoch=snap['epoch'],
            watermark_tick=snap['tick'], expected_payload=expected_payload)
        if saved is None or (saved['epoch'], saved['record_id'], int(saved['identity_hex'], 16)) != (bound.epoch, bound.record_id, bound.identity):
            raise RuntimeError('Archive differs from runtime binding; no release')
        archive_driver.drain_aux()
        if self.system_gate is not None:
            self.system_gate.grant_saved_release(self, bound, saved)
        ticket = self.request_release(bound)
        return saved, ticket
