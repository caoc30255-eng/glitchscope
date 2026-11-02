"""Real loop/executor exception handlers with modeled buses; no board access."""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import test_local_rule_loop as fixtures
from controlled_trial_executor import ControlledTrialExecutor
from unknown_after_start_pilot import UnknownAfterStartPilot,InjectedSupervisorInterruption


class UnknownPilotTests(unittest.TestCase):
    setUp=fixtures.LocalLoopTests.setUp

    def pilot(self,done=True):
        self.start_calls=0
        self.stop_calls=0
        self.s.mark_capture=NS(used=False,read=lambda a:3 if a==0x20 else 0)
        self.s.start_current=self.actual_start
        self.done_observed=done
        def stop(exc):
            self.stop_calls+=1
            self.s.fault=True
            self.s.control_transport.fault=True
        self.s._stop=stop
        self.s.control_transport.pending_snapshot=lambda **k: {'receiver_running':False,'buffered_words':[]}
        config_call=self.ex.run_next
        def next_record():
            if self.ex.index==0:return config_call()
            return ControlledTrialExecutor.run_next(self.ex)
        self.ex.run_next=next_record
        for rid in (2,3,4):
            shutil.rmtree(self.ex.root/('record_%08x'%rid))
        self.patchers=[
            patch('controlled_trial_executor.rotate_idle_journal'),
            patch('controlled_trial_executor._one',side_effect=self.interrupted_one),
        ]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
        return UnknownAfterStartPilot(self.ex)

    def actual_start(self,**kwargs):
        self.start_calls+=1
        self.s.current.started=True
        self.s.current.done=self.done_observed
        return {'start_command_ack_saved':True,'physical_start_confirmed':True,
                'physical_done_confirmed':self.done_observed,'admission_ticket':'modeled'}

    def interrupted_one(self,*args,**kwargs):
        self.s.current=NS(binding=NS(record_id=2,identity=123),started=False,done=False)
        self.s.start_current(ch0_margin_ticks=1,ch1_margin_ticks=1)
        self.fail('Fixture should interrupt before completion/archive/retirement')

    def test_real_exception_paths_keep_unknown_and_reservation_no_retry(self):
        pilot=self.pilot();original=self.s.start_current
        summary=pilot.run()
        self.assertEqual(self.start_calls,1)
        self.assertEqual(summary['interrupted_record_effect'],'UNKNOWN')
        self.assertIsNone(summary['interrupted_business_label'])
        self.assertEqual(self.ex.index,1);self.assertEqual(self.ex.attempts,2)
        self.assertTrue(self.ex.stopped);self.assertTrue(pilot.loop.stopped)
        self.assertFalse(pilot.loop.done)
        self.assertEqual(self.s.start_current,original)
        self.assertFalse((self.ex.root/'cancelled').exists())
        before=self.stop_calls
        with self.assertRaises(RuntimeError):pilot.run()
        self.assertEqual(self.stop_calls,before)
        self.assertEqual(self.start_calls,1)

    def test_done_true_is_retained_without_business_success(self):
        pilot=self.pilot(done=True);pilot.run()
        point=json.loads((pilot.root/'interruption_point/point.json').read_bytes())
        self.assertTrue(point['physical_done_confirmed'])
        self.assertIsNone(point['business_label'])

    def test_done_false_is_not_promoted_to_done(self):
        pilot=self.pilot(done=False);pilot.run()
        point=json.loads((pilot.root/'interruption_point/point.json').read_bytes())
        self.assertFalse(point['physical_done_confirmed'])

    def test_actual_start_failure_is_not_injected_acceptance(self):
        pilot=self.pilot()
        pilot._original_start=None
        def fail(**kwargs):raise TimeoutError('real transport failed before fixture')
        self.s.start_current=fail
        with self.assertRaises(TimeoutError):pilot.run()
        self.assertFalse(pilot.injected)
        self.assertFalse((pilot.root/'result').exists())

    def test_unconfirmed_start_does_not_certify_injected_branch(self):
        pilot=self.pilot()
        self.s.start_current=lambda **k: {'start_command_ack_saved':True,'physical_start_confirmed':False}
        with self.assertRaises(RuntimeError):pilot.run()
        self.assertFalse(pilot.injected)
        self.assertFalse((pilot.root/'result').exists())

    def test_changed_policy_blocks_before_CONFIG(self):
        pilot=self.pilot()
        (pilot.root/'policy/policy.json').write_bytes(b'changed')
        with self.assertRaises(RuntimeError):pilot.run()
        self.assertEqual(self.actual_calls,0);self.assertEqual(self.start_calls,0)

    def test_interruption_point_save_failure_is_not_success(self):
        pilot=self.pilot()
        from unknown_after_start_pilot import persist_exact
        def save(path,*args,**kwargs):
            if path.name=='interruption_point':raise OSError('disk full')
            return persist_exact(path,*args,**kwargs)
        with patch('unknown_after_start_pilot.persist_exact',side_effect=save):
            with self.assertRaises(OSError):pilot.run()
        self.assertFalse(pilot.injected);self.assertTrue(self.ex.stopped)
        self.assertFalse((pilot.root/'result').exists())

    def test_expected_exception_without_saved_hook_point_rejected(self):
        pilot=self.pilot()
        self.s.start_current=lambda **k: (_ for _ in ()).throw(InjectedSupervisorInterruption('not fixture'))
        with self.assertRaises(RuntimeError):pilot.run()
        self.assertFalse((pilot.root/'result').exists())

    def test_no_mark_or_profile_change_and_same_plan_source(self):
        pilot=self.pilot()
        before=self.ex._frozen_plan,self.ex._frozen_source
        pilot.run()
        self.assertEqual(before,(self.ex._frozen_plan,self.ex._frozen_source))
        self.assertFalse(self.s.mark_capture.used)
        self.assertEqual(len(pilot.loop._history()),1)

    def test_receiver_not_paused_denies_certificate(self):
        pilot=self.pilot()
        self.s.control_transport.pending_snapshot=lambda **k: {'receiver_running':True}
        with self.assertRaises(RuntimeError):pilot.run()
        self.assertFalse((pilot.root/'result').exists())

    def test_result_save_failure_keeps_stopped_no_success(self):
        pilot=self.pilot()
        from unknown_after_start_pilot import persist_exact
        def save(path,*args,**kwargs):
            if path.name=='result':raise OSError('result disk full')
            return persist_exact(path,*args,**kwargs)
        with patch('unknown_after_start_pilot.persist_exact',side_effect=save):
            with self.assertRaises(OSError):pilot.run()
        self.assertTrue(self.ex.stopped);self.assertTrue(self.s.fault)
        self.assertFalse((pilot.root/'result').exists())

if __name__=='__main__':unittest.main()
