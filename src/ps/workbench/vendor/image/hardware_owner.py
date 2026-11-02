"""Adapter over unchanged, previously board-tested record/evidence machinery."""
import copy
import hashlib
import json
from pathlib import Path


class HardwareOwner:
    def __init__(self, session, buses, source, board_lock, package):
        # Kept lazy: software preflight and demo cannot touch FPGA or import PYNQ.
        import fcntl
        from controlled_trial_executor import ControlledTrialExecutor, TrialRequest
        from local_rule_trial_loop import LocalRuleTrialLoop, local_b_rule
        from fault_profile import FaultProfile
        import ch1_evidence_store as store
        expected = session.root.parent/'exclusive.lock'
        if board_lock.closed or Path(board_lock.name).resolve() != expected.resolve():
            raise ValueError('EXISTING_EXCLUSIVE_BOARD_LOCK_REQUIRED')
        fcntl.flock(board_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bytes(source) != bytes(range(256))*3:
            raise ValueError('EXACT_FIXED_SOURCE_REQUIRED')
        self.board_lock = board_lock  # retain ownership through service lifetime
        self.session = session
        self.buses = buses
        self.package = Path(package).resolve()
        self.stop_flag = None
        self.local_rule = local_b_rule
        self.store = store
        self.session_name = session.root.name
        self.executor = ControlledTrialExecutor(session, buses, source, (
            TrialRequest('baseline', 3, -1),
            TrialRequest('reference_mark', 3, -1, FaultProfile(20, 0, 15, 20)),
            TrialRequest('candidate_mark', 4, -1, FaultProfile(20, 0, 15, 20)),
        ), max_physical_starts=4, exclusive_owner=True)
        self.loop = LocalRuleTrialLoop(self.executor, policy=self.decide,
                                      policy_id='web_fixed_four_B_pilot_v0_1')
        self.plan = json.loads(self.executor._frozen_plan)
        self.plan['objective'] = 'B_frame_correct; STM separately reported'
        self.plan['source_scope'] = 'NEW_LIVE_PILOT_PENDING_SOURCE_REVIEW'
        self.code_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            self.package/'pilot_service.py', self.package/'hardware_owner.py',
            self.package/'web_service.py', self.package/'web/pilot.js',
            self.package/'web/pilot.html', self.package/'package_tools.py',
            Path(__import__('controlled_trial_executor').__file__),
            Path(__import__('local_rule_trial_loop').__file__))}

    def decide(self, plan, history):
        proposal = self.local_rule(copy.deepcopy(plan), copy.deepcopy(history))
        if self.stop_flag is not None and self.stop_flag.is_set():
            proposal.update(action='STOP', next_request=None, reason='OPERATOR_STOP_CANCEL_UNSTARTED')
        return proposal

    def step(self, stop_flag):
        self.stop_flag = stop_flag
        for path, expected in self.code_hashes.items():
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('LIVE_GATEWAY_SOURCE_CHANGED')
        output = self.loop.step()
        if output['action'] == 'STOP':
            return output
        rid = self.executor.index
        # This repeats the owner's raw-packet, applied-profile and retirement audit.
        feedback = self.loop._feedback(rid)
        result = copy.deepcopy(output['result'])
        raw_path = self.executor.root/('record_%08x/result/result.json' % rid)
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != feedback['result_sha256']:
            raise ValueError('WEB_RESULT_RECEIPT_CHANGED')
        return dict(action='RECORD_COMPLETED', verified_result=dict(
            feedback=feedback, result=result, result_ref=dict(
                path=raw_path.relative_to(self.session.root).as_posix(),
                sha256=feedback['result_sha256']), source_review='PENDING_SOURCE_REVIEW'))

    def counts(self):
        return dict(attempts=self.executor.attempts, completed=self.executor.index)

    def fail(self, exc):
        self.executor.stopped = True
        self.loop.stopped = True
        self.session._stop(exc)
        from ch1_peer_archive_driver import persist_exact
        import uuid
        persist_exact(self.session.root/'WEB_FAILURE'/uuid.uuid4().hex,
                      {'diagnostic.json': self.store._json(dict(
                          error=repr(exc), attempts=self.executor.attempts,
                          strictly_completed=self.executor.index,
                          label=None, automatic_retry=False, reset_allowed=False))})

    def close_receiver(self):
        self.session.control_transport.close()
