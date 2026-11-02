"""Explicit external permission before device import. New code authorizes zero trials."""
import json,os,sys,platform,time,uuid
from pathlib import Path
from common import ROOT,require,sha,digest,write,verify
from worker import bind,image_bind,repair_session
ORIGINAL_ASSETS=dict(bit='0c0b686e80e37e49e64ab07b719a0c1ea3387451f3ceebdba5dcf38b8c68b61c',hwh='8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc',native='e3514adfe6aef5269d0ff833b18404ba27be8435c2c3f3631d3e475ef108bdd8')

def approval_request(kind,plan,assets,runs):
    value=dict(schema='GLITCHSCOPE_UI_APPROVAL_V1',approved_by_user=False,reviewed_by_owner=False,
        approval_reference='',kind=kind,plan_sha256=plan['sha256'],max_records=plan.get('max_records',65),
        runs_directory=str(Path(runs).resolve()),asset_sha256={k:sha(v) for k,v in assets.items()},
        ui_manifest_sha256=sha(ROOT/'manifest.json'),stages=dict(overlay=False,initialize=False,physical_records=False),
        prior_occupied=None,cumulative_limit=None,
        automatic_retry=False,automatic_reset=False,resume_allowed=False,training_authorized=False)
    if kind=='scan':
        bind('edge');from custom_real import approval_template
        value['scanner_approval']=approval_template(plan,assets,runs)
    return value

class Gate:
    def __init__(self,kind,plan,config,request):
        from demo_authority import Authority
        self.authority=Authority.for_live(config);self.path=Path(request['demo_permit']).resolve();self.data=self.path.read_bytes();self.value=self.authority.verify_permit(self.path,plan)
        self.plan=plan;self.assets={k:str(Path(v).resolve()) for k,v in config['assets'].items()};self.runs=Path(config['runs']).resolve();self.job_id=request['job_id'];self.scan_path=self.path
        require(self.value['job_id']==self.job_id and self.value['kind']==kind and self.value['mode']=='LIVE','LIVE_PERMIT_REQUIRED')
        require(request['confirmation']=='执行本任务 %d 条'%self.value['limit'] and request['manual_7010_ready'] is True,'MANUAL_READY_AND_TASK_CONFIRMATION_REQUIRED')
        require(request.get('task_review_ack') is True and self.value['task_confirmation']==request['confirmation'] and self.value['review_ack'] is True and self.value['manual_ready'] is True,'TASK_CONFIRMATION_NOT_BOUND')
        require(self.value['session_alias']==request['session_alias'],'SESSION_ALIAS_CHANGED');self.authority.bind_worker(self.job_id)
    def check(self):
        require(self.path.read_bytes()==self.data,'PERMIT_FILE_CHANGED');self.authority.verify_permit(self.path,self.plan)
    def reserve(self):self.authority.mark_setup(self.job_id)
    def require_record(self,rid):
        self.check();self.authority.require_record(self.job_id,rid,self.session.root)

def image_executor_type(base,gate):
    class QuotaImageExecutor(base):
        def run_next(self):
            gate.require_record(self.index+1);return super().run_next()
    return QuotaImageExecutor

