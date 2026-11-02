"""Durable single-item lifecycle owner. Injected control/runtime drivers only.

START admission and generation continuity must come from the upstream exclusive
owner; this module cannot prove CH0 registration, policy ACKs or peer reset.
It never schedules a device run on import, invents a missing reply, or resumes
an uncertain START. Unmarked by default; a verified coordinator can bind a physically marked trial.
"""
from pathlib import Path
import json
import ch1_evidence_store as store
from ch1_control_session import decode_event,frame
from ch1_runtime_driver import unsigned


class SingleItemOwner:
    def __init__(self,journal,binding,upload,completion):
        self.journal=journal;self.binding=binding;self.upload=upload;self.completion=completion
        self.phase='BOUND';self.fault=False;self.started=False;self.done=False;self.peer_retired=False
        self.retire_sent=False;self.record_id=None;self.notifications={};self.local_retired=False
        self.prepared_inner=bytes(upload.current[2])
        self.business_success=None;self.saved_proof=None
        self.config_success_ack=None
        self.mark_required=False;self.mark_seen=False;self.mark_capture=None;self.mark_receipt=None
        self.journal.record('owner_bound',epoch=binding.epoch,record_id=binding.record_id,
                            identity=binding.identity,kind=binding.kind)
    def _stop(self,exc):
        self.fault=True;self.upload.fault=True
        if not self.journal.fault:
            try:self.journal.record('owner_stop',phase=self.phase,reason=str(exc))
            except Exception:pass # Original failure retained; no further device effects.
    def start(self,peer,runtime,peer_archive,admission,*,minimum_remaining_ticks):
        """Admission is an upstream receipt, never synthesized here.

        Full identity includes expected W19 generation. It must be derived from
        a proven fresh common KEY reset/exclusive START continuity, not H5E1's
        unrelated capture_generation. Actual START_ACCEPT is checked afterward.
        """
        try:
            if self.fault or self.phase!='BOUND':raise RuntimeError('Owner not available for a new START')
            unsigned(minimum_remaining_ticks,64,'remaining hardware budget',1)
            f=store._fields(self.binding.identity,store.IDENTITY)
            if f['route_mode']!=0:raise RuntimeError('This owner stage supports Direct only')
            required={'identity':self.binding.identity,'local_epoch':self.binding.epoch,
                      'peer_epoch':f['route_epoch'],'CH0_registered':True,
                      'STM_expected_flight_registered':True,'policy_ready':True,
                      'generation_continuity_verified':True,'mark_required':False}
            if any(admission.get(k)!=v for k,v in required.items()):raise RuntimeError('Missing exact upstream START prerequisites')
            if not peer_archive.get('peer_store_verified') or (peer_archive.get('epoch'),peer_archive.get('session'),peer_archive.get('seq'))!=(f['route_epoch'],f['session'],f['seq']):
                raise RuntimeError('Peer original frame not saved/confirmed')
            kind,seq,inner,packet=self.upload.current
            if (peer_archive.get('kind'),peer_archive.get('len'),peer_archive.get('crc'))!=(int(kind),len(inner),store.crc16(inner)):
                raise RuntimeError('Peer original receipt fingerprint differs from prepared frame')
            if self.completion.current is None or self.completion.current['binding']['identity']!=self.binding.identity or not self.completion.accepted or self.completion.done:
                raise RuntimeError('No saved exact H1 ACCEPTED')
            if runtime.binding()!=self.binding:raise RuntimeError('Actual runtime binding changed')
            self.journal.record('start_admission',admission=admission,peer_archive=peer_archive)
            window_identity=self.binding.identity & ~(0xffffffff<<88)
            peer.request_event(0x30,window_identity,0)
            snap=runtime.snapshot()
            if snap['epoch']!=self.binding.epoch or snap['tick']<self.binding.start or snap['tick']+minimum_remaining_ticks>=self.binding.deadline:
                raise RuntimeError('Hardware capture window not open with required remaining margin')
            self.journal.record('start_intent',identity=self.binding.identity,hardware_tick=snap['tick'])
            self.phase='START_REQUESTED'
            raw=peer.start(self.binding.identity)
            self.journal.record('start_command_ack',raw_hex=raw.hex(),note='not physical completion')
            self.drain_notifications(peer)
            return {'start_command_ack_saved':True,'physical_start_confirmed':self.started,
                    'physical_done_confirmed':self.done}
        except Exception as exc:self._stop(exc);raise
    def drain_notifications(self,peer,*,prefix_records=None):
        try:
            if self.fault:raise RuntimeError('Owner stopped; inspect retained evidence')
            processed=0;prefix=list(prefix_records or [])
            while peer.events:
                processed+=1
                if processed>peer.limit:raise RuntimeError('Notification drain budget exhausted')
                event=peer.events[0];decoded=decode_event(bytes.fromhex(event['raw_hex']))
                if decoded!=event or event['identity']!=self.binding.identity:raise ValueError('Peer lifecycle identity mismatch')
                typ=event['type'];old=self.notifications.get(typ)
                records=prefix;prefix=[]
                if old is not None:
                    if old!=event:raise ValueError('Changed replay for same lifecycle effect')
                else:
                    if typ==0x31 and self.phase=='START_REQUESTED' and not event['record_id']:effect='START_ACCEPT'
                    elif typ==0x33 and self.mark_required and self.started and not self.done and not event['record_id']:effect='FAULT_MARK'
                    elif typ==0x32 and self.started and (not self.mark_required or self.mark_seen) and not event['record_id']:effect='W19_DONE'
                    elif typ==0x38 and self.retire_sent and self.local_retired and event['record_id']==self.record_id:effect='RETIRED'
                    else:raise ValueError('Out-of-order notification or unsupported fault-mark trial')
                    records=records+[('peer_event_effect',{'effect':effect,'event_receipt':event})]
                ack=frame(typ+0x40,bytes.fromhex(event['payload_hex']))
                records=records+[('control_tx_intent',{'raw_hex':ack.hex()})]
                self.journal.record_many(records) # Effects and exact ACK intent fsynced together.
                if old is None:
                    self.notifications[typ]=dict(event)
                    if typ==0x31:self.started=True;self.phase='STARTED'
                    elif typ==0x33:self.mark_seen=True
                    elif typ==0x32:self.done=True;self.phase='DONE'
                    elif typ==0x38:self.peer_retired=True;self.phase='WAIT_READY'
                self.journal.verify()
                peer.ack_notification(event) # Effect already fsynced; exact tuple ACK.
                peer.events.popleft()
            if prefix:self.journal.record_many(prefix)
        except Exception as exc:self._stop(exc);raise
    def poll_lifecycle(self,peer):
        """Poll delayed actual notifications; silence does not imply completion."""
        try:
            if self.fault:raise RuntimeError('Owner stopped')
            peer.poll_notifications();self.drain_notifications(peer)
            return {'physical_start_confirmed':self.started,'physical_done_confirmed':self.done,
                    'peer_retirement_confirmed':self.peer_retired}
        except Exception as exc:self._stop(exc);raise
    def retire_peer(self,peer,saved):
        try:
            if self.fault or self.phase!='DONE' or not self.done:raise RuntimeError('No saved physical W19 completion')
            completion=self.completion.completion_receipt()
            if completion['binding']['identity']!=self.binding.identity:raise RuntimeError('No matching saved H1 TX_DONE')
            if (saved.get('epoch'),saved.get('record_id'),int(saved.get('identity_hex','0'),16))!=(self.binding.epoch,self.binding.record_id,self.binding.identity):raise ValueError('Wrong CH1 saved record')
            if not saved.get('hardware_retirement_verified') or not saved.get('mapping_retirement_verified'):
                raise RuntimeError('Local actual retirement not confirmed')
            directory=Path(saved['evidence_dir']);manifest=json.loads((directory/'committed.json').read_text())
            if not {'descriptor.bin','samples.bin','raw_packet.bin'}<=set(manifest['files']):raise ValueError('Archive manifest missing raw evidence')
            for name,proof in manifest['files'].items():
                raw=(directory/name).read_bytes()
                if store.sha(raw)!=proof['sha256'] or len(raw)!=proof['bytes']:raise ValueError('CH1 archive altered')
            proof=manifest['confirmation']
            if any(saved.get(k)!=v for k,v in proof.items()):raise ValueError('Archive proof differs from driver receipt')
            descriptor=(directory/'descriptor.bin').read_bytes();samples=(directory/'samples.bin').read_bytes()
            decoded=store.descriptor_decode(descriptor)
            if decoded['kind']!=self.binding.kind or store.crc16(descriptor)!=proof['descriptor_crc'] or store.crc16(samples)!=proof['samples_crc']:
                raise ValueError('Archived kind/fingerprints differ from actual saved proof')
            if (proof['epoch'],proof['record_id'],int(proof['identity_hex'],16))!=(self.binding.epoch,self.binding.record_id,self.binding.identity):raise ValueError('Archive confirmation identity changed')
            business=bool(manifest['classification']['business_success'])
            if business!=saved['business_success']:raise ValueError('Business classification changed')
            self.journal.record('local_record_retired',proof=saved)
            self.completion.mark_local_retired(saved)
            self.business_success=business;self.saved_proof=dict(saved)
            self.local_retired=True;self.record_id=self.binding.record_id
            peer.request_event(0x34,self.binding.identity,self.record_id)
            peer.request_event(0x35,self.binding.identity,self.record_id)
            if self.mark_required:
                if not self.mark_seen or self.mark_capture is None or self.mark_receipt is None:
                    raise RuntimeError('No saved physical mark snapshot; withhold MARK_STORED')
                from ch1_admission_parts import _has_exact_rx
                actual=self.notifications.get(0x33)
                if actual is None or not _has_exact_rx(self.journal,actual['raw_hex']):
                    raise ValueError('Physical mark notification original missing')
                proof=self.mark_capture.verify_saved(self.mark_receipt,self.binding)
                self.journal.record('physical_mark_store_intent',proof=proof)
                self.mark_capture.verify_saved(self.mark_receipt,self.binding)
                peer.request_event(0x36,self.binding.identity,proof['mark_record_id'])
            if self.binding.kind==2:
                if not business:raise RuntimeError('CONFIG failed; no CONFIG_SUCCESS or next item')
                self.config_success_ack=peer.request_event(0x39,self.binding.identity,self.record_id)
            self.journal.record('peer_retire_intent',record_id=self.record_id,identity=self.binding.identity)
            self.retire_sent=True
            peer.request_event(0x37,self.binding.identity,self.record_id)
            self.drain_notifications(peer)
        except Exception as exc:self._stop(exc);raise
    def accept_ready(self,result):
        try:
            if self.fault or not self.peer_retired or not self.local_retired:raise RuntimeError('Both peer and local retirement are required')
            if result.get('state')!=0x80 or result.get('credit')!=1 or not result.get('local_queue_release_verified') or result.get('binding')!=self.completion.current['binding']:
                raise ValueError('READY must be exact saved current-generation credit1')
            key=(self.binding.epoch,result['ticket'])
            if key not in self.completion.tickets or self.completion.tickets[key][1]['raw_hex']!=result['raw_hex']:
                raise ValueError('READY receipt not present in retained completion ledger')
            raw=bytes.fromhex(result['raw_hex'])
            if len(raw)!=18 or raw[3]!=0x80 or raw[15]!=1:
                raise ValueError('Actual saved READY bytes do not grant credit1')
            self.journal.verify();self.completion.verify_journal()
            self.journal.record('next_item_credit_committed',identity=self.binding.identity,ticket=result['ticket'])
            self.upload.record('retired_and_ready',seq=self.completion.current['seq'],identity=self.binding.identity,
                               local_record_id=self.binding.record_id,ready_ticket=result['ticket'])
            self.completion.record('retired_and_ready',record_id=self.binding.record_id,ready_ticket=result['ticket'])
            self.upload.seq=self.completion.current['seq'];self.upload.current=None;self.upload.credit=1
            self.upload.accepted=False;self.upload.done=False;self.upload.transport_offered=False
            self.completion.current=None;self.completion.receipt=None;self.completion.accepted=False;self.completion.done=False
            self.phase='RETIRED'
            return {'next_item_allowed':True,'last_seq':self.upload.seq}
        except Exception as exc:self._stop(exc);raise
