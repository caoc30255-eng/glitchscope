"""One-shot, durable four-record web gateway. No PYNQ imports or IO at import."""
import copy
import hashlib
import json
import os
from pathlib import Path
import threading


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def save(path, value):
    """Durable replacement; failed writes never authorize the next record."""
    path = Path(path)
    temporary = path.with_suffix('.pending')
    with temporary.open('wb') as f:
        f.write(canonical(value) + b'\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(temporary), str(path))
    if os.name != 'nt':
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class PilotService:
    """Owner handles physical records. HTTP can only start once or cancel rest.

    A stop during a record is applied at its next strict retirement boundary;
    it never interrupts UART or fabricates retirement of an inflight record.
    Any exception blocks this instance permanently and preserves null labels.
    """
    def __init__(self, owner, directory, *, limit=4):
        self.owner = owner
        self.root = Path(directory)
        self.root.mkdir(exist_ok=False)  # existing instance must never resume
        self.lock = threading.RLock()
        self.thread = None
        self.stop_requested = threading.Event()
        plan = copy.deepcopy(owner.plan)
        require(type(limit) is int and limit in (4,65) and plan['max_physical_starts_including_CONFIG'] == limit, 'FIXED_FOUR_OR_IMAGE65_PLAN_ONLY'); self.limit=limit
        self.state = dict(schema='PYNQ_WEB_PILOT_V0_1', state='READY', plan=plan,
                          plan_sha256=digest(plan), session=owner.session_name,
                          commands={}, results=[], attempts=0, completed_records=0,
                          inflight=False, stop_requested=False, error=None,
                          new_feedback_source_review='PENDING_SOURCE_REVIEW',
                          real_training_authorized=False, production_billing_finalized=False,
                          automatic_retry=False, max_records=limit)
        self._save()

    def _save(self):
        save(self.root/'state.json', self.state)

    def status(self):
        with self.lock:
            value = copy.deepcopy(self.state)
            value.pop('commands')
            return value

    def _prior(self, key, body):
        require(type(key) is str and 8 <= len(key) <= 128, 'IDEMPOTENCY_KEY_REQUIRED')
        prior = self.state['commands'].get(key)
        if prior:
            require(prior['body_sha256'] == digest(body), 'IDEMPOTENCY_CONFLICT')
            return copy.deepcopy(prior['receipt'])

    def command(self, action, key, plan_sha256):
        require(action in ('start', 'stop'), 'FIXED_START_OR_STOP_ONLY')
        body = dict(action=action, plan_sha256=plan_sha256)
        with self.lock:
            require(plan_sha256 == self.state['plan_sha256'], 'FIXED_PLAN_MISMATCH')
            previous = self._prior(key, body)
            if previous is not None:
                return previous
            current = self.state['state']
            if action == 'start':
                require(current == 'READY', 'PILOT_ALREADY_USED_OR_BLOCKED_NO_RESUME')
                self.state['state'] = 'RUNNING'
            else:
                require(current in ('READY', 'RUNNING', 'STOPPING'), 'PILOT_TERMINAL_NO_RESUME')
                self.stop_requested.set()
                self.state.update(state='STOPPING', stop_requested=True)
            receipt = dict(accepted=True, action=action, session=self.state['session'],
                           plan_sha256=plan_sha256, idempotency_key=key,
                           record_limit=self.limit, no_new_quota=True)
            self.state['commands'][key] = dict(body_sha256=digest(body), receipt=receipt)
            try:
                self._save()  # fsync intent before worker can call owner
            except BaseException:
                self.state['commands'].pop(key, None)
                self.state.update(state='BLOCKED_STORAGE', error='INTENT_SAVE_FAILED')
                raise
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True,
                                               name='bounded-web-pilot')
                self.thread.start()
            return copy.deepcopy(receipt)

    def _run(self):
        try:
            # Four physical records, followed by one mandatory STOP decision.
            for _ in range(self.limit+1):
                with self.lock:
                    require(self.state['completed_records'] <= self.limit, 'LIMIT_EXCEEDED')
                    self.state['inflight'] = True
                    self._save()
                output = self.owner.step(self.stop_requested)
                with self.lock:
                    counts = self.owner.counts()
                    require(0 <= counts['completed'] <= counts['attempts'] <= self.limit, 'COUNTER_SCOPE')
                    self.state.update(attempts=counts['attempts'], completed_records=counts['completed'],
                                      inflight=False)
                    if output['action'] == 'RECORD_COMPLETED':
                        self.state['results'].append(copy.deepcopy(output['verified_result']))
                        require(len(self.state['results']) == counts['completed'], 'RESULT_SEQUENCE')
                    elif output['action'] == 'STOP':
                        self.state.update(state='STOPPED' if self.stop_requested.is_set() else 'COMPLETE',
                                          summary=copy.deepcopy(output['summary']))
                    else:
                        raise ValueError('OWNER_ACTION')
                    self._save()  # failure here blocks rather than repeating a physical record
                    if self.state['state'] in ('STOPPED', 'COMPLETE'):
                        return
            raise RuntimeError('BOUNDED_LOOP_DID_NOT_STOP')
        except BaseException as exc:
            # Actual owner preserves intent/raw evidence even if web storage fails.
            try:
                self.owner.fail(exc)
            except BaseException:
                pass  # raw executor evidence remains authoritative on storage failure
            with self.lock:
                counts = self.owner.counts()
                unresolved = counts['attempts'] > len(self.state['results'])
                self.state.update(state='BLOCKED_UNKNOWN' if unresolved else 'BLOCKED_ERROR',
                                  attempts=counts['attempts'], inflight=False,
                                  error=repr(exc), unresolved_attempt=unresolved,
                                  unresolved_label=None, automatic_retry=False)
                try:
                    self._save()
                except BaseException:
                    pass
        finally:
            try:
                self.owner.close_receiver()
            except BaseException as exc:
                with self.lock:
                    self.state['receiver_close_error'] = repr(exc)
                    try:
                        self._save()
                    except BaseException:
                        pass

    def join(self, timeout=0):
        if self.thread:
            self.thread.join(timeout)
        return self.thread is None or not self.thread.is_alive()
