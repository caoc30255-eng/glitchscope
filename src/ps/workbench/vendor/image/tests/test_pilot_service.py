"""Gateway state/ordering tests with an explicit modeled owner; never hardware."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot_service import PilotService


class Owner:
    plan = dict(max_physical_starts_including_CONFIG=4, source_sha256='a'*64)
    session_name = 'modeled_only'
    def __init__(self, failure=None, gate=None):
        self.attempts = self.done = self.calls = 0
        self.closed = False
        self.failed = False
        self.failure = failure
        self.gate = gate
        self.entered = threading.Event()
    def counts(self):
        return dict(attempts=self.attempts, completed=self.done)
    def step(self, stop):
        self.calls += 1
        if stop.is_set() or self.done == 4:
            return dict(action='STOP', summary=dict(retire_count=self.done, grant_count=self.done))
        self.attempts += 1
        self.entered.set()
        if self.gate:
            self.gate.wait(5)
        if self.failure:
            raise self.failure
        self.done += 1
        return dict(action='RECORD_COMPLETED', verified_result=dict(record_id=self.done, label=True))
    def fail(self, exc):
        self.failed = True
    def close_receiver(self):
        self.closed = True


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.owner = Owner()
        self.root = Path(self.tmp.name)/'WEB'
        self.service = PilotService(self.owner, self.root)
        self.plan = self.service.status()['plan_sha256']
    def command(self, action='start', key='start-key-0001'):
        return self.service.command(action, key, self.plan)
    def finish(self):
        self.assertTrue(self.service.join(5))
        return self.service.status()
    def test_constructor_and_status_do_not_execute(self):
        for _ in range(20):self.service.status()
        self.assertEqual(self.owner.calls,0)
        self.assertEqual(self.service.status()['state'],'READY')
    def test_full_four_and_repeat_start_idempotent(self):
        first=self.command();self.assertEqual(first,self.command())
        final=self.finish();self.assertEqual(final['state'],'COMPLETE')
        self.assertEqual(self.owner.attempts,4);self.assertEqual(self.owner.calls,5)
        self.assertTrue(self.owner.closed)
        self.assertEqual(first,self.command())
        with self.assertRaises(ValueError):self.command(key='different-start')
        self.assertEqual(self.owner.attempts,4)
    def test_same_key_different_command_rejected(self):
        self.command();self.finish()
        with self.assertRaises(ValueError):self.command('stop')
    def test_wrong_plan_rejected_before_execution(self):
        with self.assertRaises(ValueError):self.service.command('start','new-key-1234','b'*64)
        self.assertEqual(self.owner.calls,0)
    def test_unknown_action_or_short_key_rejected(self):
        for action,key in [('retry','a-long-enough-key'),('start','x')]:
            with self.assertRaises(ValueError):self.service.command(action,key,self.plan)
        self.assertEqual(self.owner.calls,0)
    def test_stop_before_start_cancels_all_without_record(self):
        self.command('stop','stop-key-0001');final=self.finish()
        self.assertEqual(final['state'],'STOPPED');self.assertEqual(self.owner.attempts,0)
        with self.assertRaises(ValueError):self.command()
    def test_stop_during_record_waits_boundary_and_no_next_record(self):
        gate=threading.Event();self.owner.gate=gate
        self.command();self.assertTrue(self.owner.entered.wait(2))
        stop=self.command('stop','stop-key-0001')
        self.assertEqual(self.service.status()['state'],'STOPPING')
        self.assertFalse(self.owner.closed)
        gate.set();final=self.finish()
        self.assertEqual(final['state'],'STOPPED');self.assertEqual(self.owner.done,1)
        self.assertEqual(final['completed_records'],1)
        self.assertEqual(stop,self.command('stop','stop-key-0001'))
    def test_concurrent_start_creates_one_worker(self):
        receipts=[];errors=[]
        def call():
            try:receipts.append(self.command())
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=call) for _ in range(10)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.finish();self.assertFalse(errors);self.assertEqual(len(receipts),10)
        self.assertTrue(all(r==receipts[0] for r in receipts));self.assertEqual(self.owner.attempts,4)
    def test_unknown_has_null_label_and_never_retries(self):
        self.owner.failure=TimeoutError('modeled uncertain START')
        self.command();final=self.finish()
        self.assertEqual(final['state'],'BLOCKED_UNKNOWN');self.assertIsNone(final['unresolved_label'])
        self.assertEqual(final['attempts'],1);self.assertEqual(final['results'],[])
        self.assertTrue(self.owner.closed);self.assertTrue(self.owner.failed)
        with self.assertRaises(ValueError):self.command(key='new-start-after-unknown')
        self.assertEqual(self.owner.attempts,1)
    def test_owner_diagnostic_failure_still_blocks(self):
        self.owner.failure=OSError('disk')
        self.owner.fail=lambda e:(_ for _ in ()).throw(OSError('diagnostic disk'))
        self.command();self.assertEqual(self.finish()['state'],'BLOCKED_UNKNOWN')
    def test_storage_failure_prevents_first_record(self):
        with patch('pilot_service.save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.command()
        self.assertEqual(self.owner.calls,0)
        self.assertEqual(self.service.status()['state'],'BLOCKED_STORAGE')
        with self.assertRaises(ValueError):self.command(key='another-new-start')
    def test_storage_failure_between_records_does_not_repeat(self):
        import pilot_service
        real=pilot_service.save
        def fail_after_record(path,value):
            if value['completed_records']==1:raise OSError('web storage full')
            return real(path,value)
        with patch('pilot_service.save',side_effect=fail_after_record):
            self.command();final=self.finish()
        self.assertEqual(self.owner.attempts,1);self.assertEqual(final['state'],'BLOCKED_ERROR')
    def test_restart_same_directory_denied(self):
        with self.assertRaises(FileExistsError):PilotService(Owner(),self.root)
        self.assertEqual(self.owner.calls,0)
    def test_status_copy_cannot_change_owner_or_budget(self):
        status=self.service.status();status['state']='RUNNING';status['plan']['max_physical_starts_including_CONFIG']=900
        self.assertEqual(self.service.status()['state'],'READY')
        self.assertEqual(self.service.status()['max_records'],4)
    def test_persisted_receipts_and_result_counts(self):
        self.command();final=self.finish();saved=json.loads((self.root/'state.json').read_bytes())
        self.assertEqual(saved['results'],final['results']);self.assertEqual(len(saved['commands']),1)
        self.assertEqual(saved['attempts'],4)
    def test_feedback_is_snapshotted(self):
        self.command();final=self.finish();final['results'][0]['label']=False
        self.assertIs(self.service.status()['results'][0]['label'],True)


if __name__=='__main__':unittest.main()
