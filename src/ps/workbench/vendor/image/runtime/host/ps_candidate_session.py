"""Explicit PS orchestration for the reviewed 7020 candidate; imports perform no IO.

Caller supplies ordered DWORD buses which raise on AXI errors, durable storage,
exclusive ownership, independent epochs and measured window budgets. No Overlay
loading, reset, guessed identities, image source filling or uncertain retries.
"""
from h1_axi_driver import H1Transport
from h1_upload_ledger import UploadLedger
from h1_protocol import Kind
from ch1_runtime_driver import CH1RuntimeDriver, unsigned
from ch1_mapping_driver import CH1MappingDriver
from ch1_completion_ledger import CompletionLedger, H1CompletionReader, _codec
from ch1_axi_archive_driver import CH1ArchiveDriver
from ch1_control_session import ApplicationJournal, PeerControlSession
from ch1_peer_archive_driver import AXPeerArchiveDriver
from ch1_admission_parts import AdmissionParts
from ch1_verified_admission import VerifiedAdmissionCoordinator, FlightContext
from ch1_verified_item_owner import VerifiedSingleItemOwner
from ch0_registration_driver_v0_2 import CH0RegistrationDriverV2
from ch0_archive_driver import CH0ArchiveDriver
from ch0_rx_profile_driver import CH0RXProfileDriver
from peer_prestart_routed_bus import PeerPrestartRoutedBus
from peer_prestart_driver import PeerPrestartDriver
from ps_system_gate import SystemGate
from ps_hello import HelloSession
from pathlib import Path
import time
import ch1_evidence_store as store


BANKS = {
    'H1': (0x43c30000, 0x1000, 0x48315431),
    'CTRL': (0x43c40000, 0x1000, 0x48315231),
    'MAIN': (0x43c50000, 0x4000, 0x48314331),
    'AUX': (0x43c60000, 0x1000, 0x48314a31),
    'MAP': (0x43c70000, 0x1000, 0x48314d31),
    'CH0': (0x43c80000, 0x8000, 0x48305232),
    'PROFILE': (0x43c90000, 0x1000, 0x48525031),
    'SYS': (0x43ca0000, 0x1000, 0x48375331),
}


