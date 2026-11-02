"""Durable association of H1T1 raw status to one immutable CH1 binding.

This produces a SOFTWARE receipt, not an RTL physical_done pulse. Requires
exclusive ownership and a shared durable root whose session reservations are
never discarded. No reopen/resume, reset, START or automatic retransmit API.
"""
from dataclasses import asdict
from pathlib import Path
import importlib.util
import json
import os
import struct
import sys
from functools import lru_cache
import ch1_evidence_store as store
from ch1_runtime_driver import unsigned


@lru_cache(maxsize=1)
def _codec():
    path = Path(__file__).resolve().parents[1]/'reference/reference_codec.py'
    spec = importlib.util.spec_from_file_location('ch1_completion_reference', path)
    module = importlib.util.module_from_spec(spec)
    # The frozen reference imports its sibling queue_model.
    sys.path.insert(0,str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module.ImagePacketCodec


class CompletionLedger:
    def __init__(self, root, *, local_epoch, peer_epoch, session):
        self.local_epoch = unsigned(local_epoch, 32, 'local_epoch', 1)
        self.peer_epoch = unsigned(peer_epoch, 32, 'peer_epoch', 1)
        self.session = unsigned(session, 32, 'session', 1)
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        # Session is absent from the wire's epoch namespace. Reuse cannot be safe.
        store._write(self.root/f'used_session_{session:08x}.json', store._json({
            'local_epoch':local_epoch, 'peer_epoch':peer_epoch, 'session':session}))
        store._sync_directory(self.root)
        self.path = self.root/f'completion_{local_epoch:08x}.jsonl'
        self.file = self.path.open('x', encoding='utf-8')
        self.chain = '0'*64; self.records = 0; self.fault = False
        self.current = None; self.accepted = False; self.done = False
        self.last_seq = 0; self.tickets = {}; self.receipt = None
        self.local_retired = False
        self.record('begin', local_epoch=local_epoch, peer_epoch=peer_epoch, session=session,
                    scope='software completion association only; not hardware physical_done')

    def record(self, event, **fields):
        item = {'index':self.records, 'previous_sha256':self.chain, 'event':event, **fields}
        digest = store.sha(store._json(item))
        try:
            self.file.write(json.dumps({**item, 'sha256':digest}, sort_keys=True)+'\n')
            self.file.flush(); os.fsync(self.file.fileno())
        except Exception:
            self.fault = True
            raise
        self.chain = digest; self.records += 1
        return digest

    def bind(self, binding, inner):
        if self.fault or self.current is not None:
            raise RuntimeError('Outstanding binding or locked ledger')
        unsigned(binding.epoch,32,'binding epoch',1)
        unsigned(binding.record_id,32,'record_id',1)
        unsigned(binding.kind,2,'kind',1)
        unsigned(binding.start,64,'start'); unsigned(binding.deadline,64,'deadline',1)
        identity = store._fields(unsigned(binding.identity,256,'identity'), store.IDENTITY)
        if identity['reserved'] or identity['session'] != self.session or identity['route_epoch'] != self.peer_epoch or identity['seq'] <= self.last_seq or identity['seq'] == 0xffffffff or not identity['generation'] or identity['route_mode'] > 1:
            raise ValueError('Binding identity/peer namespace does not match ledger')
        if binding.epoch != self.local_epoch or not binding.record_id or not binding.start < binding.deadline:
            raise ValueError('Binding local epoch/record/window invalid')
        inner = bytes(inner)
        codec = _codec()
        decoder = {1:codec.decode_item, 2:codec.decode_config, 3:codec.decode_cleanup}.get(binding.kind)
        if decoder is None:
            raise ValueError('Invalid CH1 binding kind')
        decoded = decoder(inner)
        keys = ('run_id','image_id','trial_id','item_index','attempt_id','route_mode') if binding.kind == 1 else ('run_id','image_id')
        if not decoded['valid'] or any(decoded[key] != identity[key] for key in keys):
            raise ValueError('Prepared inner frame differs from complete CH1 identity')
        wire_kind = {1:3, 2:2, 3:4}[binding.kind]
        body = struct.pack('>BBIIH', 1, wire_kind, self.session, identity['seq'], len(inner))+inner
        packet = b'\xa6\x69'+body+store.crc16(body).to_bytes(2,'big')
        current = {'binding':asdict(binding), 'seq':identity['seq'], 'inner_crc':store.crc16(inner),
                   'inner_sha256':store.sha(inner), 'outer_sha256':store.sha(packet)}
        self.record('binding_prepared', **current, inner_hex=inner.hex(), outer_hex=packet.hex())
        self.current = current; self.last_seq = identity['seq']
        self.accepted = False; self.done = False; self.receipt = None
        self.local_retired = False
        return packet

    def observe_snapshot(self, *, source_epoch, ticket, meta, packed):
        """Accept exact 7-DWORD snapshot, persist raw before any semantic result.

        source_epoch is locally attested by exclusive transport owner, NOT a
        wire field. Reserved session and monotonically used seq prevent aliasing.
        Invalid events lock the ledger and remain held at the transport endpoint.
        """
        if self.fault:
            raise RuntimeError('Locked completion ledger; evidence must remain held')
        packed = bytes(packed)
        fields = {'source_epoch':source_epoch, 'ticket':ticket, 'meta':meta, 'packed_hex':packed.hex()}
        self.record('snapshot_raw', **fields)
        try:
            unsigned(source_epoch,32,'source_epoch',1); unsigned(ticket,32,'ticket',1)
            unsigned(meta,32,'meta')
            if source_epoch != self.local_epoch or self.current is None:
                raise ValueError('Wrong local transport namespace or no bound record')
            key = (source_epoch,ticket)
            fingerprint = (meta,packed)
            if key in self.tickets:
                old, result = self.tickets[key]
                if old != fingerprint or result['binding'] != self.current['binding']:
                    raise ValueError('Same snapshot ticket changed its raw evidence')
                self.record('snapshot_retry', ticket=ticket)
                return {**result, 'new_completion':False}
            if self.tickets and ticket <= max(t for e,t in self.tickets):
                raise ValueError('Snapshot ticket regressed or reused')
            if len(packed) != 20 or packed[18:] != b'\0\0' or meta != 0x112:
                raise ValueError('Malformed/partial/UART-error status or nonzero padding')
            raw = packed[:18]
            if raw[:2] != b'\xa6\x6a' or store.crc16(raw[2:16]) != int.from_bytes(raw[16:],'big'):
                raise ValueError('Status SOF/CRC mismatch')
            version,state,session,seq,crc,code,credit = struct.unpack('>BBIIHBB', raw[2:16])
            if version != 1 or state not in (0x80,0x81,0x82,0x83) or code > 8 or credit > 1 or (state != 0x82 and code):
                raise ValueError('Invalid status fields')
            session_ready=(state==0x80 and session==self.session and seq==0 and crc==0)
            if session_ready and not (self.done and self.local_retired):
                raise ValueError('Session READY before saved TX_DONE and exact actual local retirement')
            if not session_ready and (session,seq,crc) != (self.session,self.current['seq'],self.current['inner_crc']):
                raise ValueError('Status does not match immutable prepared frame')
            if state == 0x82:
                raise ValueError(f'Peer rejected prepared frame (code {code})')
            if state == 0x81 and self.done:
                raise ValueError('Status regressed after TX_DONE')
            if state == 0x83 and not self.accepted:
                raise ValueError('TX_DONE before saved ACCEPTED')
            new_done = state == 0x83 and not self.done
            digest = self.record('status_matched', ticket=ticket, state=state, credit=credit,
                                 new_completion=new_done, raw_hex=raw.hex(), **self.current)
            result = {'state':state, 'new_completion':new_done,
                      'completion_seen':self.done or new_done, 'journal_sha256':digest,
                      'credit':credit,'ticket':ticket,'raw_hex':raw.hex(),
                      'binding':dict(self.current['binding'])}
            result['session_ready']=session_ready
            self.tickets[key] = (fingerprint,result)
            if state == 0x81: self.accepted = True
            if new_done:
                self.done = True
                self.receipt = {**self.current, 'local_epoch':self.local_epoch, 'peer_epoch':self.peer_epoch,
                    'session':self.session, 'ticket':ticket, 'raw_hex':raw.hex(), 'journal_sha256':digest,
                    'hardware_physical_done_published':False}
            return result
        except Exception as exc:
            self.fault = True
            self.record('fault', reason=str(exc))
            raise

    def completion_receipt(self):
        if self.fault or self.receipt is None:
            raise RuntimeError('No qualified saved completion receipt')
        self.verify_journal()
        # Return a deep copy; callers cannot mutate retained identity.
        return json.loads(json.dumps(self.receipt))

    def mark_local_retired(self,proof):
        if self.fault or not self.done or self.current is None:
            raise RuntimeError('No saved completion for actual retirement')
        b=self.current['binding']
        if not proof.get('hardware_retirement_verified') or not proof.get('mapping_retirement_verified') or (proof.get('epoch'),proof.get('record_id'),int(proof.get('identity_hex','0'),16))!=(b['epoch'],b['record_id'],b['identity']):
            raise ValueError('Local retirement proof differs from retained binding')
        self.record('actual_local_retirement',epoch=b['epoch'],record_id=b['record_id'],identity=b['identity'])
        self.local_retired=True

    def verify_journal(self):
        chain = '0'*64; count = 0
        try:
            for line in self.path.read_text(encoding='utf-8').splitlines():
                record = json.loads(line); digest = record.pop('sha256')
                if record['index'] != count or record['previous_sha256'] != chain or store.sha(store._json(record)) != digest:
                    raise ValueError('Completion journal changed')
                chain = digest; count += 1
            if (chain,count) != (self.chain,self.records):
                raise ValueError('Completion journal truncated/replaced')
        except Exception:
            self.fault = True
            raise

    def close(self):
        self.file.close()


class H1CompletionReader:
    """Preserve/qualify H1T1 snapshot before explicit local queue release.

    No callback publishes physical_done; a future hardware bridge must consume
    the real saved-snapshot handshake with this immutable mapping.
    """
    def __init__(self, mmio, ledger):
        self.bus = mmio; self.ledger = ledger
        self.upload = None
        if self._read(0) != 0x48315431:
            raise RuntimeError('Requires H1T1; no writes performed')

    def _read(self, a):
        return unsigned(self.bus.read(a),32,'transport DWORD')

    def bind(self, binding, inner):
        if self._read(4) & 0x7e:
            raise RuntimeError('Transport must be idle with no old RX evidence before binding')
        return self.ledger.bind(binding,inner)

    def bind_prepared(self, binding, upload_ledger):
        """Join the existing durable UploadLedger without launching anything."""
        current = upload_ledger.current
        if upload_ledger.fault or current is None or upload_ledger.transport_offered:
            raise RuntimeError('A durable unoffered upload is required before binding')
        kind,seq,inner,packet = current
        identity = store._fields(binding.identity,store.IDENTITY)
        if (upload_ledger.session,seq,int(kind)) != (self.ledger.session,identity['seq'],{1:3,2:2,3:4}.get(binding.kind)):
            raise ValueError('Prepared upload differs from CH1 binding')
        prepared = self.bind(binding,inner)
        if prepared != packet:
            self.ledger.fault = True
            raise ValueError('Durable upload bytes differ from completion mapping')
        self.upload = upload_ledger
        return prepared

    def read_and_preserve(self):
        flags = self._read(4)
        if flags & 0x60:
            self.ledger.fault = True
            raise RuntimeError('Transport fault; evidence held, no completion authorization')
        if not flags & 8: return None
        if not flags & 16:
            self.bus.write(0x30,1)
        if not self._read(4) & 16:
            raise RuntimeError('Snapshot command not accepted')
        ticket = self._read(0x40); meta = self._read(0x44)
        packed = b''.join(self._read(a).to_bytes(4,'big') for a in (0x48,0x4c,0x50,0x54,0x58))
        result = self.ledger.observe_snapshot(source_epoch=self.ledger.local_epoch,
            ticket=ticket, meta=meta, packed=packed)
        if self.upload is not None:
            try:
                if result.get('session_ready'):
                    # Legacy UploadLedger's seq-bound observe is intentionally unchanged.
                    # Preserve the actual session advisory; only owner unlocks credit.
                    self.upload.record('status_raw',raw_hex=packed[:18].hex())
                    self.upload.record('retired_session_ready_advisory',credit=result['credit'],ticket=ticket)
                else:self.upload.observe(packed[:18])
                if self.upload.fault:
                    raise RuntimeError('Upload ledger rejected completion status')
            except Exception:
                self.ledger.fault = True
                raise
        if self._read(0x5c) != 127 or self._read(4) & 0x60:
            self.ledger.fault = True
            raise RuntimeError('Missing delivered reads or transport fault; no queue release')
        self.ledger.verify_journal()
        self.bus.write(0x34,ticket)
        if self._read(4) & 16:
            raise RuntimeError('Saved local queue release unconfirmed; held snapshot may be retried')
        self.ledger.record('local_queue_released', ticket=ticket,
                           note='not peer retirement and not RTL physical_done')
        return {**result,'local_queue_release_verified':True}
