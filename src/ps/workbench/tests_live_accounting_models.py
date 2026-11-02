"""Exercise real orchestration with fake devices and a PREVIEW ledger, not hardware evidence."""
import json,tempfile,unittest,copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from common import ROOT
from demo_authority import Authority,default_scope
from worker import bind,execute
bind('edge')
import live,custom_owner,custom_authorization,custom_io,custom_replay
from custom_executor import CustomExecutor

class LoopModels(unittest.TestCase):
    def run_model(self,stop_after=None,fail_at=None,ai_abstains=False):
        base=Path(tempfile.mkdtemp(prefix='synthetic_live_loop_',dir=str(ROOT.parent)));out=base/('c'*32);out.mkdir()
        plan=json.loads((ROOT/'checks/regression_saved_plan.json').read_bytes())
        if ai_abstains:
            r=copy.deepcopy(plan['request']);r['max_records']=14;r['scan']['points']=[dict(phase=15,width=1),dict(phase=15,width=30)];r['refinement']=dict(enabled=True,confirmation_repeats=3,candidates=[dict(phase=p,width=w) for p in (5,15,25,35) for w in (1,10,20,30,40) if p+w<=45])
            plan=execute('scan_preview',dict(request=r,strategy='ai',max_extra_groups=2),out)['plan']
        a=Authority(base/'book');round_id=a.create_round(100,default_scope(),'MODEL_ONLY','批准本轮 100 条',True)['active_round']['id'];reservation=a.reserve('scan',plan,'c'*32,'合成执行循环测试')
        class FakeGate:
            def __init__(self,kind,p,config,request):
                self.authority=a;self.job_id='c'*32;self.value=dict(session_alias='合成执行循环测试',limit=14 if ai_abstains else 44);self.scan_path=Path(reservation['permit_path']);self.runs=base;self.assets={}
            def check(self):a.verify_permit(reservation['permit_path'],plan)
        class Lock:
            closed=False
            def close(self):self.closed=True
        class Control:
            context=object()
            def close(self):self.context=None
        session=SimpleNamespace(root=base/'session_00000050',handles=[],_stop=lambda error:None)
        session.root.mkdir();session.fault=False;session._stop=lambda error:setattr(session,'fault',True);control=Control();lock=Lock()
        def setup(gate,output,progress):
            a.mark_setup('c'*32);a.bind_session('c'*32,session.root);return session,{},lock,control,None
        class Owner:
            def __init__(self,s,b,l,p,execution_context=None):
                self.state='READY';self.cleanup=None;self.executor=SimpleNamespace(index=0);self.receipts=[];self.feedback=SimpleNamespace(_feedback=lambda rid:self.receipts[rid-1]);self._queue=copy.deepcopy(p['initial_queue']);self._cursor=0
            def start_once(self,key):self.state='RUNNING'
            def next_suggestion(self):return dict(action='STOP',reason='SYNTHETIC_ABSTENTION')
            def step(self,key,selection=None):
                n=self.executor.index
                if n>=plan['max_records'] or (n>=2 and self._cursor>=len(self._queue)):
                    self.state='STOPPED_PLAN_COMPLETE';self.cleanup=dict(errors=[]);return
                if fail_at==n+1:raise TimeoutError('SYNTHETIC_UNKNOWN_NO_DEVICE')
                self.executor.index+=1;self.receipts.append(dict(record_id=n+1,kind='CONFIG' if n==0 else 'ITEM',identity_hex='01',result_sha256='0'*64,actual_receiver_B={'d':3,'s':-1},labels={},evidence_quality='VALID',strict_retirement_verified=True,actual_READY_saved=True))
                if n>=2:self._cursor+=1
                if self.executor.index==plan['max_records']:self.state='STOPPED_PLAN_COMPLETE';self.cleanup=dict(errors=[])
                if self.executor.index==stop_after:(out/'STOP_REQUESTED').write_text('operator model stop')
            def status(self):return dict(state=self.state,valid_records=self.executor.index,max_records=plan['max_records'])
            def _close(self):self.cleanup=dict(errors=[])
            def request_stop(self):
                if session.fault:raise RuntimeError('PS session stopped; no automatic resume')
                self.state='STOPPED';self.cleanup=dict(errors=[])
        with patch.object(live,'Gate',FakeGate),patch.object(live,'initialize',setup),patch.object(custom_owner,'CustomOwner',Owner),patch.object(custom_authorization,'ExecutionContext',lambda *a,**k:object()),patch.object(custom_io,'export',lambda *a:None),patch.object(custom_replay,'reconstruct',lambda *a:dict(status='REGISTER_DRIVER_MODEL_ONLY')):
            try:live.run('live_scan',dict(plan=plan,live_config={}),out,lambda **v:None)
            except TimeoutError:
                if fail_at is None:raise
        self.assertTrue(lock.closed);self.assertIsNone(control.context)
        return a.status()['active_round'],json.loads((out/'demo_accounting.json').read_bytes())
    def test_complete44_claims_exactly44(self):
        r,t=self.run_model();self.assertEqual((r['occupied'],r['completed'],r['available'],t['unknown']),(44,44,56,0))
    def test_operator_stop_releases_only_unstarted(self):
        r,t=self.run_model(stop_after=5);self.assertEqual((r['occupied'],r['completed'],r['available'],t['state']),(5,5,95,'STOPPED'))
    def test_unknown_attempt_not_refunded(self):
        r,t=self.run_model(fail_at=3);self.assertEqual((r['occupied'],r['completed'],r['unknown'],r['state']),(3,2,1,'BLOCKED'))
    def test_ai_selection_boundary_without_execution_costs_nothing(self):
        r,t=self.run_model(ai_abstains=True);self.assertEqual((r['occupied'],r['completed'],r['available']),(8,8,92))
    def credit_fixture(self):
        base=Path(tempfile.mkdtemp(prefix='record_guard_model_',dir=str(ROOT.parent)));a=Authority(base/'book');p=json.loads((ROOT/'checks/regression_saved_plan.json').read_bytes());a.create_round(100,default_scope(),'MODEL_ONLY','批准本轮 100 条',True);a.reserve('scan',p,'d'*32,'纯模型验证');a.mark_setup('d'*32);session=SimpleNamespace(root=base/'session_00000050');a.bind_session('d'*32,session.root);return a,p,session
    def test_original_scan_dispatch_calls_credit_guard_before_writer(self):
        a,p,session=self.credit_fixture();calls=[]
        ctx=SimpleNamespace(verify_record=lambda plan,s,lock,rid:a.require_record('d'*32,rid,s.root))
        owner=SimpleNamespace(execution_context=ctx,plan=p,board_lock=None);e=CustomExecutor.__new__(CustomExecutor);e._bridge_owner=owner;e._active_owner_thread=None;e.index=0;e.session=session;e.run_next=lambda:calls.append('MODEL_WRITER')
        with self.assertRaises(ValueError):e.execute_bound(owner)
        self.assertFalse(calls);a.claim('d'*32,1);e.execute_bound(owner);self.assertEqual(len(calls),1);a.retire('d'*32,1)
        with self.assertRaises(ValueError):e.execute_bound(owner)
    def test_image_wrapper_calls_credit_guard_before_writer(self):
        a,p,session=self.credit_fixture();calls=[]
        class Base:
            index=0
            def run_next(self):calls.append('MODEL_IMAGE_WRITER')
        gate=SimpleNamespace(require_record=lambda rid:a.require_record('d'*32,rid,session.root));e=live.image_executor_type(Base,gate)()
        with self.assertRaises(ValueError):e.run_next()
        self.assertFalse(calls);a.claim('d'*32,1);e.run_next();self.assertEqual(len(calls),1);a.retire('d'*32,1)
        with self.assertRaises(ValueError):e.run_next()

if __name__=='__main__':unittest.main(verbosity=2)
