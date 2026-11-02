"""Sequential Direct image attempt bookkeeping; received bytes alone reconstruct.

No device I/O or automatic retry. trial_registry must be shared across sessions
and retained; crash resume is intentionally refused. Source is used for request
generation/comparison, never to fill missing/corrupted received image pixels.
"""
from pathlib import Path
import ch1_evidence_store as store
from ch1_peer_archive_driver import persist_exact
from ch1_control_session import ApplicationJournal
from ch1_completion_ledger import _codec
from ch1_runtime_driver import unsigned


class ImageAttemptLedger:
    def __init__(self,root,source,config,*,epoch,trial_registry):
        self.root=Path(root);self.source=bytes(source);self.config=bytes(config)
        self.codec=_codec();self.cfg=self.codec.decode_config(self.config)
        if not self.cfg['valid'] or self.cfg['total_bytes']!=len(self.source) or self.cfg['sha256'].hex()!=store.sha(self.source):
            raise ValueError('Frozen source/config mismatch')
        self.chunks=[self.source[i:i+self.cfg['chunk_size']] for i in range(0,len(self.source),self.cfg['chunk_size'])]
        if [store.crc16(x) for x in self.chunks]!=self.cfg['item_crc_list']:raise ValueError('Frozen item CRC table mismatch')
        self.journal=ApplicationJournal(self.root/'ledger',epoch)
        persist_exact(self.root/'source',{'source.bin':self.source,'config.bin':self.config})
        self.registry=Path(trial_registry);self.registry.mkdir(parents=True,exist_ok=True)
        self.configured=False;self.pending=None;self.received={};self.attempts={};self.fault=False
    def _gate(self,owner):
        if self.fault or owner.fault or owner.phase!='RETIRED' or owner.completion.current is not None or owner.upload.credit!=1:
            raise RuntimeError('Previous exact retirement and READY credit required')
        owner.journal.verify();self.journal.verify()
    def accept_config(self,owner):
        self._gate(owner)
        if owner.binding.kind!=2 or owner.business_success is not True or owner.prepared_inner!=self.config:
            raise ValueError('Exact CONFIG not acknowledged as business success')
        self.journal.record('configuration_success',identity=owner.binding.identity)
        self.configured=True
    def prepare_item(self,index,attempt,trial_id,previous_owner):
        self._gate(previous_owner)
        unsigned(index,16,'item index');unsigned(attempt,8,'attempt');unsigned(trial_id,16,'trial ID',1)
        if not self.configured or self.pending is not None or index>=len(self.chunks) or attempt>3 or index in self.received:
            raise RuntimeError('Item not eligible for a new attempt')
        if attempt!=self.attempts.get(index,-1)+1:raise ValueError('Attempt must increment from zero, without reuse')
        if attempt==0 and index!=len(self.attempts):raise ValueError('First pass must be sequential')
        pending={'index':index,'attempt':attempt,'trial_id':trial_id}
        # Exclusive creation permanently burns trial ID before any offer.
        store._write(self.registry/f'trial_{trial_id:04x}.json',store._json({**pending,'epoch':previous_owner.binding.epoch}))
        store._sync_directory(self.registry)
        inner=self.codec.encode_item(self.cfg['run_id'],self.cfg['image_id'],trial_id,index,len(self.chunks),attempt,0,self.chunks[index])
        self.journal.record('image_attempt_prepared',**pending,inner_hex=inner.hex(),inner_sha256=store.sha(inner))
        self.pending={**pending,'inner':inner};return inner
    def record_attempt(self,owner):
        try:
            self._gate(owner)
            if self.pending is None or owner.binding.kind!=1 or owner.prepared_inner!=self.pending['inner'] or owner.saved_proof is None:
                raise ValueError('Retired item differs from immutable attempt')
            path=Path(owner.saved_proof['evidence_dir'])
            import json
            manifest=json.loads((path/'committed.json').read_text())
            if not {'raw_packet.bin','descriptor.bin','samples.bin'}<=set(manifest['files']):raise ValueError('Missing full image evidence files')
            for name,entry in manifest['files'].items():
                raw_file=(path/name).read_bytes()
                if store.sha(raw_file)!=entry['sha256'] or len(raw_file)!=entry['bytes']:raise ValueError('Image evidence changed')
            descriptor=store.descriptor_decode((path/'descriptor.bin').read_bytes())
            if (descriptor['epoch'],descriptor['record_id'],descriptor['identity'])!=(owner.binding.epoch,owner.binding.record_id,owner.binding.identity):
                raise ValueError('Image archive binding differs from retired owner')
            raw=(path/'raw_packet.bin').read_bytes();decoded=self.codec.decode_report(raw)
            p=self.pending;f=store._fields(owner.binding.identity,store.IDENTITY)
            if (f['run_id'],f['image_id'],f['trial_id'],f['item_index'],f['attempt_id'],f['route_mode'])!=(self.cfg['run_id'],self.cfg['image_id'],p['trial_id'],p['index'],p['attempt'],0):
                raise ValueError('Prepared item metadata and owner identity differ')
            keys=('run_id','image_id','trial_id','item_index','attempt_id','route_mode')
            ok=(owner.business_success is True and manifest['classification']['business_success'] is True and decoded.get('valid') and
                all(decoded.get(k)==f[k] for k in keys) and decoded['result_status']==0 and decoded['uart_flags']==0 and decoded['recvd_data']==self.chunks[p['index']])
            self.journal.record('image_attempt_result',index=p['index'],attempt=p['attempt'],trial_id=p['trial_id'],
                business_success=bool(ok),evidence_dir=str(path),actual_raw_sha256=store.sha(raw))
            self.attempts[p['index']]=p['attempt']
            if ok:self.received[p['index']]=bytes(decoded['recvd_data'])
            self.pending=None
            return {'business_success':bool(ok),'items_verified':len(self.received),'items_total':len(self.chunks)}
        except Exception:self.fault=True;raise
    def reconstruct(self):
        self.journal.verify()
        if self.fault or self.pending is not None or len(self.received)!=len(self.chunks):raise RuntimeError('Image incomplete; missing pixels are not replaced')
        actual=b''.join(self.received[i] for i in range(len(self.chunks)))
        if store.sha(actual)!=self.cfg['sha256'].hex():raise ValueError('Received whole-image SHA mismatch')
        persist_exact(self.root/'received',{'received.bin':actual})
        self.journal.record('received_image_verified',received_sha256=store.sha(actual),items=len(self.chunks))
        return {'received_path':str(self.root/'received/received.bin'),'sha256':store.sha(actual),'items':len(self.chunks)}
    def close(self):self.journal.close()