class CandidateSession:
    def __init__(self, buses, root, *, local_epoch, peer_epoch, session,
                 control_epoch, exclusive_owner=False, poll_limit=1000):
        if exclusive_owner is not True:
            raise ValueError('Exclusive device/control UART ownership required')
        for name, value in [('local epoch', local_epoch), ('peer epoch', peer_epoch),
                            ('H1 session', session), ('control epoch', control_epoch)]:
            unsigned(value, 32, name, 1)
        unsigned(poll_limit, 32, 'poll limit', 1)
        for name, (_, _, identity) in BANKS.items():
            if unsigned(buses[name].read(0), 32, 'IP ID') != identity:
                raise RuntimeError(f'Wrong production {name} bank; no hardware writes')
        if (buses['SYS'].read(4) & ~8 or buses['SYS'].read(0x0c)
                or buses['SYS'].read(0x20) or buses['SYS'].read(0x1c)
                or buses['SYS'].read(0x18) or buses['CTRL'].read(8)
                or buses['H1'].read(4) & 0x7e or buses['CH0'].read(4) & 7):
            raise RuntimeError('Fresh idle reset state required; existing flights cannot resume')
        self.root = Path(root)
        self.local_epoch, self.peer_epoch, self.session = local_epoch, peer_epoch, session
        self.limit = poll_limit
        self.current = self.ticket = self.config_owner = None
        self.mark_capture = None
        self.last_retired_owner = None
        self.fault = False
        self.handles = []
        try:
            self.journal = ApplicationJournal(self.root, local_epoch); self.handles.append(self.journal)
            self.completion = CompletionLedger(self.root/'completion', local_epoch=local_epoch,
                peer_epoch=peer_epoch, session=session); self.handles.append(self.completion)
            self.upload = UploadLedger(self.root/'upload', session); self.handles.append(self.upload)
            self.gate = SystemGate(buses['SYS'], self.journal)
            self.runtime = CH1RuntimeDriver(buses['CTRL'], poll_limit=poll_limit, system_gate=self.gate)
            self.mapping = CH1MappingDriver(buses['MAP'])
            self.reader = H1CompletionReader(buses['H1'], self.completion)
            self.transport = H1Transport(buses['H1'])
            self.profile = CH0RXProfileDriver(buses['PROFILE'])
            self.ch0 = CH0RegistrationDriverV2(buses['CH0'], expected_clock_hz=100000000)
            self.ch0_archive = CH0ArchiveDriver(self.ch0, self.root/'CH0')
            self.archive = CH1ArchiveDriver(buses['MAIN'], buses['AUX'], self.root/'CH1')
            self.control_epoch = control_epoch
            self.peer = None
        except Exception:
            self.close()
            raise

    def _available(self):
        if self.fault:
            raise RuntimeError('PS session stopped; no automatic resume')

    def _stop(self, exc):
        self.fault = True
        self.upload.fault = True
        try: self.journal.record('PS_stop', error=repr(exc))
        except Exception: pass
        transport=getattr(self,'control_transport',None)
        pause=getattr(transport,'pause_receiver',None)
        if callable(pause):
            try:
                pause()
                self.journal.record('background_RX_paused',
                    **transport.pending_snapshot(limit=65536))
            except Exception: pass

    def _archive_upload(self, record_id):
        started = time.monotonic()
        for _ in range(self.limit):
            proof = self.peer_archive.archive_prepared(self.upload,
                peer_epoch=self.peer_epoch, record_id=record_id, route=0)
            if proof is not None:
                self.journal.record('peer_raw_archive_elapsed',record_id=record_id,
                    elapsed_seconds=time.monotonic()-started)
                return proof
        raise TimeoutError('Peer raw evidence not sealed; no retransmission')

    def initialize(self, control_transport, *, hello_record_id=0xffffffff):
        """Authorize the peer namespace, activate local epoch, then one HELLO."""
        self._available()
        if self.peer is not None:
            raise RuntimeError('Initialization cannot be repeated')
        self.hello_record_id = unsigned(hello_record_id, 32, 'HELLO store record ID', 1)
        try:
            self.control_transport=control_transport
            if callable(getattr(control_transport,'close',None)):
                self.handles.append(control_transport)
            self.peer = PeerControlSession(control_transport, self.journal, self.control_epoch)
            # Mandatory first remote READ32 is address0/txn1, enforced by peer.
            if self.peer.read(0) != 0x48354531 or self.peer.read(4) != 0x20:
                raise RuntimeError('Fresh idle unauthorized H5E1 peer required')
            if tuple(self.peer.read(a) for a in (0x24, 0x28, 0x2c)) != (0, 0, 0):
                raise RuntimeError('Peer namespace already used')
            self.observer = PeerPrestartDriver(PeerPrestartRoutedBus(self.peer, observer_base=0xd00))
            self.journal.record('peer_namespace_intent', peer_epoch=self.peer_epoch,
                session=self.session, route=0)
            for a, v in ((0x10, self.peer_epoch), (0x14, self.session), (0x18, 0)):
                self.peer.write(a, v)
            self.peer.write(0x1c, 1)
            status = self.peer.read(4)
            if (tuple(self.peer.read(a) for a in (0x24, 0x28, 0x2c)) !=
                    (self.peer_epoch, self.session, 0) or status & 0x5e
                    or status & 0x21 != 0x21 or status & ~0x3ff):
                raise RuntimeError('Peer namespace authorization unconfirmed')
            self.runtime.activate_epoch(self.local_epoch)
            self.peer_archive = AXPeerArchiveDriver(self.peer, self.root/'peer', poll_limit=self.limit)
            HelloSession(self.transport, self.upload, self.journal, poll_limit=self.limit,
                save_peer=lambda: self._archive_upload(self.hello_record_id)).establish()
            self.coordinator = VerifiedAdmissionCoordinator(self.root/'admission', self.journal,
                peer=self.peer, observer=self.observer, parts=AdmissionParts(self.root/'flight', self.journal),
                profile=self.profile, ch0=self.ch0, runtime=self.runtime)
            self.journal.record('PS_session_initialized', local_epoch=self.local_epoch,
                peer_epoch=self.peer_epoch, session=self.session)
        except Exception as exc:
            self._stop(exc)
            raise

    def configure_fault_capture(self,mmio_factory,hwh_path):
        self._available()
        if self.current is not None or self.mark_capture is not None or not hasattr(self,'coordinator'):
            raise RuntimeError('Initialized idle session and fresh mark driver required')
        from raw_mark_snapshot import RawMarkCapture
        self.mark_capture=RawMarkCapture.from_reviewed_hwh(mmio_factory,self.root/'MARK',hwh_path)
        return {'mark_capture_configured':True,'hardware_writes':0,'legacy_hardware_identity_register':False}

    def prepare_flight(self, kind, inner, *, record_id, d, s, ch1_delay_ticks,
                       ch1_duration_ticks, ch0_delay_ticks, ch0_duration_ticks,fault_profile=None):
        started = time.monotonic()
        self._available()
        if not hasattr(self, 'coordinator') or self.current is not None:
            raise RuntimeError('Initialized idle session required')
        if type(d) is not int or type(s) is not int or d not in (1, 2, 3, 4) or not -2 <= s <= 3-d:
            raise ValueError('Illegal B experiment profile; no hardware writes')
        for name, value in [('CH1 delay', ch1_delay_ticks), ('CH0 delay', ch0_delay_ticks)]:
            unsigned(value, 32, name, 4)
        for name, value in [('CH1 duration', ch1_duration_ticks), ('CH0 duration', ch0_duration_ticks)]:
            unsigned(value, 32, name, 1)
        try:
            kind = Kind(kind)
            if kind not in (Kind.CONFIG, Kind.ITEM, Kind.CLEANUP):
                raise ValueError('CONFIG/ITEM/CLEANUP only')
            unsigned(record_id, 32, 'record ID', 1)
            if record_id == self.hello_record_id:
                raise ValueError('Record ID reserved for persisted HELLO')
            basis = self.observer.snapshot(current=False, epoch=self.peer_epoch, session=self.session)
            decoded = {Kind.CONFIG: _codec().decode_config, Kind.ITEM: _codec().decode_item,
                       Kind.CLEANUP: _codec().decode_cleanup}[kind](bytes(inner))
            if not decoded['valid']:
                raise ValueError('Malformed source request')
            self.upload.prepare(kind, bytes(inner))
            fields = dict(reserved=0, session=self.session, seq=self.upload.current[1],
                route_epoch=self.peer_epoch, slot=0, generation=basis['next_generation'],
                run_id=decoded['run_id'], image_id=decoded['image_id'],
                trial_id=decoded.get('trial_id', 0), item_index=decoded.get('item_index', 0),
                attempt_id=decoded.get('attempt_id', 0), route_mode=decoded.get('route_mode', 0))
            identity = 0
            for name, width in store.IDENTITY:
                identity = identity << width | unsigned(fields[name], width, name)
            record_kind = {Kind.CONFIG: 2, Kind.ITEM: 1, Kind.CLEANUP: 3}[kind]
            context = FlightContext(self.local_epoch, record_id, record_kind, identity)
            def arm(c):
                return self.mapping.arm_prepared(self.runtime, self.reader, self.upload,
                    epoch=c.epoch, peer_epoch=self.peer_epoch, record_id=c.record_id,
                    kind=c.kind, identity=c.identity, delay_ticks=ch1_delay_ticks,
                    duration_ticks=ch1_duration_ticks)
            def deliver(binding):
                self.transport.send_prepared(self.upload)
                proof = self._archive_upload(record_id)
                for _ in range(self.limit):
                    self.reader.read_and_preserve()
                    if self.completion.accepted:
                        return proof
                raise TimeoutError('No saved actual ACCEPTED; do not resend')
            self.ticket = self.coordinator.issue(context, self.upload, self.completion,
                arm_ch1=arm, deliver_and_archive=deliver, d=d, s=s,
                ch0_delay_ticks=ch0_delay_ticks, ch0_duration_ticks=ch0_duration_ticks,
                config_owner=self.config_owner,
                **({'fault_profile':fault_profile,'mark_capture':self.mark_capture} if fault_profile is not None else {}))
            self.current = VerifiedSingleItemOwner(self.journal, self.runtime.binding(), self.upload, self.completion)
            self.last_preparation_seconds = time.monotonic()-started
            self.journal.record('flight_preparation_complete',record_id=record_id,
                elapsed_seconds=self.last_preparation_seconds)
            return self.current.binding
        except Exception as exc:
            self._stop(exc)
            raise

    def start_current(self, *, ch0_margin_ticks, ch1_margin_ticks):
        self._available()
        if self.current is None: raise RuntimeError('No flight')
        try:
            return self.current.start_verified(self.peer, self.coordinator, self.ticket,
                ch0_margin_ticks=ch0_margin_ticks, ch1_margin_ticks=ch1_margin_ticks)
        except Exception as exc:
            self._stop(exc)
            raise

    def window_readiness(self, *, ch0_margin_ticks, ch1_margin_ticks):
        """Read both actual clock domains. A waiting result issues no START."""
        self._available()
        if self.current is None: raise RuntimeError('No flight')
        unsigned(ch0_margin_ticks, 64, 'CH0 margin', 1)
        unsigned(ch1_margin_ticks, 64, 'CH1 margin', 1)
        try:
            record = self.coordinator._ticket(self.ticket)
            bound = record['ch0_binding']
            if self.ch0._binding() != bound or self.ch0.read(4) & 0x1f != 0x11:
                raise RuntimeError('CH0 received/closed/faulted or binding changed')
            old_seq = 0
            if self.ch0.read(0x1a0) & 1:
                old = [self.ch0.read(a) for a in range(0x180, 0x1a0, 4)]
                old_seq = old[5]
                if self.ch0.read(0x1a4) != 255:
                    raise RuntimeError('Old CH0 clock not fully delivered')
            self.ch0.bus.write(0x7c, 1)
            words = [self.ch0.read(a) for a in range(0x180, 0x1a0, 4)]
            zero_tick = words[0] << 32 | words[1]
            if (words[2:5] != [bound['epoch'], bound['peer_epoch'], bound['record_id']]
                    or words[5] != old_seq + 1 or words[7] != 100000000
                    or words[6] not in (9, 0x19) or self.ch0.read(0x1a4) != 255):
                raise RuntimeError('CH0 actual clock/context/coverage invalid')
            one = self.runtime.snapshot()
            binding = self.current.binding
            if (one['epoch'] != binding.epoch or self.runtime.binding() != binding
                    or zero_tick + ch0_margin_ticks >= bound['deadline']
                    or one['tick'] + ch1_margin_ticks >= binding.deadline):
                raise RuntimeError('Capture window changed or remaining margin exhausted')
            opened = (zero_tick >= bound['start'] and words[6] == 0x19
                      and self.ch0.read(0x1a0) == 3 and one['tick'] >= binding.start)
            return {'windows_open': opened, 'CH0_tick': zero_tick, 'CH1_tick': one['tick'],
                    'START_sent': False, 'complete_START_admission': False}
        except Exception as exc:
            self._stop(exc)
            raise

    def poll_current(self):
        self._available()
        if self.current is None: raise RuntimeError('No flight')
        if self.current.local_retired:
            raise RuntimeError('Use poll_next_credit after local retirement; do not consume READY here')
        try:
            self.reader.read_and_preserve()
            life = self.current.poll_lifecycle(self.peer)
            return {**life, 'saved_H1_TX_DONE': self.completion.done,
                    'CH0_closed': bool(self.ch0.read(4) & 2),
                    'CH1_finalized': bool(self.runtime.status() & 64)}
        except Exception as exc:
            self._stop(exc)
            raise

    def retire_current(self):
        self._available()
        if self.current is None: raise RuntimeError('No flight')
        try:
            return self.current.retire_verified(self.peer, ch0_archive=self.ch0_archive,
                mapping=self.mapping, reader=self.reader, archive=self.archive)
        except Exception as exc:
            self._stop(exc)
            raise

    def poll_next_credit(self):
        self._available()
        if self.current is None: raise RuntimeError('No flight')
        if not self.current.local_retired:
            raise RuntimeError('Local retirement must complete before waiting for next credit')
        try:
            if not self.current.peer_retired:
                self.current.poll_lifecycle(self.peer)
                if not self.current.peer_retired:
                    return {'next_item_allowed': False}
            result = self.current.accept_ready_verified(self.reader)
            if result['next_item_allowed']:
                self.last_retired_owner = self.current
                if self.current.binding.kind == 2: self.config_owner = self.current
                self.current = self.ticket = None
            return result
        except Exception as exc:
            self._stop(exc)
            raise

    def close(self):
        for handle in reversed(self.handles): handle.close()
        self.handles.clear()
