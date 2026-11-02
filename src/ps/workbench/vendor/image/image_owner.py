"""Arbitrary uploaded GRAY8 source over the unchanged per-record hardware path."""
import hashlib
import json
from pathlib import Path


class ImageOwner:
    def __init__(self,session,buses,asset,seed,board_lock,package):
        import fcntl
        from random_image_plan import make_schedule
        from random_image_executor import RandomImageExecutor
        from random_image_monitor import RandomImageMonitor
        from ch1_peer_archive_driver import persist_exact
        import ch1_evidence_store as store
        if board_lock.closed or Path(board_lock.name).resolve()!=(session.root.parent/'exclusive.lock').resolve():
            raise ValueError('EXCLUSIVE_LOCK_REQUIRED')
        fcntl.flock(board_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if len(asset['source'])!=16384 or store.sha(asset['source'])!=asset['metadata']['source_sha256']:
            raise ValueError('UPLOADED_IMAGE_BINDING')
        self.session,self.buses,self.board_lock=session,buses,board_lock
        self.session_name=session.root.name;self.package=Path(package).resolve()
        self.source_hash=store.sha(asset['source']);self.failed=False
        self.schedule=make_schedule(seed,source_sha256=self.source_hash)
        # Use a separate image executor/65-record allowance, never the four-record loop.
        persist_exact(session.root/'USER_IMAGE_SOURCE',asset['files'])
        self.executor=RandomImageExecutor(session,buses,asset['source'],self.schedule,exclusive_owner=True)
        self.monitor=RandomImageMonitor(self.executor,self.schedule)
        self.plan=json.loads(self.executor._frozen_plan)
        self.plan.update(asset_id=asset['metadata']['asset_id'],seed=seed,
                         planned_points=sum(e['count'] for e in self.schedule['items']),
                         receiver_B={'d':3,'s':-1},item_count=64)
        self.artifact_root=session.root/'USER_IMAGE_RESULTS'
        self.artifacts=dict(status='WAITING_FOR_RECEIVED_DATA',hardware_input='actual UART archives only')
        files=[self.package/'image_owner.py',self.package/'image_results.py',self.package/'image_service.py',
               self.package/'pilot_service.py',self.package/'web_service.py']
        files.extend((self.package/'runtime/host'/name) for name in (
            'random_image_plan.py','random_image_executor.py','random_image_monitor.py','controlled_trial_executor.py'))
        self.code={p:store.sha(p.read_bytes()) for p in files}
    def counts(self):return dict(attempts=self.executor.attempts,completed=self.executor.index)
    def step(self,stop):
        from ps_idle_journal_segments import _idle,verify_sealed_segments
        from ch1_peer_archive_driver import persist_exact
        import ch1_evidence_store as store
        for p,expected in self.code.items():
            if store.sha(p.read_bytes())!=expected:raise ValueError('IMAGE_GATEWAY_SOURCE_CHANGED')
        e=self.executor
        if stop.is_set() or e.index==65:
            e._verify_plan();self.monitor._verify()
            if set(self.monitor.receipts)!=set(range(1,e.index+1)):
                raise ValueError('IMAGE_ACTUAL_POINT_RECEIPTS_INCOMPLETE')
            if e.index<65:e.cancel_remaining()
            _idle(self.session,self.buses);verify_sealed_segments(self.session)
            actual=(self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))
            if actual!=(e.index,e.index):raise ValueError('IMAGE_STRICT_RETIREMENT_TOTALS')
            summary=dict(completed_records=e.index,attempts=e.attempts,retire_count=actual[0],grant_count=actual[1],
                         plan_complete=e.index==65,source_sha256=self.source_hash,
                         reason='OPERATOR_STOP' if stop.is_set() else 'IMAGE_65_RECORDS_COMPLETE',
                         source_review='PENDING_SOURCE_REVIEW',training_authorized=False)
            persist_exact(self.session.root/'WEB_IMAGE_FINAL',{'summary.json':store._json(summary)})
            return dict(action='STOP',summary=summary)
        result=e.run_next()
        if e.stopped or result['evidence_quality']!='VALID':raise ValueError('IMAGE_INVALID_REPORT_BLOCKS')
        rid=e.index
        raw=(e.root/('record_%08x/result/result.json'%rid)).read_bytes()
        if json.loads(raw)!=result:raise ValueError('IMAGE_RESULT_ORIGINAL_CHANGED')
        if not all(result['retirement'][k] for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')):
            raise ValueError('IMAGE_RECORD_NOT_STRICTLY_RETIRED')
        if not result['next_credit']['next_item_allowed']:raise ValueError('ACTUAL_READY_MISSING')
        return dict(action='RECORD_COMPLETED',verified_result=dict(record_id=rid,kind=result['kind'],
            identity_hex=result['identity_hex'],source_review='PENDING_SOURCE_REVIEW',
            receiver_B_frame_correct=result['receiver_B_frame_correct'],STM_business_success=result['STM_business_success'],
            emitted_points=result['MPG1_pre_retirement']['emitted_points'],strict_retirement_verified=True,
            result_ref=dict(path=(e.root/('record_%08x/result/result.json'%rid)).relative_to(self.session.root).as_posix(),sha256=store.sha(raw))))
    def fail(self,exc):
        self.failed=True;self.executor.stopped=True;self.session._stop(exc)
    def close_receiver(self):
        self.session.control_transport.close()
        if not self.executor.index:
            self.artifacts=dict(status='NO_RECEIVED_CONFIG',missing_pixels=16384);return
        self.artifacts=dict(status='BUILDING_RECEIVED_IMAGES_AND_REPAIR')
        try:
            from image_results import build_results
            report=build_results(self.executor,self.artifact_root)
            self.artifacts=dict(status='READY',report=report)
        except Exception as exc:
            self.artifacts=dict(status='ERROR',error=repr(exc),source_pixels_used_by_repair=False)