def initialize(gate,out,progress):
    require(platform.system()=='Linux' and platform.machine()=='armv7l','LIVE_REQUIRES_PYNQ_ARMV7L')
    from runtime_lease import acquire_runtime_lock
    from installation_state import fresh_identity,validate_registries,check_clock_environment
    lock=None;session=None;control=None
    try:
        lock=acquire_runtime_lock(gate.runs);gate.check();gate.reserve()
        # File hashes and external approval have been checked before this import or write.
        from pynq import Overlay,MMIO,Clocks
        import pynq
        profile=check_clock_environment(Clocks,pynq.__version__)
        progress(stage='CLOCK_ENVIRONMENT_CHECKED',profile=profile)
        require(sha(gate.assets['bit'])=='0c0b686e80e37e49e64ab07b719a0c1ea3387451f3ceebdba5dcf38b8c68b61c','ORIGINAL_BIT_REQUIRED')
        require(sha(gate.assets['hwh'])=='8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc','ORIGINAL_HWH_REQUIRED')
        require(sha(gate.assets['native'])=='e3514adfe6aef5269d0ff833b18404ba27be8435c2c3f3631d3e475ef108bdd8','REVIEWED_NATIVE_REQUIRED')
        # Clock convention for the accepted Navigator V2/PYNQ 2.7 image:
        # PYNQ assumes a 50 MHz PS reference; this board uses 33.333333 MHz.
        # API readback 150 therefore corresponds to ~100 MHz from PLL/dividers.
        # Preserve the accepted setting. Do not copy 150 to a corrected image,
        # or change only this value/reference. See docs/clock_reference.md.
        # Register-derived frequency is not an independent physical measurement.
        progress(stage='OVERLAY_SETUP');overlay=Overlay(gate.assets['bit']);Clocks.fclk0_mhz=150
        require(abs(float(Clocks.fclk0_mhz)-150)<0.001,'FCLK_READBACK')
        if gate.value['kind']=='scan':from reviewed_probe import probe
        else:from read_only_probe import probe
        fresh=probe(MMIO,gate.assets['hwh']);expected=dict(H1=1,CTRL=0,MAIN=0,AUX=0,MAP=0,CH0=8,PROFILE=4,SYS=0)
        require(fresh['all_IDs_match'] and all(int(b['status'],16)==expected[b['bank']] for b in fresh['banks']),'FRESH_CSR_REQUIRED')
        require(all(fresh[k]==0 for k in ('local_epoch','retire_count','grant_count','capacity_permission')),'FRESH_COUNTERS_REQUIRED')
        origin=fresh_identity(gate.authority.config)
        registry=gate.runs/'namespace_allocations.jsonl';numbers=[v['number'] for v in validate_registries(gate.runs,origin)]
        trials=gate.runs/'trial_registry';require(trials.is_dir(),'EXISTING_TRIAL_REGISTRY_REQUIRED')
        ids=sorted(int(p.stem.split('_')[1],16) for p in trials.glob('trial_*.json'))
        require(ids==list(range(1,len(ids)+1)) and len(ids)<65535,'TRIAL_HISTORY_CHANGED')
        for p in trials.glob('trial_*.json'):require(json.loads(p.read_bytes())['trial_id']==int(p.stem.split('_')[1],16),'TRIAL_ID_CHANGED')
        n=len(numbers)+1;root=gate.runs/('session_%08x'%n);require(n<0x10000000 and not root.exists(),'NEW_SESSION_REQUIRED')
        allocation=dict(number=n)
        if origin:allocation['installation_id']=origin['id']
        with registry.open('a',encoding='utf-8') as f:f.write(json.dumps(allocation)+'\n');f.flush();os.fsync(f.fileno())
        fd=os.open(str(gate.runs),os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        gate.authority.bind_session(gate.job_id,root)
        progress(stage='SESSION_ALLOCATED',session_name=root.name,session=str(root),session_alias=gate.value['session_alias'])
        from ps_candidate_session import CandidateSession,BANKS
        from ch1_uartlite_realtime_transport import RealtimeUARTLiteControlTransport
        buses={bank:MMIO(address,size) for bank,(address,size,_) in BANKS.items()}
        session=CandidateSession(buses,root,local_epoch=0x10000000+n,peer_epoch=0x20000000+n,session=0x30000000+n,control_epoch=0x40000000+n,exclusive_owner=True,poll_limit=10000)
        if origin:write(root/'INSTALLATION_BINDING.json',dict(installation_id=origin['id'],runs=str(gate.runs)))
        write(root/'DEMO_UI/session_label.json',dict(job_id=gate.job_id,round_id=gate.value['round_id'],session_alias=gate.value['session_alias'],session_name=root.name,plan_sha256=gate.plan['sha256']))
        write(root/'UNIFIED_UI/binding.json',dict(plan=gate.plan,approval=gate.value,permit_sha256=sha(gate.path),new_session=True,automatic_retry=False))
        write(root/'UNIFIED_UI/preflight.json',fresh)
        control=RealtimeUARTLiteControlTransport(MMIO(0x42c00000,0x10000),session.journal,library=gate.assets['native'],exclusive_owner=True,timeout=2.0,receiver_cpu=1,receiver_priority=10,receiver_idle_ns=50000)
        control.start_receiver();session.initialize(control)
        require(session.upload.ready is True and not session.fault,'SESSION_NOT_READY')
        from fault_pilot_workflow import inspect_raw_mark_interface
        from multipoint_capability_preflight import inspect_multipoint_capability
        inspect_raw_mark_interface(session,MMIO,gate.assets['hwh']);inspect_multipoint_capability(session,buses)
        progress(stage='READY',session=str(root),scheduling=control.scheduling_snapshot())
        return session,buses,lock,control,overlay
    except BaseException as e:
        errors=[]
        if session:
            try:session._stop(e)
            except BaseException as close_error:errors.append(repr(close_error))
        if control:
            try:control.close()
            except BaseException as close_error:errors.append(repr(close_error))
        if session:
            for h in reversed(session.handles):
                try:h.close()
                except BaseException as close_error:errors.append(repr(close_error))
        if control is not None and getattr(control,'context',None) is not None:errors.append('receiver native context not released')
        if lock is not None:
            if errors:lock.quarantine(errors)
            lock.close()
        gate.authority.settle(gate.job_id,'FAILED_SETUP',not errors,repr(e),block=True)
        write(out/'demo_accounting.json',gate.authority.task(gate.job_id));raise

def run(action,request,out,progress):
    kind='scan' if action=='live_scan' else 'image'
    if kind=='scan':
        bind('edge');from custom_plan import validate_plan
        validate_plan(request['plan'])
    else:
        image_bind();from image_plan import validate
        validate(request['plan'])
        # Exact accepted executor/monitor copies; only schedule validator is adapted.
        import paired_executor,paired_monitor
        paired_executor.validate_schedule=validate;paired_monitor.validate_schedule=validate
    plan=request['plan'];gate=Gate(kind,plan,request['live_config'],request)
    session,buses,lock,control,overlay=initialize(gate,out,progress)
    gate.session=session
    owner=None;e=None;failure=None;summary={};stopped=False;result_value=None;terminal_state='COMPLETE'
    try:
        if kind=='scan':
            from custom_authorization import ExecutionContext
            from custom_owner import CustomOwner,TERMINAL
            context=ExecutionContext(gate.scan_path,plan,gate.assets,gate.runs,session,lock)
            owner=CustomOwner(session,buses,lock,plan,execution_context=context);owner.start_once(uuid.uuid4().hex)
            for i in range(plan['max_records']+2):
                gate.check()
                if (out/'STOP_REQUESTED').exists():owner.request_stop();stopped=True;break
                if owner.state in TERMINAL:break
                index=owner.executor.index;selection=None
                if index>=plan['max_records']:
                    owner.step(uuid.uuid4().hex);break
                if index>=2 and owner._cursor>=len(owner._queue):
                    if not plan['refinement']['enabled']:
                        owner.step(uuid.uuid4().hex);break
                    selection=owner.next_suggestion()
                    if selection['action']!='SELECT':
                        owner.step(uuid.uuid4().hex);break
                gate.authority.claim(gate.job_id,index+1)
                owner.step(uuid.uuid4().hex,selection)
                from feedback_contract import verify_owner_receipt
                verify_owner_receipt(owner,index+1)
                gate.authority.retire(gate.job_id,index+1)
                progress(stage=owner.state,session_name=session.root.name,session_alias=gate.value['session_alias'],execution_max_records=gate.value['limit'],**owner.status())
                if owner.state in TERMINAL:break
            terminal_state=owner.state
            from custom_io import export
            export(out/'scan',owner)
            from custom_replay import reconstruct
            result_value=reconstruct(session.root)
        else:
            from paired_executor import PairedImageExecutor
            from paired_monitor import PairedImageMonitor
            source=Path(request['source']).read_bytes()
            require(hashlib_sha(source)==plan['source_sha256'],'UPLOADED_SOURCE_CHANGED')
            e=image_executor_type(PairedImageExecutor,gate)(session,buses,source,plan,exclusive_owner=True);monitor=PairedImageMonitor(e,plan)
            for i in range(65):
                gate.check()
                if (out/'STOP_REQUESTED').exists():e.cancel_remaining();stopped=True;break
                gate.authority.claim(gate.job_id,i+1)
                r=e.run_next();monitor._verify()
                require(not e.stopped and r['evidence_quality']=='VALID','INVALID_IMAGE_FEEDBACK_BLOCKS')
                require(e.index==i+1 and all(r['retirement'][k] is True for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')),'IMAGE_RECORD_NOT_STRICTLY_RETIRED')
                gate.authority.retire(gate.job_id,i+1)
                progress(stage='RUNNING',session=str(session.root),completed_records=e.index,max_records=65,
                    B_correct=r['receiver_B_frame_correct'],STM_business_success=r['STM_business_success'])
            from ps_idle_journal_segments import _idle,verify_sealed_segments
            _idle(session,buses);verify_sealed_segments(session)
            require((buses['SYS'].read(0x18),buses['SYS'].read(0x1c))==(e.index,e.index),'STRICT_RETIREMENT_COUNTS')
            require(set(monitor.receipts)==set(range(1,e.index+1)),'IMAGE_POINT_RECEIPTS_INCOMPLETE')
            summary=dict(state='STOPPED' if stopped else 'COMPLETE',session=str(session.root),completed_records=e.index,attempts=e.attempts,receiver_B=plan['request']['receiver_B'])
    except BaseException as error:
        failure=repr(error)
        try:session._stop(error)
        except BaseException:pass
        raise
    finally:
        errors=[]
        if owner is not None and owner.cleanup is None:
            try:
                # A stopped PS session cannot enter _idle again. Close host resources only.
                if getattr(session,'fault',False):owner._close()
                else:owner.request_stop()
            except BaseException as error:
                errors.append(repr(error))
                try:
                    if owner.cleanup is None:owner._close()
                except BaseException as close_error:errors.append(repr(close_error))
        try:control.close()
        except BaseException as error:errors.append(repr(error))
        for handle in reversed(session.handles):
            try:handle.close()
            except BaseException as error:errors.append(repr(error))
        if owner and owner.cleanup and owner.cleanup.get('errors'):errors.extend(owner.cleanup['errors'])
        if control.context is not None:errors.append('receiver native context not released')
        if errors and hasattr(lock,'quarantine'):lock.quarantine(errors)
        lock.close()
        accounted=gate.authority.settle(gate.job_id,'FAILED' if failure else 'STOPPED' if stopped else terminal_state,not errors,failure or terminal_state,block=bool(failure or 'BLOCKED' in terminal_state or 'FAILED' in terminal_state))
        write(out/'demo_accounting.json',accounted)
        write(out/'live_cleanup.json',dict(session=str(session.root),failure=failure,close_errors=errors,lock_closed=lock.closed,receiver_released=control.context is None,reset_sent=False,retry_sent=False))
    if kind=='image':
        summary['artifacts']=repair_session(session.root,out,progress,live=True);result_value=summary
    return result_value

def hashlib_sha(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()
