"""Two-phase durable Direct admission over explicitly supplied source drivers.

Actual ARM precedes H1 offer, avoiding a queued-status ARM veto. Explicit
delays must cover slow source verification. Each local window uses its own ticks. A sealed ticket is not START permission; claim requires live sources
after WINDOW and durable one-use consumption. No implicit device IO on import.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import uuid
import ch1_evidence_store as store
from ch1_peer_archive_driver import persist_exact
from ch1_runtime_driver import unsigned
from ps_path_compat import path_within


@dataclass(frozen=True)
class FlightContext:
    epoch: int
    record_id: int
    kind: int
    identity: int


@dataclass(frozen=True)
class AdmissionTicket:
    token: str


class VerifiedAdmissionCoordinator:
    def __init__(self, root, journal, *, peer, observer, parts, profile, ch0, runtime):
        self.root = Path(root)
        self.journal = journal
        self.peer, self.observer, self.parts = peer, observer, parts
        self.profile, self.ch0, self.runtime = profile, ch0, runtime
        self.tickets = {}
        self.fault = False

    def _files(self, directory):
        directory = Path(directory)
        marker = json.loads((directory / 'committed.json').read_text())
        for name, fingerprint in marker['files'].items():
            path = (directory / name).resolve()
            if not path_within(path, directory) or store.sha(path.read_bytes()) != fingerprint:
                raise ValueError('Persistent source manifest mismatch')
        return marker

    def _peer_archive(self, context, upload, proof):
        fields = store._fields(context.identity, store.IDENTITY)
        kind, seq, inner, outer = upload.current
        directory = Path(proof['directory'])
        manifest = self._files(directory)
        if set(manifest['files']) != {'context.json', 'inner.bin', 'outer.bin'}:
            raise ValueError('Peer archive has incomplete source files')
        actual = json.loads((directory / 'context.json').read_text())
        expected = {'kind': int(kind), 'epoch': fields['route_epoch'],
                    'session': fields['session'], 'seq': seq, 'len': len(inner),
                    'crc': store.crc16(inner), 'route': 0}
        if any(actual.get(k) != v or proof.get(k) != v for k, v in expected.items()):
            raise ValueError('Peer raw archive context differs from actual prepared flight')
        if (directory / 'inner.bin').read_bytes() != bytes(inner) or (directory / 'outer.bin').read_bytes() != bytes(outer):
            raise ValueError('Peer archived bytes differ from prepared flight')
        if not proof.get('peer_store_verified') or not actual.get('ticket') or not actual.get('store_record_id'):
            raise RuntimeError('Missing exact peer saved-take receipt')
        if proof.get('ticket') != actual['ticket'] or proof.get('store_record_id') != actual['store_record_id']:
            raise ValueError('Changed peer saved-take identity')
        if self.peer.read(4) & 0x5e or (self.peer.read(0x68), self.peer.read(0x6c)) != (actual['store_record_id'], actual['ticket']):
            raise RuntimeError('Actual peer saved-take not retained/empty/fault-free')

    def _peer_live(self, record):
        sequence = record['peer_snapshot']['snapshot_seq']
        before = self.observer.read(8)
        status = self.observer.read(4)
        after = self.observer.read(8)
        if before != sequence or after != sequence or status & 255 != 0xe7:
            raise RuntimeError('Actual HPQ1 tuple replaced, started, faulted or no longer live')

    def _profile_live(self, record):
        profile = record['profile']
        if self.profile.read(0) != 0x48525031 or self.profile.read(4) & 15 != 7:
            raise RuntimeError('Actual dual RX profile not clean/applied/idle')
        if (self.profile.read(0x10), self.profile.read(0x14), self.profile.read(8), self.profile.read(0x4c)) != (
                profile['d'], profile['s'] & 0xffffffff, profile['profile_seq'], 7):
            raise RuntimeError('Actual applied RX profile changed')

    def _completion(self, completion, binding, prepared):
        kind,seq,inner,outer=prepared
        current=completion.current
        if completion.fault or not completion.accepted or completion.done or current is None:
            raise RuntimeError('Saved H1 ACCEPTED unavailable/faulted/completed')
        if current['binding']!=asdict(binding) or current['seq']!=seq or current['inner_crc']!=store.crc16(inner) or current['inner_sha256']!=store.sha(inner) or current['outer_sha256']!=store.sha(outer):
            raise ValueError('Completion ledger binding/frame differs from actual flight')
        completion.verify_journal()

    def _local_windows(self, record, ch0_margin, ch1_margin):
        unsigned(ch0_margin, 64, 'CH0 remaining ticks', 1)
        unsigned(ch1_margin, 64, 'CH1 remaining ticks', 1)
        binding = record['binding']
        self._completion(record['completion'],binding,record['prepared'])
        if record['parts'].get('mark_required'):
            record['mark_capture'].verify_armed(binding)
        if self.runtime.binding() != binding:
            raise RuntimeError('Actual CH1 binding differs')
        self._profile_live(record)
        zero = self.ch0.snapshot_window(record['ch0_binding'], minimum_remaining_ticks=ch0_margin)
        one = self.runtime.snapshot()
        if one['epoch'] != binding.epoch or one['tick'] < binding.start or one['tick'] + ch1_margin >= binding.deadline:
            raise RuntimeError('CH1 window not open with remaining margin')
        return {'CH0': zero, 'CH1': one}

    def _ticket(self, ticket):
        if not isinstance(ticket, AdmissionTicket) or ticket.token not in self.tickets:
            raise RuntimeError('Coordinator-issued ticket required, not prerequisite flags')
        record = self.tickets[ticket.token]
        if record['ticket'] is not ticket or record['phase'] != 'SEALED':
            raise RuntimeError('Foreign, consumed or incomplete admission ticket')
        self._files(record['directory'])
        if (record['directory'] / 'admission.json').read_bytes() != record['sealed_bytes']:
            raise ValueError('Sealed admission altered')
        return record

    def issue(self, context, upload, completion, *, arm_ch1, deliver_and_archive,
              d, s, ch0_delay_ticks, ch0_duration_ticks, config_owner=None,
              fault_profile=None,mark_capture=None):
        """ARM then deliver/archive the prepared H1 through explicit callbacks.

        arm_ch1 must use existing mapping/runtime and return actual Binding.
        deliver_and_archive must save real H1 ACCEPTED and return AXPeerArchive
        receipt. Delays/windows are explicit; this API never chooses/reset clocks.
        """
        if self.fault or not isinstance(context, FlightContext):
            raise RuntimeError('Available coordinator and explicit flight context required')
        try:
            unsigned(context.epoch, 32, 'local epoch', 1)
            unsigned(context.record_id, 32, 'local record ID', 1)
            unsigned(context.identity, 256, 'full identity')
            unsigned(context.kind, 2, 'record kind', 1)
            fields = store._fields(context.identity, store.IDENTITY)
            if fields['reserved'] or fields['slot'] or not fields['generation'] or not fields['session'] or not fields['seq']:
                raise ValueError('Canonical exclusive one-slot identity required')
            if upload.fault or upload.current is None or fields['route_mode'] != 0:
                raise RuntimeError('Immutable Direct prepared upload required')
            kind, seq, inner, outer = upload.current
            if (int(kind),seq,upload.session) != ({1:3,2:2,3:4}[context.kind],fields['seq'],fields['session']):
                raise ValueError('Prepared envelope and proposed binding differ before ARM')
            if context.kind in (2,3) and any(fields[k] for k in ('trial_id','item_index','attempt_id')):
                raise ValueError('Management identity must use zero trial/item/attempt')
            if fault_profile is not None:
                from fault_profile import FaultProfile
                from multi_point_profile import MultiPointProfile
                from raw_mark_snapshot import RawMarkCapture
                if context.kind!=1 or type(fault_profile) not in (FaultProfile,MultiPointProfile) or type(mark_capture) is not RawMarkCapture:
                    raise ValueError('Marked ITEM requires typed profile and physical snapshot driver')
                fault_profile.validate(inner)
                if mark_capture.used:raise RuntimeError('One-shot mark capture already used')
            binding = arm_ch1(context)
            if (binding.epoch, binding.record_id, binding.kind, binding.identity) != (
                    context.epoch, context.record_id, context.kind, context.identity) or self.runtime.binding() != binding:
                raise ValueError('Actual local ARM consumed another flight')
            peer_archive = deliver_and_archive(binding)
            if not peer_archive:
                raise RuntimeError('Actual H1 delivery/archive not complete')
            current = self.observer.snapshot(current=True, epoch=fields['route_epoch'], session=fields['session'])
            if (current['identity'], current['kind'], current['length'], current['next_generation']) != (
                    context.identity, int(kind), len(inner), fields['generation']):
                raise ValueError('Actual HPQ1 current identity/generation/kind/length differs')
            self._peer_archive(context, upload, peer_archive)
            partial = self.parts.register(context, upload, self.peer, config_owner=config_owner,
                **({'fault_profile':fault_profile} if fault_profile is not None else {}))
            if not partial.get('STM_expected_flight_registered') or not partial.get('policy_ready') or bool(partial.get('mark_required')) != (fault_profile is not None):
                raise RuntimeError('Required persisted flight/policy source missing')
            self._files(partial['flight_dir'])
            profile = self.profile.apply(d=d, s=s)
            self.journal.record('admission_sources_after_ARM_and_H1_save',context=asdict(context),peer_snapshot=current,profile=profile)
            self._completion(completion,binding,(int(kind),seq,bytes(inner),bytes(outer)))
            ch0_binding = self.ch0.register(epoch=context.epoch, peer_epoch=fields['route_epoch'],
                record_id=context.record_id, kind=context.kind, identity=context.identity,
                request_length=len(inner), delay_ticks=ch0_delay_ticks, duration_ticks=ch0_duration_ticks)
            record = {'binding': binding, 'ch0_binding': ch0_binding, 'peer_snapshot': current,
                      'profile': profile, 'parts': partial, 'peer_archive': dict(peer_archive),
                      'upload': upload, 'completion': completion,
                      'prepared': (int(kind), seq, bytes(inner), bytes(outer))}
            if fault_profile is not None:
                record['mark_capture']=mark_capture
                record['mark_arm_receipt']=mark_capture.arm(binding,inner,fault_profile)
            self._peer_live(record)
            now = self.runtime.snapshot()
            if now['epoch'] != binding.epoch or now['tick'] >= binding.deadline:
                raise RuntimeError('Slow source verification exhausted CH1 capture window')
            token = AdmissionTicket(uuid.uuid4().hex)
            directory = self.root / f'epoch_{context.epoch:08x}_record_{context.record_id:08x}'
            # This record key is never silently reused; a failed seal remains held.
            directory.mkdir(parents=True, exist_ok=False)
            data = store._json({'token': token.token, 'context': asdict(context), 'binding': asdict(binding),
                'CH0_binding': ch0_binding, 'peer_snapshot': current, 'profile': profile,
                'flight_dir': partial['flight_dir'], 'peer_archive': dict(peer_archive),
                'phase': 'SEALED_WAIT_FOR_LOCAL_WINDOWS', 'START_executed': False,
                **({'mark_arm_receipt':record['mark_arm_receipt']} if fault_profile is not None else {})})
            persist_exact(directory, {'admission.json': data})
            self.journal.record('admission_ticket_sealed',token=token.token,directory=str(directory),receipt_sha256=store.sha(data))
            self.tickets[token.token] = {**record, 'ticket': token, 'directory': directory,
                                        'sealed_bytes': data, 'phase': 'SEALED'}
            return token
        except Exception:
            self.fault = True
            raise

    def claim(self, ticket, owner, *, ch0_margin, ch1_margin):
        """Called AFTER WINDOW ACK. Burn before final check; never blind-retry."""
        if self.fault:
            raise RuntimeError('Admission coordinator stopped')
        try:
            record = self._ticket(ticket)
            binding = record['binding']
            if owner.binding != binding or owner.upload is not record['upload'] or owner.completion is not record['completion']:
                raise RuntimeError('Ticket owner mismatch')
            kind, seq, inner, outer = owner.upload.current
            if (int(kind), seq, bytes(inner), bytes(outer)) != record['prepared'] or owner.upload.fault:
                raise ValueError('Immutable prepared upload changed')
            self._files(record['parts']['flight_dir'])
            if (Path(record['parts']['flight_dir']) / 'inner.bin').read_bytes() != bytes(inner):
                raise ValueError('Persisted expected flight changed')
            self._completion(owner.completion,binding,record['prepared'])
            self._local_windows(record, ch0_margin, ch1_margin)
            record['phase'] = 'CONSUMED'
            self.journal.record('admission_consumed',token=ticket.token,identity=binding.identity)
            store._write(record['directory'] / 'consumed.json',store._json({'token':ticket.token,'identity':binding.identity}))
            store._sync_directory(record['directory'])
            # Slow fsync and remote MMIO can exhaust a window: check afterward.
            self._peer_live(record)
            windows = self._local_windows(record, ch0_margin, ch1_margin)
            self._files(record['directory'])
            return {'identity': binding.identity, 'local_epoch': binding.epoch,
                    'peer_epoch': record['peer_snapshot']['peer_epoch'], 'record_id': binding.record_id,
                    'CH0_registered': True, 'STM_expected_flight_registered': True,
                    'policy_ready': True, 'generation_continuity_verified': True,
                    'mark_required': bool(record['parts'].get('mark_required')), 'admission_complete': True,
                    'ticket': ticket.token, 'window_receipts': windows}
        except Exception:
            self.fault = True
            raise
