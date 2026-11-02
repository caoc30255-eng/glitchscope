"""Strict ticket START entry over the existing retained lifecycle owner.

Old flag-injection start API is blocked on this subclass. No automatic retries,
resource release or uncertain START resume. Physical events still require the
old owner's exact durable event handling and later CH1/peer retirement.
"""
import ch1_evidence_store as store
from pathlib import Path
import json
from ch1_item_owner import SingleItemOwner
from ch1_runtime_driver import unsigned


class VerifiedSingleItemOwner(SingleItemOwner):
    def start(self, *args, **kwargs):
        raise RuntimeError('Use start_verified with a coordinator-issued ticket')

    def start_verified(self, peer, coordinator, ticket, *, ch0_margin_ticks, ch1_margin_ticks):
        try:
            if self.fault or self.phase != 'BOUND':
                raise RuntimeError('Owner unavailable for START')
            unsigned(ch0_margin_ticks, 64, 'CH0 margin', 1)
            unsigned(ch1_margin_ticks, 64, 'CH1 margin', 1)
            if not callable(getattr(peer,'start_checked',None)):
                raise RuntimeError('Peer session with post-fsync local guard required')
            record = coordinator._ticket(ticket)
            if coordinator.peer is not peer or record['binding'] != self.binding or record['upload'] is not self.upload or record['completion'] is not self.completion:
                raise RuntimeError('Ticket source/owner identity mismatch before WINDOW')
            self.mark_required=bool(record['parts'].get('mark_required'))
            if self.mark_required:
                self.mark_capture=record['mark_capture']
                self.mark_capture.verify_armed(self.binding)
            fields = store._fields(self.binding.identity, store.IDENTITY)
            if fields['route_mode'] != 0:
                raise RuntimeError('Direct mode required')
            window_identity = self.binding.identity & ~(0xffffffff << 88)
            peer.request_event(0x30, window_identity, 0)
            # Verify both windows after the real WINDOW exchange, burn/fsync,
            # then recheck live peer and remaining local clocks before START.
            admission = coordinator.claim(ticket, self, ch0_margin=ch0_margin_ticks, ch1_margin=ch1_margin_ticks)
            self.verified_coordinator = coordinator
            self.verified_record = record
            self.journal.record('verified_start_intent',admission=admission)
            # Account for the intent fsync too; local reads do not consume remote
            # UART traffic budget. Exclusive host control remains required.
            coordinator._local_windows(record, ch0_margin_ticks, ch1_margin_ticks)
            self.phase = 'START_REQUESTED'
            raw = peer.start_checked(self.binding.identity,
                lambda: coordinator._local_windows(record, ch0_margin_ticks, ch1_margin_ticks))
            self.drain_notifications(peer,prefix_records=[('start_command_ack',
                {'raw_hex':raw.hex(),'note':'not physical completion'})])
            return {'start_command_ack_saved': True, 'physical_start_confirmed': self.started,
                    'physical_done_confirmed': self.done, 'admission_ticket': ticket.token}
        except Exception as exc:
            self._stop(exc)
            raise

    def retire_peer(self, *args, **kwargs):
        raise RuntimeError('Use retire_verified: actual CH0/CH1 drivers required')

    def accept_ready(self, *args, **kwargs):
        raise RuntimeError('Use accept_ready_verified: actual saved READY reader required')

    def retire_verified(self, peer, *, ch0_archive, mapping, reader, archive):
        """Perform local save/retire, then exact peer retirement; no automatic retry."""
        from ch0_archive_driver import CH0ArchiveDriver
        from ch1_mapping_driver import CH1MappingDriver
        from ch1_runtime_driver import CH1RuntimeDriver
        from ch1_completion_ledger import H1CompletionReader, _codec
        from ch1_axi_archive_driver import CH1ArchiveDriver
        try:
            coordinator = getattr(self, 'verified_coordinator', None)
            record = getattr(self, 'verified_record', None)
            if self.fault or self.phase != 'DONE' or not self.done or coordinator is None or coordinator.fault:
                raise RuntimeError('No completed strict START flight')
            if getattr(self, 'strict_retire_attempted', False):
                raise RuntimeError('Uncertain strict retirement cannot be retried')
            if bytes(self.prepared_inner) != record['prepared'][2]:
                raise ValueError('Owner original request changed after START')
            if (peer is not coordinator.peer or ch0_archive.registration is not coordinator.ch0 or
                reader.ledger is not self.completion or reader.upload is not self.upload or
                not isinstance(ch0_archive, CH0ArchiveDriver) or not isinstance(mapping, CH1MappingDriver) or
                not isinstance(coordinator.runtime, CH1RuntimeDriver) or not isinstance(reader, H1CompletionReader) or
                not isinstance(archive, CH1ArchiveDriver)):
                raise RuntimeError('Retirement drivers differ from strict flight sources')
            runtime = coordinator.runtime
            if runtime.binding() != self.binding or mapping.status() & 3 != 2 or mapping.expected != mapping.mapping():
                raise RuntimeError('Actual runtime/mapping no longer holds exact flight')
            expected = mapping.expected
            if expected is None or (expected['epoch'], expected['record_id'], expected['identity'], expected['inner_crc']) != (
                self.binding.epoch, self.binding.record_id, self.binding.identity, store.crc16(self.prepared_inner)):
                raise RuntimeError('Mapping differs from original request')
            completion = self.completion.completion_receipt()
            prepared = record['prepared']
            fingerprints = {'seq': prepared[1], 'inner_crc': store.crc16(prepared[2]),
                            'inner_sha256': store.sha(prepared[2]), 'outer_sha256': store.sha(prepared[3])}
            if not self.completion.done or not self.completion.accepted or self.upload.fault or any(
                completion.get(key) != value or self.completion.current.get(key) != value
                for key, value in fingerprints.items()):
                raise ValueError('Saved completion fingerprint differs from original flight')
            if completion['binding'] != record['completion'].current['binding'] or completion['binding'] != {
                'epoch':self.binding.epoch, 'record_id':self.binding.record_id, 'kind':self.binding.kind,
                'identity':self.binding.identity, 'start':self.binding.start, 'deadline':self.binding.deadline}:
                raise RuntimeError('No complete saved matching H1 TX_DONE')
            self.journal.verify()
            self.completion.verify_journal()
            coordinator._files(record['directory'])
            coordinator._files(record['parts']['flight_dir'])
            if (int(self.upload.current[0]), self.upload.current[1], bytes(self.upload.current[2]), bytes(self.upload.current[3])) != record['prepared']:
                raise ValueError('Prepared original changed after START')
            self.strict_retire_attempted = True
            if self.mark_required:
                if not self.mark_seen:raise RuntimeError('No actual FAULT_MARK notification')
                self.mark_receipt=self.mark_capture.archive(self.binding,self.notifications[0x33])
                self.mark_capture.verify_saved(self.mark_receipt,self.binding)
            self.journal.record('strict_three_party_retire_intent',identity=self.binding.identity,record_id=self.binding.record_id)
            receipt = ch0_archive.archive_current(record['ch0_binding'], expected_request=self.prepared_inner)
            self.strict_ch0_release = ch0_archive.release_saved(receipt)
            ch0_archive.verify_release(self.strict_ch0_release)
            self.journal.record('strict_CH0_released',proof=self.strict_ch0_release)
            if runtime.system_gate is not None:
                runtime.system_gate.bind_ch0_release(ch0_archive, self.strict_ch0_release, self.binding)
            payload = _codec().decode_item(self.prepared_inner)['payload'] if self.binding.kind == 1 else None
            saved = mapping.archive_and_retire(runtime, reader, archive, expected_payload=payload)
            ch0_archive.verify_release(self.strict_ch0_release)
            self.strict_sources = (ch0_archive, mapping, runtime, reader)
            self.strict_saved = saved
            self.strict_ch1_manifest = (Path(saved['evidence_dir'])/'committed.json').read_bytes()
            # The base method validates the CH1 archive and saved physical events,
            # fsyncs their effects, then sends peer STORE/LOCAL/RETIRE commands.
            self._strict_local_recheck()
            SingleItemOwner.retire_peer(self, peer, saved)
            return {'CH0_release_verified': True, 'CH1_retirement_verified': True,
                    'peer_retirement_verified': self.peer_retired, 'next_item_allowed': False}
        except Exception as exc:
            self._stop(exc)
            raise

    def accept_ready_verified(self, reader):
        """Read actual H1 READY and authorize credit only after all three retirements."""
        try:
            if self.fault or self.phase == 'RETIRED' or not self.peer_retired or not self.local_retired or not hasattr(self, 'strict_sources'):
                raise RuntimeError('Strict three-party retirement incomplete')
            ch0, mapping, runtime, bound_reader = self.strict_sources
            if reader is not bound_reader:
                raise RuntimeError('READY reader differs from saved completion source')
            self._strict_local_recheck()
            result = reader.read_and_preserve()
            if result is None:
                return {'next_item_allowed': False, 'waiting_for_actual_READY': True}
            self._strict_local_recheck()
            if reader._read(4) & 0x7e:
                raise RuntimeError('H1 transport still busy/queued/faulted after READY; no credit')
            return SingleItemOwner.accept_ready(self, result)
        except Exception as exc:
            self._stop(exc)
            raise

    def _strict_local_recheck(self):
        ch0, mapping, runtime, reader = self.strict_sources
        if self.mark_required:self.mark_capture.verify_saved(self.mark_receipt,self.binding)
        ch0.verify_release(self.strict_ch0_release)
        directory = Path(self.strict_saved['evidence_dir'])
        raw = (directory/'committed.json').read_bytes()
        if raw != self.strict_ch1_manifest:
            raise ValueError('CH1 saved manifest changed during retirement')
        for name, info in json.loads(raw)['files'].items():
            data = (directory/name).read_bytes()
            if store.sha(data) != info['sha256'] or len(data) != info['bytes']:
                raise ValueError('CH1 saved original changed during retirement')
        if runtime.status() & (2 | 4 | 32 | 64 | 256) or runtime._read(8) != self.binding.epoch or runtime._read(0x24) != self.strict_saved['retire_count']:
            raise RuntimeError('CH1 actual retired state/count changed')
        if mapping.status() & 3 or mapping.read(8) != self.binding.epoch or (mapping.read(0x18)-mapping.retire_before) & 0xffffffff != 1:
            raise RuntimeError('Mapping actual retired state/count changed')
