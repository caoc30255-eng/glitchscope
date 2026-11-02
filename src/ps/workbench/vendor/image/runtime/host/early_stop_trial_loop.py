"""Explicit two-record STOP pilot over the unchanged four-slot rule executor.

This does not fabricate successful marked reception. No marked ITEM is run.
All imports are free of hardware IO. No reset/retry/refund/extra quota API.
"""
from pathlib import Path
import json
from local_rule_trial_loop import LocalRuleTrialLoop,local_b_rule,_require
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store

POLICY_ID='explicit_stop_after_control_v0_1'
STOP_REASON='EXPLICIT_STOP_AFTER_UNMARKED_CONTROL'

def stop_after_control(plan,history):
    proposal=local_b_rule(plan,history)
    if len(history)>=2:
        proposal.update(action='STOP',next_request=None,reason=STOP_REASON)
    return proposal

class EarlyStopTrialLoop(LocalRuleTrialLoop):
    def __init__(self,executor):
        super().__init__(executor,policy=stop_after_control,policy_id=POLICY_ID)
        self.stop_test_summary=None
        self._stop_source=Path(__file__).resolve()
        self._stop_sha=store.sha(self._stop_source.read_bytes())
        policy={'schema':'EXPLICIT_EARLY_STOP_POLICY_V0_1','policy_id':POLICY_ID,
                'policy_module_sha256':self._stop_sha,'base_loop_module_sha256':self._code_sha,
                'plan_sha256':self.plan['plan_sha256'],'stop_after_completed_records':2,
                'max_plan_records':4,'reason':STOP_REASON,
                'scope':'explicit cancellation of unstarted slots, not reference B already-correct branch',
                'marked_reception_success_fabricated':False,'teammate_algorithm_called':False,
                'training_authorized':False,'production_billing_finalized':False}
        self._stop_bytes=store._json(policy)
        persist_exact(self.root/'EARLY_STOP_POLICY',{'policy.json':self._stop_bytes})
        self.session.journal.record('explicit_early_stop_policy_saved',**policy)

    def _check_state(self):
        super()._check_state()
        _require(self.policy is stop_after_control and self.policy_id==POLICY_ID,'Explicit STOP policy changed')
        _require(store.sha(self._stop_source.read_bytes())==self._stop_sha,'Explicit STOP source changed')
        self._verify_directory(self.root/'EARLY_STOP_POLICY')
        _require((self.root/'EARLY_STOP_POLICY/policy.json').read_bytes()==self._stop_bytes,'Explicit STOP fingerprint changed')

    def _finish(self,proposal):
        try:
            ex=self.executor
            _require(ex.index==ex.attempts==2 and len(ex.results)==2,'STOP must follow exactly CONFIG and unmarked control')
            _require(proposal['action']=='STOP' and proposal['reason']==STOP_REASON and proposal['next_request'] is None,'Not the explicit STOP test')
            history=self._history()
            _require(all(all(h['labels'][k] is True for k in ('A_correct','B_correct','STM_success')) for h in history),'Unmarked control did not pass')
            cap=self.session.mark_capture
            _require(cap.used is False,'Raw capture was unexpectedly armed')
            raw={'status':cap.read(8),'sample_count':cap.read(12),'trigger_offset':cap.read(16),'live_sample':cap.read(0x20)}
            _require(raw['status']==0 and raw['sample_count']==0 and raw['trigger_offset']==0 and raw['live_sample']&7==3,'Raw capture not fresh/unarmed at explicit STOP')
            # Existing cancellation is filesystem-only and requires actual idle.
            base=super()._finish(proposal)
            cancel_dir=ex.root/'cancelled';self._verify_directory(cancel_dir)
            cancel=json.loads((cancel_dir/'cancel.json').read_bytes())
            _require(cancel=={'completed_records':2,'unstarted_records_cancelled':2,
                             'refund_or_new_quota_created':False,'hardware_writes':0},'Unstarted cancellation proof differs')
            _require(ex.stopped is True and base['retire_count']==base['grant_count']==2,'Executor did not stop at two actual retirements')
            self.stop_test_summary={'schema':'EXPLICIT_EARLY_STOP_RESULT_V0_1','session':self.session.root.name,
                'policy_id':POLICY_ID,'stop_reason':STOP_REASON,'completed_records':2,'max_plan_records':4,
                'unstarted_records_cancelled':2,'retire_count':2,'grant_count':2,'decisions_saved':self.decisions,
                'raw_capture_unarmed_readback':raw,'raw_capture_ARM_commands_by_this_policy':0,
                'marked_ITEMs_executed':0,'refund_or_new_quota_created':False,
                'base_summary_sha256':store.sha((self.root/'final/summary.json').read_bytes()),
                'reference_B_already_correct_branch_tested':False,'teammate_algorithm_called':False,
                'training_authorized':False,'production_billing_finalized':False,
                'scope':'explicit two-record STOP and cancellation pilot; no marked-reference label invented'}
            persist_exact(self.root/'EARLY_STOP_RESULT',{'result.json':store._json(self.stop_test_summary)})
            self.session.journal.record('explicit_early_stop_verified',result_sha256=store.sha(store._json(self.stop_test_summary)),**self.stop_test_summary)
            return self.stop_test_summary
        except Exception:
            # Base finish may have completed cancellation before a disk failure.
            # Do not leave a failed STOP certificate looking like a successful run.
            self.done=False
            raise

    def run(self):
        super().run()
        _require(self.stop_test_summary is not None,'No saved explicit STOP result')
        return self.stop_test_summary
