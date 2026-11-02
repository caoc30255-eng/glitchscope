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

def local_b_rule(plan,history):
    """Rule strategy, not the teammate optimizer or an AI model."""
    count=len(history);last=history[-1] if history else None
    if count==0:stop=False;reason='BOOTSTRAP_CONFIG'
    elif count==1:stop=False;reason='CONFIG_VERIFIED_RUN_UNMARKED_CONTROL'
    elif count==2:
        stop=not all(last['labels'][k] for k in ('A_correct','B_correct','STM_success'))
        reason='BASELINE_INCORRECT_STOP' if stop else 'CONTROL_VERIFIED_RUN_REFERENCE'
    elif count==3:
        stop=last['labels']['B_correct']
        reason='REFERENCE_ALREADY_CORRECT_STOP' if stop else 'REFERENCE_B_FALSE_TRY_PREDECLARED_CANDIDATE'
    else:stop=True;reason='FOUR_RECORD_PLAN_COMPLETE'
    if stop:next_request=None
    elif count==0:next_request={'client_request_id':'CONFIG','receiver_B':{'d':3,'s':-1},'fault':None}
    else:next_request=copy.deepcopy(plan['requests'][count-1])
    return {'schema':'LOCAL_B_RULE_DECISION_V0_1','plan_sha256':plan['plan_sha256'],
            'after_record_id':count,'after_identity_hex':None if last is None else last['identity_hex'],
            'after_result_sha256':None if last is None else last['result_sha256'],
            'action':'STOP' if stop else 'CONTINUE_PREDECLARED_NEXT','next_request':next_request,'reason':reason}


