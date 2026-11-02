"""Opt-in supervisor exception fixture after a real START return.

No UART/clock/pin changes. This is NOT a real communication fault or power loss.
The unchanged loop and executor must preserve UNKNOWN and prohibit continuation.
"""
from pathlib import Path
import json
import threading
from local_rule_trial_loop import LocalRuleTrialLoop, _require
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store


class InjectedSupervisorInterruption(RuntimeError):
    pass


class UnknownAfterStartPilot:
    def __init__(self, executor):
        _require(executor.index == executor.attempts == 0 and not executor.stopped,
                 'Fresh executor required; no resume')
        self.executor = executor
        self.session = executor.session
        _require(not self.session.fault and self.session.current is None,
                 'Fresh healthy initialized session required')
        self.root = self.session.root / 'UNKNOWN_PILOT'
        self.root.mkdir(exist_ok=False)
        self.loop = LocalRuleTrialLoop(executor)
        self.used = False
        self.injected = False
        self.summary = None
        self._lock = threading.Lock()
        self._source = Path(__file__).resolve()
        self._source_sha = store.sha(self._source.read_bytes())
        self.policy = {
            'schema': 'UNKNOWN_AFTER_START_POLICY_V0_1',
            'source_sha256': self._source_sha,
            'plan_sha256': store.sha(executor._frozen_plan),
            'target_record_id': 2, 'target_client_request_id': 'baseline',
            'injection': 'PS_EXCEPTION_AFTER_REAL_START_RETURN_BEFORE_COMPLETION_ARCHIVE',
            'actual_UART_fault_injected': False, 'power_loss_injected': False,
            'automatic_retry_allowed': False, 'refund_or_new_quota_created': False,
            'training_authorized': False, 'production_billing_finalized': False,
        }
        plan = json.loads(executor._frozen_plan)
        _require(plan['max_physical_starts_including_CONFIG'] == 4 and
                 plan['requests'][0] == {'client_request_id': 'baseline',
                    'receiver_B': {'d': 3, 's': -1}, 'fault': None},
                 'Frozen four-slot plan with unmarked baseline required')
        self._policy_bytes = store._json(self.policy)
        persist_exact(self.root/'policy', {'policy.json': self._policy_bytes})
        self.session.journal.record('unknown_pilot_policy_saved', **self.policy)

    def _verify_policy(self):
        _require(store.sha(self._source.read_bytes()) == self._source_sha,
                 'Unknown fixture source changed')
        directory = self.root/'policy'
        manifest = json.loads((directory/'committed.json').read_bytes())
        _require(manifest['files'] == {'policy.json': store.sha(self._policy_bytes)} and
                 (directory/'policy.json').read_bytes() == self._policy_bytes,
                 'Unknown fixture policy changed')
        self.executor._verify_plan()

    def _counts(self):
        ex = self.executor
        return {'retire_count': int(ex.buses['SYS'].read(0x18)),
                'grant_count': int(ex.buses['SYS'].read(0x1c)),
                'completed_records': ex.index, 'attempts_reserved': ex.attempts,
                'saved_results': len(ex.results)}

    def _install(self):
        self._original_start = self.session.start_current

        def interrupted_start(*args, **kwargs):
            self._verify_policy()
            ex = self.executor
            owner = self.session.current
            _require(not self.injected and ex.index == 1 and ex.attempts == 2 and
                     owner is not None and owner.binding.record_id == 2,
                     'Injection must target the first unmarked ITEM once')
            actual = self._original_start(*args, **kwargs)
            _require(isinstance(actual, dict) and actual.get('start_command_ack_saved') is True and
                     actual.get('physical_start_confirmed') is True and owner.started is True,
                     'Actual START not confirmed; do not claim injected-path acceptance')
            point = {'schema': 'UNKNOWN_AFTER_START_POINT_V0_1',
                     'record_id': 2, 'identity_hex': '%064x' % owner.binding.identity,
                     'actual_START_return': actual,
                     'physical_start_confirmed': bool(owner.started),
                     'physical_done_confirmed': bool(owner.done),
                     'business_label': None, 'record_completion_acceptance': 'UNKNOWN',
                     'source_sha256': self._source_sha,
                     'scope': 'Deliberate supervisor exception; retain all known physical facts'}
            persist_exact(self.root/'interruption_point', {'point.json': store._json(point)})
            self.session.journal.record('unknown_pilot_interruption_point_saved', **point)
            self.injected = True
            raise InjectedSupervisorInterruption('Controlled PS exception after actual START; retain UNKNOWN, no retry')

        self._wrapped_start = interrupted_start
        self.session.start_current = interrupted_start

    def run(self):
        if not self._lock.acquire(False):
            raise RuntimeError('Concurrent UNKNOWN pilot denied')
        installed = False
        entered = False
        try:
            _require(not self.used, 'UNKNOWN pilot already used; no retry/resume')
            self.used = True
            entered = True
            self._verify_policy()
            self.loop.step()  # CONFIG must genuinely complete and retire first.
            _require(self.executor.index == self.executor.attempts == 1,
                     'CONFIG did not finish exactly once')
            self._install(); installed = True
            try:
                self.loop.step()
            except InjectedSupervisorInterruption:
                _require(self.injected, 'Expected exception without saved interruption point')
            else:
                raise RuntimeError('Expected supervisor interruption did not occur')
            validated = self._verify_stopped()
            persist_exact(self.root/'result', {'result.json': store._json(validated)})
            self.summary = validated
            return self.summary
        except Exception as exc:
            # Persisted policy/point remain; no success certificate is fabricated.
            if entered:
                self.executor.stopped = True
                self.loop.stopped = True
                self.session._stop(exc)
            raise
        finally:
            if installed and self.session.start_current is self._wrapped_start:
                self.session.start_current = self._original_start
            self._lock.release()

    def _verify_stopped(self):
        ex = self.executor
        self._verify_policy()
        _require(self.loop.stopped and not self.loop.done and ex.stopped and self.session.fault,
                 'Original fail-stop guards did not latch')
        before = self._counts()
        _require(before == {'retire_count': 1, 'grant_count': 1, 'completed_records': 1,
                            'attempts_reserved': 2, 'saved_results': 1},
                 'Interrupted ITEM must remain reserved and unretired')
        diagnostics = {}
        for name, root, field in (('executor', ex.root, 'execution_effect'),
                                  ('loop', self.loop.root, 'effect')):
            paths = list(root.glob('STOP_*/diagnostic.json'))
            _require(len(paths) == 1, 'Exactly one original UNKNOWN diagnostic required: '+name)
            diagnostic = json.loads(paths[0].read_bytes())
            _require(diagnostic[field] == 'UNKNOWN' and diagnostic['label'] is None and
                     diagnostic['automatic_retry_allowed'] is False,
                     'Original diagnostic must retain UNKNOWN without a business label')
            diagnostics[name] = {'relative_path': str(paths[0].relative_to(self.session.root)),
                                 'sha256': store.sha(paths[0].read_bytes())}
        _require(not (ex.root/'record_00000002/result').exists() and
                 not (ex.root/'record_00000003').exists() and
                 not (ex.root/'record_00000004').exists() and
                 not (ex.root/'cancelled').exists(),
                 'No completed second result, later record or idle cancellation allowed')
        rejections = {}
        for name, operation in (('loop_run', self.loop.run), ('loop_step', self.loop.step),
                                ('executor_run_next', ex.run_next)):
            try:
                operation()
            except RuntimeError as exc:
                rejections[name] = str(exc)
            else:
                raise RuntimeError('Stopped entry allowed continuation: '+name)
        _require(self._counts() == before, 'Rejection checks changed counters')
        capture = self.session.mark_capture
        raw = {name: capture.read(address) for name, address in
               (('status',8), ('sample_count',12), ('trigger_offset',16), ('live_sample',0x20))}
        _require(capture.used is False and raw['status'] == raw['sample_count'] ==
                 raw['trigger_offset'] == 0, 'Snapshot unexpectedly armed')
        self.session.journal.verify()
        receiver = self.session.control_transport
        snapshot = receiver.pending_snapshot(limit=65536)
        _require(receiver.fault is True and snapshot['receiver_running'] is False,
                 'Stopped UART receiver must remain paused, with its buffered evidence retained')
        point_bytes = (self.root/'interruption_point/point.json').read_bytes()
        point = json.loads(point_bytes)
        return {'schema':'UNKNOWN_AFTER_START_RESULT_V0_1', 'session':self.session.root.name,
                'test_mechanism':'CONTROLLED_PS_EXCEPTION_NOT_UART_FAULT_OR_POWER_LOSS',
                'interrupted_record_id':2, 'interrupted_business_label':None,
                'interrupted_record_effect':'UNKNOWN', 'interrupted_record_known_START_lower_bound':1,
                'known_physical_facts':point, 'interruption_point_sha256':store.sha(point_bytes),
                'paused_receiver_snapshot':snapshot,
                'before_rejection_checks':before, 'after_rejection_checks':self._counts(),
                'original_diagnostics':diagnostics, 'post_stop_rejections':rejections,
                'raw_capture_unarmed_readback':raw, 'automatic_retry_allowed':False,
                'refund_or_new_quota_created':False, 'remaining_plan_reusable':False,
                'power_loss_recovery_verified':False, 'production_billing_finalized':False,
                'training_authorized':False}
