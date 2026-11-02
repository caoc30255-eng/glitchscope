"""Local fixed-rule feedback loop over the reviewed bounded v0.2 executor.

No board IO on import. No learning, arbitrary parameter selection, retry, reset
or recovery API. Policy can continue the next sealed slot or stop, at most four
records including CONFIG/control. Executor retains all live START authority.
"""
from pathlib import Path
import copy,json,threading
from controlled_trial_executor import ControlledTrialExecutor
from ps_idle_journal_segments import _idle,verify_sealed_segments
from raw_mark_snapshot import _same_session_buses,analyze_waveform
from ch1_completion_ledger import _codec
from ch0_archive_driver import CH0ArchiveDriver
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store


def _require(ok,reason):
    if not ok:raise RuntimeError(reason)

class ScanFeedback:
    def __init__(self,executor):
        self.executor=executor;self.session=executor.session

    def _verify_directory(self,directory):
        directory=Path(directory)
        raw=(directory/'committed.json').read_bytes();manifest=json.loads(raw)
        for name,proof in manifest['files'].items():
            path=(directory/name).resolve()
            _require(directory.resolve() in path.parents,'Archive path escaped directory')
            data=path.read_bytes();expected=proof if isinstance(proof,str) else proof['sha256']
            _require(store.sha(data)==expected,'Saved original SHA mismatch')
            if isinstance(proof,dict):_require(len(data)==proof['bytes'],'Saved original length mismatch')
        return manifest

    def _feedback(self,rid):
        ex=self.executor;suffix='epoch_%08x_record_%08x'%(self.session.local_epoch,rid)
        result_dir=ex.root/('record_%08x/result'%rid)
        self._verify_directory(result_dir);raw=(result_dir/'result.json').read_bytes();result=json.loads(raw)
        _require(raw==store._json(ex.results[rid-1]),'Saved/in-memory result differs')
        _require(result['record_id']==rid and result['evidence_quality']=='VALID','Invalid or old record feedback')
        _require(all(result['retirement'][k] is True for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')),'Incomplete strict retirement')
        _require(result['next_credit']['next_item_allowed'] is True and result['next_credit']['last_seq']==rid,'Saved actual READY differs')
        _require(result['next_trial_allowed_by_plan']==(rid<12),'Plan credit differs')
        zero=self.session.root/'CH0'/suffix;one=self.session.root/'CH1/main'/suffix
        _require(Path(result['CH0_evidence_dir']).resolve()==zero.resolve() and Path(result['CH1_evidence_dir']).resolve()==one.resolve(),'Evidence path belongs to another session')
        self._verify_directory(zero);manifest=self._verify_directory(one)
        request=(zero/'expected_request.bin').read_bytes()
        intent_dir=ex.root/('record_%08x/intent'%rid);self._verify_directory(intent_dir)
        _require((intent_dir/'request.bin').read_bytes()==request,'Saved intent request differs')
        descriptor=store.descriptor_decode((one/'descriptor.bin').read_bytes())
        packed=(one/'samples.bin').read_bytes();samples=store.samples_decode(packed,descriptor)
        report=(one/'raw_packet.bin').read_bytes()
        _require(bytes(s['data'] for s in samples)==report,'Actual report samples differ')
        _require(descriptor['epoch']==self.session.local_epoch and descriptor['record_id']==rid and descriptor['identity']==int(result['identity_hex'],16),'Full feedback binding differs')
        decoded=(_codec().decode_config(request) if rid==1 else _codec().decode_item(request))
        _require(decoded['valid'],'Saved source protocol invalid')
        payload=None if rid==1 else ex.parts[rid-2]
        if rid==1:_require(request==ex._frozen_config,'CONFIG source differs from frozen plan')
        else:
            expected_request=_codec().encode_item(self.session.local_epoch,1,result['trial_id'],rid-2,11,0,0,payload)
            _require(request==expected_request,'Exact ITEM source differs from frozen plan/identity')
        fields=store._fields(descriptor['identity'],store.IDENTITY)
        _require(all(decoded.get(k,0)==fields[k] for k in ('run_id','image_id','trial_id','item_index','attempt_id','route_mode')),'Request and full binding differ')
        classification=store.classify(report,descriptor,samples,payload)
        _require(classification==manifest['classification']==result['CH1_classification'],'STM classification differs from originals')
        _require(all(classification[k] is True for k in ('capture_valid','raw_frame_crc_and_format_valid','wire_identity_match')),'Report not valid evidence')
        _require(classification['business_success']==result['STM_business_success'],'B success must not replace STM classification')
        metadata=json.loads((zero/'descriptor.json').read_bytes());binding=metadata['binding']
        _require(metadata['status']==3 and metadata['first_fault']==0,'CH0 has unresolved capture fault')
        _require(binding['identity']==descriptor['identity'] and binding['record_id']==rid and binding['epoch']==self.session.local_epoch,'CH0 binding differs')
        lanes={}
        for lane in ('a','b'):
            lane_samples=CH0ArchiveDriver._decode((zero/(lane+'_samples.bin')).read_bytes(),binding)
            received=bytes(s['data'] for s in lane_samples)
            _require(received==(zero/(lane+'_raw.bin')).read_bytes(),'CH0 samples/raw differ')
            lanes[lane]=received==request and metadata[lane+'_errors']==0 and not any(s['flags'] for s in lane_samples)
            _require(lanes[lane]==result['receiver_'+lane.upper()+'_frame_correct'],'B/A feedback label differs from originals')
        admission=self.session.root/'admission'/suffix;self._verify_directory(admission)
        admission_data=json.loads((admission/'admission.json').read_bytes());applied=admission_data['profile']
        _require(admission_data['context']=={'epoch':self.session.local_epoch,'identity':descriptor['identity'],
                                           'kind':descriptor['kind'],'record_id':rid},'Admission belongs to another record')
        expected={'d':3 if rid==1 else ex.requests[rid-2].d,'s':-1}
        _require(result['actual_receiver_B']==applied and result['requested_receiver_B']==expected and applied['RX_profile_verified'] is True and applied['profile_seq']==rid,'Actual profile differs')
        _require({k:applied[k] for k in ('d','s')}==expected,'Old/mismatched profile readback')
        if rid>=4:
            directory=self.session.root/'MARK'/suffix/'saved';self._verify_directory(directory)
            ctx=json.loads((directory/'context.json').read_bytes())
            wave=(directory/'samples.bin').read_bytes()
            _require(ctx['binding']=={'epoch':self.session.local_epoch,'identity':descriptor['identity'],'record_id':rid},'Waveform binding differs')
            _require(ctx['arm']['source_sha256']==store.sha(request) and ctx['arm']['profile']==ex.requests[rid-2].validate(request)['fault'],'Waveform source/profile differs')
            _require(ctx['analysis']==analyze_waveform(wave,2048,(request[20]&1),ex.requests[rid-2].fault.width),'Physical waveform analysis differs')
            self._verify_directory(directory.parent/'retired_for_next')
            retired=json.loads((directory.parent/'retired_for_next/retired.json').read_bytes())
            _require(retired['old_manifest_sha256']==store.sha((directory/'committed.json').read_bytes()) and
                     retired['proof']['identity']==descriptor['identity'] and retired['proof']['mark_record_id']==rid and
                     retired['actual_READY_consumed'] is True and retired['three_party_retired'] is True and
                     retired['soft_reset_allowed'] is False,'Snapshot retirement seal differs')
            from ch1_control_session import decode_event
            mark=ctx['mark_event']
            _require(decode_event(bytes.fromhex(mark['raw_hex']))==mark and mark['type']==0x33 and
                     mark['identity']==descriptor['identity'] and mark['record_id']==0,'Actual FAULT_MARK identity differs')
            if rid>=5:
                old=self.session.root/'MARK'/('epoch_%08x_record_%08x'%(self.session.local_epoch,rid-1))/'retired_for_next/retired.json'
                _require(ctx['arm']['replaces_retired_snapshot']==json.loads(old.read_bytes()),'Successor linked to wrong retired snapshot')
        return {'record_id':rid,'kind':result['kind'],'identity_hex':result['identity_hex'],
                'result_sha256':store.sha(raw),'actual_receiver_B':applied,
                'labels':{'A_correct':lanes['a'],'B_correct':lanes['b'],'STM_success':classification['business_success'],'STM_payload_correct':classification['source_bytes_match']},
                'evidence_quality':'VALID','strict_retirement_verified':True,'actual_READY_saved':True}

