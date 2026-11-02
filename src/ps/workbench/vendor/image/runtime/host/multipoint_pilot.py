"""Explicit four-record Direct pilot. Import performs no device access."""
from pathlib import Path
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from fault_profile import FaultProfile
from multi_point_profile import MultiPointProfile
from mpg1_trial_monitor import MPG1TrialMonitor
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store


class MultiPointPilot:
    def __init__(self,session,buses,source):
        if bytes(source)!=bytes(range(256))*3:raise ValueError('Frozen three identical payload chunks required')
        self.monitor=MPG1TrialMonitor(session,buses)
        self.executor=ControlledTrialExecutor(session,buses,source,(
            TrialRequest('baseline',3,-1),
            TrialRequest('legacy_single',3,-1,FaultProfile(20,0,15,20)),
            TrialRequest('multi_four',3,-1,MultiPointProfile(20,4,0,15,20)),
        ),max_physical_starts=4,exclusive_owner=True)
        self.used=False;self.session=session;self.buses=buses
        self.source=Path(__file__).resolve();self.source_sha=store.sha(self.source.read_bytes())
        persist_exact(self.executor.root/'multipoint_policy',{'policy.json':store._json({
            'schema':'MPG1_FOUR_RECORD_PILOT_V0_1','source_sha256':self.source_sha,
            'expected_points':[0,0,1,4],'automatic_retry_allowed':False,
            'CAP06_scope':'FIRST_POINT_ONLY','all_points_waveform_verified':False})})

    def run(self):
        if self.used:raise RuntimeError('Pilot already attempted; no retry/resume')
        self.used=True
        e=self.executor
        try:
            if e.index or e.attempts or store.sha(self.source.read_bytes())!=self.source_sha:
                raise RuntimeError('Fresh frozen pilot required')
            for rid in range(1,5):
                result=e.run_next()
                if e.stopped or result['evidence_quality']!='VALID':raise RuntimeError('Invalid evidence stops plan')
                print('已完成记录:',rid,'/ 4',flush=True)
            counts=[r['MPG1_pre_retirement']['emitted_points'] for r in e.results]
            if counts!=[0,0,1,4] or (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(4,4):
                raise ValueError('Four exact count proofs and strict retirements required')
            try:e.run_next()
            except RuntimeError as exc:
                if str(exc)!='Finite plan complete; no extra START':raise
                rejection=str(exc)
            else:raise RuntimeError('Extra record was not denied')
            summary={'schema':'MPG1_FOUR_RECORD_SUMMARY_V0_1','session':self.session.root.name,
                'completed_records':e.index,'retire_count':4,'grant_count':4,
                'emitted_points':counts,'TYPE3C_exact_ACK_verified':True,
                'B_frame_correct':[r['receiver_B_frame_correct'] for r in e.results],
                'STM_business_success':[r['STM_business_success'] for r in e.results],
                'first_point_waveform_verified':e.results[3]['physical_waveform']['first_point_physical_inversion_verified'],
                'all_points_waveform_verified':False,'fifth_record_rejection':rejection,
                'plan_complete':True,'training_authorized':False,'production_billing_finalized':False}
            persist_exact(e.root/'multipoint_summary',{'summary.json':store._json(summary)})
            return summary
        except Exception as exc:
            e.stopped=True;self.session._stop(exc)
            raise
