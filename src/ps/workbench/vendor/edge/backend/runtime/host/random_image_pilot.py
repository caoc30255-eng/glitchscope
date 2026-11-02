"""Explicit one-image pilot: at most CONFIG+64 ITEM, no retry or resume."""
from pathlib import Path
import json
from random_image_plan import make_schedule,DEFAULT_SEED
from random_image_executor import RandomImageExecutor
from random_image_monitor import RandomImageMonitor
from random_image_render import archive_images
from ps_idle_journal_segments import _idle,verify_sealed_segments
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store

class RandomImagePilot:
    def __init__(self,session,buses,source,seed=DEFAULT_SEED):
        self.schedule=make_schedule(seed)
        self.executor=RandomImageExecutor(session,buses,source,self.schedule,exclusive_owner=True)
        self.monitor=RandomImageMonitor(self.executor,self.schedule)
        self.session=session;self.buses=buses;self.used=False;self._schedule=store._json(self.schedule)
        self.source=Path(__file__).resolve();self.source_sha=store.sha(self.source.read_bytes())
        self._policy=store._json({
            'schema':'RANDOM_IMAGE_PILOT_V0_1','source_sha256':self.source_sha,
            'schedule_sha256':store.sha(self._schedule),'max_records_including_CONFIG':65,
            'automatic_retry_allowed':False,'all_points_waveform_verified':False,
            'training_authorized':False,'production_billing_finalized':False})
        persist_exact(self.executor.root/'image_policy',{'policy.json':self._policy})

    def _verify_policy(self):
        if (store.sha(self.source.read_bytes())!=self.source_sha or
                store._json(self.schedule)!=self._schedule or
                (self.executor.root/'image_policy/policy.json').read_bytes()!=self._policy or
                json.loads((self.executor.root/'image_policy/committed.json').read_bytes())['files']!=
                {'policy.json':store.sha(self._policy)}):raise ValueError('Image pilot policy/source changed')

    def run(self):
        if self.used:raise RuntimeError('Image pilot already attempted; no retry/resume')
        self.used=True;e=self.executor
        try:
            if (e.index or e.attempts or store.sha(self.source.read_bytes())!=self.source_sha or
                    store._json(self.schedule)!=self._schedule):raise RuntimeError('Fresh frozen image pilot required')
            for rid in range(1,66):
                self._verify_policy()
                e.run_next()
                if e.stopped:raise RuntimeError('Invalid evidence stops remaining image plan')
                print('图片记录:',rid,'/65',flush=True)
            _idle(self.session,self.buses);verify_sealed_segments(self.session)
            if (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(65,65):
                raise ValueError('All65 actual strict retirements/grants required')
            if [r['MPG1_pre_retirement']['emitted_points'] for r in e.results]!=list(self.monitor.expected):
                raise ValueError('Actual point counts differ from saved schedule')
            view=archive_images(e)
            try:e.run_next()
            except RuntimeError as exc:
                if str(exc)!='Finite plan complete; no extra START':raise
                rejection=str(exc)
            else:raise RuntimeError('Record66 was not denied')
            summary={'schema':'RANDOM_IMAGE_PILOT_SUMMARY_V0_1','session':self.session.root.name,
                'seed':self.schedule['seed'],'completed_records':65,'retire_count':65,'grant_count':65,
                'planned_points':view['planned_points'],'actual_emitted_points':sum(self.monitor.expected),
                'zero_point_ITEMs':sum(e['count']==0 for e in self.schedule['items']),
                'receivers':view['receivers'],'all_points_waveform_verified':False,
                'diagnostic_image_view_saved':True,'image_business_acceptance_claimed':False,
                'record66_rejection':rejection,'plan_complete':True,'training_authorized':False,
                'production_billing_finalized':False}
            persist_exact(e.root/'image_summary',{'summary.json':store._json(summary)})
            return summary
        except Exception as exc:
            e.stopped=True;self.session._stop(exc)
            raise