class LocalRuleTrialLoop:
    def __init__(self,executor,*,policy=local_b_rule,policy_id='local_b_rule_v0_1'):
        _require(type(executor) is ControlledTrialExecutor,'Exact reviewed bounded executor required')
        _require(executor.index==executor.attempts==0 and not executor.results and not executor.stopped,'Fresh unexecuted plan required')
        _require(not hasattr(executor,'_rule_loop_owner'),'Executor already owned by a feedback loop')
        _require(callable(policy) and type(policy_id) is str and policy_id and len(policy_id)<=64,'Named explicit policy required')
        executor._verify_plan();_same_session_buses(executor.session,executor.buses);_idle(executor.session,executor.buses)
        plan=json.loads(executor._frozen_plan)
        expected=[{'client_request_id':'baseline','receiver_B':{'d':3,'s':-1},'fault':None},
                  {'client_request_id':'reference_mark','receiver_B':{'d':3,'s':-1},'fault':{'byte':20,'bit':0,'phase':15,'width':20}},
                  {'client_request_id':'candidate_mark','receiver_B':{'d':4,'s':-1},'fault':{'byte':20,'bit':0,'phase':15,'width':20}}]
        _require(plan['requests']==expected and plan['max_physical_starts_including_CONFIG']==4,'First loop requires exact four-record fixed plan')
        _require(executor._frozen_source==bytes(range(256))*3,'Fixed 768-byte stimulus required')
        self.executor=executor;self.session=executor.session;self.buses=executor.buses
        self.policy=policy;self._policy=policy;self.policy_id=policy_id;self._policy_id=policy_id
        self.plan=copy.deepcopy(plan);self.plan['plan_sha256']=store.sha(executor._frozen_plan)
        self._plan_bytes=store._json(self.plan);self._code_sha=store.sha(Path(__file__).read_bytes())
        self.root=self.session.root/'LOCAL_RULE_LOOP';self.root.mkdir(parents=True,exist_ok=False)
        config={'schema':'LOCAL_B_RULE_LOOP_CANDIDATE_V0_1','policy_id':policy_id,
                'plan_sha256':self.plan['plan_sha256'],'policy_source_sha256':self._code_sha,
                'max_records_including_CONFIG_and_control':4,'objective':'receiver_B_complete_frame_correct',
                'STM_separate':True,'training_authorized':False,'production_billing_finalized':False,
                'scope':'local fixed-rule candidate; no teammate algorithm or AI called'}
        persist_exact(self.root/'config',{'config.json':store._json(config)})
        self._config_bytes=store._json(config);self._lock=threading.Lock()
        self.observed_index=0;self.decisions=0;self.done=False;self.stopped=False;self.final_summary=None
        executor._rule_loop_owner=self
        self.session.journal.record('local_rule_loop_config_saved',**config)

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

    def _check_state(self):
        ex=self.executor
        _require(not self.done and not self.stopped and not ex.stopped,'Loop complete/stopped; no resume')
        _require(ex._rule_loop_owner is self and self.policy is self._policy and self.policy_id==self._policy_id,'Executor or policy owner changed')
        _require(ex.index==self.observed_index==len(ex.results) and ex.attempts==ex.index,'Execution outside loop or unresolved attempt')
        _require(self.decisions<=4,'Decision limit reached')
        _require(store._json(self.plan)==self._plan_bytes and store.sha(Path(__file__).read_bytes())==self._code_sha,'Frozen loop source/plan changed')
        self._verify_directory(self.root/'config')
        _require((self.root/'config/config.json').read_bytes()==self._config_bytes,'Loop config changed')
        ex._verify_plan();_same_session_buses(self.session,self.buses)
        verify_sealed_segments(self.session);_idle(self.session,self.buses)

    def _feedback(self,rid):
        ex=self.executor;suffix='epoch_%08x_record_%08x'%(self.session.local_epoch,rid)
        result_dir=ex.root/('record_%08x/result'%rid)
        self._verify_directory(result_dir);raw=(result_dir/'result.json').read_bytes();result=json.loads(raw)
        _require(raw==store._json(ex.results[rid-1]),'Saved/in-memory result differs')
        _require(result['record_id']==rid and result['evidence_quality']=='VALID','Invalid or old record feedback')
        _require(all(result['retirement'][k] is True for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')),'Incomplete strict retirement')
        _require(result['next_credit']['next_item_allowed'] is True and result['next_credit']['last_seq']==rid,'Saved actual READY differs')
        _require(result['next_trial_allowed_by_plan']==(rid<4),'Plan credit differs')
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
            expected_request=_codec().encode_item(self.session.local_epoch,1,result['trial_id'],rid-2,3,0,0,payload)
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
        expected={'d':4 if rid==4 else 3,'s':-1}
        _require(result['actual_receiver_B']==applied and result['requested_receiver_B']==expected and applied['RX_profile_verified'] is True and applied['profile_seq']==rid,'Actual profile differs')
        _require({k:applied[k] for k in ('d','s')}==expected,'Old/mismatched profile readback')
        if rid>=3:
            directory=self.session.root/'MARK'/suffix/'saved';self._verify_directory(directory)
            ctx=json.loads((directory/'context.json').read_bytes())
            wave=(directory/'samples.bin').read_bytes()
            _require(ctx['binding']=={'epoch':self.session.local_epoch,'identity':descriptor['identity'],'record_id':rid},'Waveform binding differs')
            _require(ctx['arm']['source_sha256']==store.sha(request) and ctx['arm']['profile']=={'byte':20,'bit':0,'phase':15,'width':20},'Waveform source/profile differs')
            _require(ctx['analysis']==analyze_waveform(wave,2048,(request[20]&1),20),'Physical waveform analysis differs')
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
            if rid==4:
                old=self.session.root/'MARK'/('epoch_%08x_record_00000003'%self.session.local_epoch)/'retired_for_next/retired.json'
                _require(ctx['arm']['replaces_retired_snapshot']==json.loads(old.read_bytes()),'Successor linked to wrong retired snapshot')
        return {'record_id':rid,'kind':result['kind'],'identity_hex':result['identity_hex'],
                'result_sha256':store.sha(raw),'actual_receiver_B':applied,
                'labels':{'A_correct':lanes['a'],'B_correct':lanes['b'],'STM_success':classification['business_success']},
                'evidence_quality':'VALID','strict_retirement_verified':True,'actual_READY_saved':True}

    def _history(self):return [self._feedback(i) for i in range(1,self.executor.index+1)]

    def _validate_proposal(self,proposal,history):
        expected=local_b_rule(copy.deepcopy(self.plan),copy.deepcopy(history))
        _require(type(proposal) is dict and set(proposal)==set(expected),'Decision fields differ')
        _require(type(proposal['after_record_id']) is int,'Decision record ID must be an integer')
        for k in ('schema','plan_sha256','after_record_id','after_identity_hex','after_result_sha256'):
            _require(proposal[k]==expected[k],'Decision tied to old/wrong feedback')
        _require(proposal['action'] in ('STOP','CONTINUE_PREDECLARED_NEXT'),'Decision action not allowed')
        _require(type(proposal['reason']) is str and 0<len(proposal['reason'])<=256,'Decision reason required')
        if proposal['action']=='STOP':_require(proposal['next_request'] is None,'STOP cannot carry an execution request')
        else:
            _require(len(history)<4,'Four-record budget complete')
            count=len(history)
            allowed={'client_request_id':'CONFIG','receiver_B':{'d':3,'s':-1},'fault':None} if count==0 else self.plan['requests'][count-1]
            _require(store._json(proposal['next_request'])==store._json(allowed),'Parameters/stimulus not next frozen slot')

    def _finish(self,proposal):
        ex=self.executor
        if ex.index<4:ex.cancel_remaining()
        retired=int(self.buses['SYS'].read(0x18));grants=int(self.buses['SYS'].read(0x1c))
        _require(retired==grants==ex.index,'Actual retirement/grant count differs from completed records')
        self.final_summary={'schema':'LOCAL_B_RULE_LOOP_SUMMARY_V0_1','session':self.session.root.name,
                            'policy_id':self.policy_id,'completed_records':ex.index,'max_records':4,
                            'retire_count':retired,'grant_count':grants,'decisions_saved':self.decisions,
                            'stop_reason':proposal['reason'],'history':self._history(),
                            'policy_kind':'LOCAL_REFERENCE_RULE' if self.policy is local_b_rule else 'EXPLICIT_CALLABLE',
                            'teammate_algorithm_called':False if self.policy is local_b_rule else None,
                            'AI_training_run':False,'production_billing_finalized':False}
        persist_exact(self.root/'final',{'summary.json':store._json(self.final_summary)})
        self.session.journal.record('local_rule_loop_finished',summary_sha256=store.sha(store._json(self.final_summary)))
        self.done=True
        return self.final_summary

    def step(self):
        if not self._lock.acquire(False):raise RuntimeError('Concurrent loop step denied')
        entered=False;next_record=self.executor.index+1
        try:
            self._check_state();history=self._history()
            input_data={'plan':self.plan,'history':history,'policy_id':self.policy_id}
            proposal=self.policy(copy.deepcopy(self.plan),copy.deepcopy(history))
            self._validate_proposal(proposal,history)
            directory=self.root/('decision_%08x'%(self.decisions+1))
            persist_exact(directory,{'input.json':store._json(input_data),'proposal.json':store._json(proposal)})
            self.session.journal.record('local_rule_decision_saved',decision_number=self.decisions+1,
                                        proposal_sha256=store.sha(store._json(proposal)),**proposal)
            self._check_state()
            _require(self._history()==history,'Feedback changed before execution')
            self._verify_directory(directory)
            _require((directory/'proposal.json').read_bytes()==store._json(proposal),'Saved decision changed')
            persist_exact(directory/'consumed',{'consume.json':store._json({'proposal_sha256':store.sha(store._json(proposal)),
                'expected_executor_index':self.executor.index,'action':proposal['action'],'one_use':True})})
            self.decisions+=1
            print('LOCAL_RULE_DECISION',json.dumps(proposal),flush=True)
            if proposal['action']=='STOP':return {'action':'STOP','summary':self._finish(proposal)}
            entered=True
            result=self.executor.run_next();self.observed_index=self.executor.index
            checked=self._feedback(self.executor.index)
            self.session.journal.record('local_rule_feedback_verified',**checked)
            return {'action':'RECORD_COMPLETED','decision':proposal,'result':result}
        except Exception as exc:
            if not self.done and not self.stopped:
                self.stopped=True;self.executor.stopped=True;self.session._stop(exc)
                current=self.session.current or self.session.last_retired_owner
                if current is not None and current.binding.record_id!=next_record:current=None
                diagnostic={'error':repr(exc),'next_record_id':next_record,'entered_executor_call':entered,
                            'effect':'UNKNOWN' if entered else 'NO_NEW_RECORD_BY_THIS_CALL','label':None,
                            'actual_start_confirmed':bool(getattr(current,'started',False)),
                            'actual_done_confirmed':bool(getattr(current,'done',False)),
                            'automatic_retry_allowed':False,'soft_reset_allowed':False}
                persist_exact(self.root/('STOP_'+__import__('uuid').uuid4().hex),{'diagnostic.json':store._json(diagnostic)})
            raise
        finally:self._lock.release()

    def run(self):
        _require(not self.done and not self.stopped,'Loop already complete/stopped')
        # Four possible record calls plus one explicit STOP decision, never a fifth record.
        for _ in range(5):
            output=self.step()
            if self.done:return self.final_summary
        raise RuntimeError('Bounded rule loop did not stop')
