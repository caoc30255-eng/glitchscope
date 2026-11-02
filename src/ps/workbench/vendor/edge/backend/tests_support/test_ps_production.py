"""Production host ordering tests: MMIO/control models plus actual file fsync.

These are software tests, not HDL, PYNQ, MCU or hardware acceptance.
"""
from pathlib import Path
import sys, unittest, json, uuid
from unittest.mock import patch, Mock
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'host'), str(ROOT/'tests')]
import test_verified_retirement as r
from test_completion_ledger import reply
from test_runtime_driver import RuntimeModel
from ch1_runtime_driver import CH1RuntimeDriver, ReleaseTicket
from ch1_control_session import ApplicationJournal
from h1_upload_ledger import UploadLedger
from h1_axi_driver import H1Transport
from ps_system_gate import SystemGate
from ps_hello import HelloSession
from ps_candidate_session import CandidateSession, BANKS
from test_application_owner import PeerCache


class SysBus:
    def __init__(self, case):
        self.c = case; self.permission = 0; self.count = 0
        self.fault = False; self.writes = []; self.lost = False; self.late_fault = False
        self.bad_retire_count = False
        original = case.runtime_bus.retire
        def retire():
            before = case.runtime_bus.count
            original()
            if case.runtime_bus.count != before:
                self.permission = 0; case.runtime_bus.capacity = False
        case.runtime_bus.retire = retire
    def read(self, a):
        b = self.c.runtime_bus
        live = bool(b.live and not b.count)
        if a == 0: return 0x48375331
        if a == 8: return 100000000
        if a == 4:
            return self.permission | (0x82 if self.fault else 0) | (
                4 if self.c.ch0_bus.bound and not self.c.ch0_bus.released else 0) | (
                0x10 if live else 0) | (0x20 if live and b.main else 0) | (
                0x40 if live and b.physical_done else 0)
        if a == 0x0c: return b.epoch
        if a == 0x10: return self.c.binding.record_id
        if a == 0x18: return b.count + int(self.bad_retire_count)
        if a == 0x1c: return self.count
        if a == 0x20: return self.permission
        raise AssertionError(a)
    def write(self, a, v):
        self.writes.append((a, v))
        assert a == 0x20 and v == 1
        if self.late_fault:
            self.fault = True; raise RuntimeError('actual SYS denied late fault')
        assert self.c.ch0_bus.released and self.c.main.effects == 1
        assert self.c.runtime_bus.physical_done
        lines = [json.loads(x) for x in self.c.journal.path.read_text().splitlines()]
        assert any(x['event'] == 'SYS_grant_intent' for x in lines)
        self.permission = 1; self.count += 1; self.c.runtime_bus.capacity = True
        if self.lost: raise OSError('Grant executed; reply lost')


class ProductionRetirementTests(unittest.TestCase):
    issue = r.RetirementTests.issue
    deliver = r.RetirementTests.deliver
    owner = r.RetirementTests.owner
    start = r.RetirementTests.start
    arm = r.RetirementTests.arm
    begin = r.RetirementTests.begin
    retire = r.RetirementTests.retire
    ready = r.RetirementTests.ready
    def setUp(self):
        r.RetirementTests.setUp(self)
    def attach(self):
        self.runtime_bus.capacity = False
        self.sysbus = SysBus(self)
        self.gate = SystemGate(self.sysbus, self.journal)
        self.runtime.system_gate = self.gate

    def test_real_driver_save_then_SYS_grant_then_retirement_and_READY(self):
        self.begin(); self.attach()
        self.retire()
        self.assertEqual(self.sysbus.writes, [(0x20, 1)])
        self.assertEqual(self.sysbus.count, 1)
        self.assertEqual(self.runtime_bus.count, 1)
        self.assertEqual(self.sysbus.permission, 0)
        self.assertEqual(self.upload.credit, 0)
        self.assertTrue(self.ready()['next_item_allowed'])

    def test_session_entry_wraps_actual_three_party_retirement(self):
        self.begin(); self.attach()
        ps = CandidateSession.__new__(CandidateSession)
        ps.fault = False; ps.current = self.o; ps.ticket = None
        ps.peer = self.peer; ps.ch0_archive = self.ch0_archive
        ps.mapping = self.mapping; ps.reader = self.reader; ps.archive = self.archive
        ps.upload = self.upload; ps.journal = self.journal; ps.config_owner = None
        ps.retire_current()
        self.status_bus.events = [reply(self.inner, 0x80, seq=0, crc=0, credit=1)]
        self.assertTrue(ps.poll_next_credit()['next_item_allowed'])
        self.assertIs(ps.config_owner, self.o)
        self.assertIsNone(ps.current)
        self.assertEqual(self.sysbus.count, 1)

    def test_session_retired_poll_cannot_consume_next_READY(self):
        self.begin(); self.attach(); self.retire()
        ps = CandidateSession.__new__(CandidateSession)
        ps.fault = False; ps.current = self.o
        self.status_bus.events = [reply(self.inner, 0x80, seq=0, crc=0, credit=1)]
        with self.assertRaises(RuntimeError): ps.poll_current()
        self.assertEqual(len(self.status_bus.events), 1)

    def test_session_next_credit_before_local_retire_does_no_IO(self):
        self.begin()
        ps = CandidateSession.__new__(CandidateSession)
        ps.fault = False; ps.current = self.o
        before = len(self.wire.requests)
        with self.assertRaises(RuntimeError): ps.poll_next_credit()
        self.assertEqual(len(self.wire.requests), before)

    def test_CH0_open_cannot_grant(self):
        self.begin(); self.attach(); self.ch0_bus.closed = False
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.sysbus.writes, [])

    def test_no_actual_DONE_cannot_grant(self):
        self.begin(); self.attach(); self.runtime_bus.physical_done = False
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.sysbus.writes, [])
        self.assertTrue(self.ch0_bus.released)

    def test_CH1_fsync_failure_never_grants(self):
        self.begin(); self.attach()
        with patch.object(r.store, '_write', side_effect=OSError('CH1 disk failure')):
            with self.assertRaises(OSError): self.retire()
        self.assertEqual(self.sysbus.writes, [])
        self.assertEqual(self.runtime_bus.count, 0)

    def test_SYS_fault_before_grant_no_write(self):
        self.begin(); self.attach(); self.sysbus.fault = True
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.sysbus.writes, [])

    def test_same_command_edge_fault_denies_release(self):
        self.begin(); self.attach(); self.sysbus.late_fault = True
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.runtime_bus.count, 0)
        self.assertEqual(self.upload.credit, 0)

    def test_lost_SYS_reply_never_rewrites_or_releases(self):
        self.begin(); self.attach(); self.sysbus.lost = True
        with self.assertRaises(OSError): self.retire()
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.sysbus.writes, [(0x20, 1)])
        self.assertEqual(self.runtime_bus.count, 0)
        self.assertFalse(any(a == 0xa8 for a, v in self.runtime_bus.writes))

    def test_grant_intent_fsync_failure_no_grant(self):
        self.begin(); self.attach(); original = self.journal.record
        def fail(event, **kw):
            if event == 'SYS_grant_intent': raise OSError('intent fsync failed')
            return original(event, **kw)
        with patch.object(self.journal, 'record', side_effect=fail):
            with self.assertRaises(OSError): self.retire()
        self.assertEqual(self.sysbus.writes, [])

    def test_grant_count_wrap_denied(self):
        self.begin(); self.attach(); self.sysbus.count = 0xffffffff
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.sysbus.writes, [])

    def test_saved_confirmation_crc_changed_no_grant(self):
        self.begin(); self.attach(); original = self.gate.grant_saved_release
        def changed(runtime, binding, saved):
            saved = dict(saved); saved['samples_crc'] ^= 1
            return original(runtime, binding, saved)
        self.gate.grant_saved_release = changed
        with self.assertRaises(ValueError): self.retire()
        self.assertEqual(self.sysbus.writes, [])

    def test_no_main_proof_submission_no_grant(self):
        self.begin(); self.attach(); original = self.gate.grant_saved_release
        def missing(runtime, binding, saved):
            saved = dict(saved); saved['hardware_proof_command_submitted'] = False
            return original(runtime, binding, saved)
        self.gate.grant_saved_release = missing
        with self.assertRaises(RuntimeError): self.retire()
        self.assertEqual(self.sysbus.writes, [])

    def test_SYS_retirement_count_mismatch_no_peer_retirement(self):
        self.begin(); self.attach(); original = self.gate.verify_retired
        def wrong(b, count):
            self.sysbus.bad_retire_count = True; original(b, count)
        self.gate.verify_retired = wrong
        with self.assertRaises(RuntimeError): self.retire()
        self.assertFalse(self.o.peer_retired)
        self.assertEqual(self.upload.credit, 0)

    def test_CH1_saved_file_changed_during_intent_no_grant(self):
        self.begin(); self.attach(); original = self.journal.record
        def tamper(event, **kw):
            original(event, **kw)
            if event == 'SYS_grant_intent':
                next((self.root/'main').glob('*/samples.bin')).write_bytes(b'changed')
        with patch.object(self.journal, 'record', side_effect=tamper):
            with self.assertRaises(ValueError): self.retire()
        self.assertEqual(self.sysbus.writes, [])


class ReceiptLatencyTests(unittest.TestCase):
    def test_count_visible_before_busy_clear_polls_without_new_command(self):
        bus = RuntimeModel(); driver = CH1RuntimeDriver(bus, poll_limit=5)
        driver.activate_epoch(1)
        identity = r.store.descriptor_decode(r.fixture()[0])['identity']
        binding = driver.arm(kind=1, record_id=17, identity=identity,
            delay_ticks=50, duration_ticks=100)
        ticket = ReleaseTicket(binding, 0)
        bus.count = 1; bus.pending = True
        original = bus.read; reads = [0]
        def delayed(a):
            if a == 4:
                reads[0] += 1
                if reads[0] >= 3: bus.live = bus.pending = False
            return original(a)
        bus.read = delayed; before = list(bus.writes)
        self.assertTrue(driver.wait_retirement(ticket)['hardware_retirement_verified'])
        self.assertEqual(bus.writes, before)

    def test_count_visible_but_busy_never_clears_times_out(self):
        bus = RuntimeModel(); driver = CH1RuntimeDriver(bus, poll_limit=3)
        driver.activate_epoch(1)
        identity = r.store.descriptor_decode(r.fixture()[0])['identity']
        b = driver.arm(kind=1, record_id=17, identity=identity, delay_ticks=50, duration_ticks=100)
        bus.count = 1; bus.pending = True
        with self.assertRaises(TimeoutError): driver.wait_retirement(ReleaseTicket(b, 0))


class ProductionWindowTests(unittest.TestCase):
    issue = r.RetirementTests.issue
    deliver = r.RetirementTests.deliver
    owner = r.RetirementTests.owner
    arm = r.RetirementTests.arm
    def setUp(self):
        r.RetirementTests.setUp(self)
        ticket = self.issue()
        self.ps = CandidateSession.__new__(CandidateSession)
        self.ps.fault = False; self.ps.current = self.owner(); self.ps.ticket = ticket
        self.ps.coordinator = self.coordinator; self.ps.ch0 = self.ch0
        self.ps.runtime = self.runtime; self.ps.upload = self.upload; self.ps.journal = self.journal
    def test_each_actual_clock_window_open_does_not_send_START(self):
        before = len(self.wire.requests)
        result = self.ps.window_readiness(ch0_margin_ticks=50, ch1_margin_ticks=50)
        self.assertTrue(result['windows_open'])
        self.assertFalse(result['START_sent'])
        self.assertEqual(len(self.wire.requests), before)
    def test_before_CH0_start_is_waiting_without_fault_or_START(self):
        self.ch0_bus.tick = 80; self.ch0_bus.flags = 9; self.ch0_bus.live = 1
        result = self.ps.window_readiness(ch0_margin_ticks=50, ch1_margin_ticks=50)
        self.assertFalse(result['windows_open'])
        self.assertFalse(self.ps.fault)
    def test_deadline_margin_exhausted_stops_without_START(self):
        self.ch0_bus.tick = 4070
        before = len(self.wire.requests)
        with self.assertRaises(RuntimeError):
            self.ps.window_readiness(ch0_margin_ticks=50, ch1_margin_ticks=50)
        self.assertTrue(self.ps.fault)
        self.assertEqual(len(self.wire.requests), before)


class HelloBus:
    def __init__(self, upload):
        self.upload = upload; self.queue = []; self.ticket = 0; self.held = False
        self.mask = 0; self.packet = []; self.sealed = False; self.launched = False
        self.bad_credit = False; self.bad_crc = False; self.bad_mask = False
        self.no_reply = False; self.release_lost = False; self.writes = []
        self.on_launch = None; self.defer_reply = False
    def read(self, a):
        if a == 0: return 0x48315431
        if a == 4: return (2 if self.sealed else 1) | (8 if self.queue else 0) | (16 if self.held else 0)
        if a == 0x20: return len(self.packet)
        if a == 0x40: self.mask |= 1; return self.ticket
        if a == 0x44: self.mask |= 2; return 0x112
        if 0x48 <= a <= 0x58:
            i = (a - 0x48)//4; self.mask |= 1 << (i+2)
            return int.from_bytes((self.queue[0]+b'\0\0')[i*4:i*4+4], 'big')
        if a == 0x5c: return 63 if self.bad_mask else self.mask
        raise AssertionError(a)
    def write(self, a, v):
        self.writes.append((a, v))
        if a == 0x10:
            self.packet.append(v & 255); self.sealed = bool(v & 256)
        elif a == 0x18:
            self.launched = True; self.sealed = False
            assert bytes(self.packet) == self.upload.current[3]
            if self.on_launch is not None: self.on_launch()
            if not self.no_reply and not self.defer_reply:
                raw = reply(b'', 0x80, seq=0, crc=0, credit=0 if self.bad_credit else 1)
                self.queue.append(raw[:-1]+bytes([raw[-1]^1]) if self.bad_crc else raw)
        elif a == 0x30: self.held = True; self.ticket += 1; self.mask = 0
        elif a == 0x34:
            assert self.mask == 127 and v == self.ticket
            records = [json.loads(x) for x in self.upload.path.read_text().splitlines()]
            assert any(x['event'] == 'hello_ready' for x in records)
            if self.release_lost: raise OSError('Lost saved-release reply')
            self.queue.pop(0); self.held = False
        else: raise AssertionError(a)


class HelloTests(unittest.TestCase):
    def setUp(self):
        root = ROOT/'evidence/offline_production_tests'/uuid.uuid4().hex
        self.upload = UploadLedger(root/'upload', 0x10203040); self.addCleanup(self.upload.close)
        self.journal = ApplicationJournal(root/'journal', 1); self.addCleanup(self.journal.close)
        self.bus = HelloBus(self.upload)
        self.hello = HelloSession(H1Transport(self.bus), self.upload, self.journal, poll_limit=3)
    def test_one_real_saved_READY_no_completion_and_no_second_hello(self):
        self.assertEqual(self.hello.establish(), {'session_established': True, 'completion': False})
        self.assertEqual(self.upload.credit, 1); self.assertFalse(self.upload.done)
        before = list(self.bus.writes)
        with self.assertRaises(RuntimeError): self.hello.establish()
        self.assertEqual(self.bus.writes, before)
    def test_zero_credit_ready_retained(self):
        self.bus.bad_credit = True
        with self.assertRaises(ValueError): self.hello.establish()
        self.assertTrue(self.bus.held); self.assertEqual(self.upload.credit, 0)
    def test_bad_crc_retained_no_release(self):
        self.bus.bad_crc = True
        with self.assertRaises(ValueError): self.hello.establish()
        self.assertTrue(self.bus.held)
        self.assertFalse(any(a == 0x34 for a, v in self.bus.writes))
    def test_incomplete_reads_never_release(self):
        self.bus.bad_mask = True
        with self.assertRaises(RuntimeError): self.hello.establish()
        self.assertTrue(self.bus.held); self.assertEqual(self.upload.credit, 0)
    def test_missing_ready_timeout_no_second_send(self):
        self.bus.no_reply = True
        with self.assertRaises(TimeoutError): self.hello.establish()
        self.assertEqual(sum(a == 0x18 for a, v in self.bus.writes), 1)
    def test_fsync_before_hello_failure_never_transmits(self):
        with patch.object(self.journal, 'record', side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.hello.establish()
        self.assertEqual(self.bus.writes, [])
    def test_lost_release_reply_locks_credit_no_resend(self):
        self.bus.release_lost = True
        with self.assertRaises(OSError): self.hello.establish()
        self.assertEqual(self.upload.credit, 0)
        with self.assertRaises(RuntimeError): self.hello.establish()

    def test_unconfirmed_peer_store_does_not_consume_READY(self):
        self.hello.save_peer = lambda: {'peer_store_verified': False}
        with self.assertRaises(RuntimeError): self.hello.establish()
        self.assertFalse(any(a == 0x30 for a, v in self.bus.writes))
        self.assertEqual(sum(a == 0x18 for a, v in self.bus.writes), 1)
        self.assertTrue(self.upload.fault)

    def test_peer_disk_failure_does_not_consume_READY_or_resend(self):
        def fail(): raise OSError('peer archive disk failed')
        self.hello.save_peer = fail
        with self.assertRaises(OSError): self.hello.establish()
        self.assertFalse(any(a == 0x30 for a, v in self.bus.writes))
        with self.assertRaises(RuntimeError): self.hello.establish()


class SessionPreflightTests(unittest.TestCase):
    def test_CONFIG_peer_saved_before_waiting_ACCEPTED(self):
        class Delivered(Exception): pass
        ps = CandidateSession.__new__(CandidateSession)
        ps.fault = False; ps.current = None; ps.config_owner = None
        ps.local_epoch = 1; ps.peer_epoch = 101; ps.session = 7; ps.hello_record_id = 0xffffffff
        ps.upload = Mock(session=7, current=(2, 1, b'x', b'packet'))
        ps.observer = Mock()
        ps.observer.snapshot.return_value = {'next_generation': 1}
        ps.journal = Mock(); ps._stop = Mock(); ps.completion = Mock(accepted=False)
        order = []; proof = {'peer_store_verified': True}
        ps.transport = Mock()
        ps.transport.send_prepared.side_effect = lambda _: order.append('send')
        ps._archive_upload = Mock(side_effect=lambda _: order.append('peer_saved') or proof)
        ps.reader = Mock()
        def accepted():
            order.append('ACCEPTED'); ps.completion.accepted = True
        ps.reader.read_and_preserve.side_effect = accepted
        ps.coordinator = Mock()
        def issue(*args, **kwargs):
            self.assertIs(kwargs['deliver_and_archive'](None), proof)
            raise Delivered()
        ps.coordinator.issue.side_effect = issue
        ps.limit = 3
        codec = Mock()
        codec.decode_config.return_value = {'valid': True, 'run_id': 1, 'image_id': 1}
        with patch('ps_candidate_session._codec', return_value=codec):
            with self.assertRaises(Delivered):
                ps.prepare_flight(2, b'x', record_id=1, d=3, s=-1,
                    ch1_delay_ticks=100, ch1_duration_ticks=100,
                    ch0_delay_ticks=100, ch0_duration_ticks=100)
        self.assertEqual(order, ['send', 'peer_saved', 'ACCEPTED'])

    def test_bad_profile_or_window_budget_fails_before_device_IO(self):
        ps = CandidateSession.__new__(CandidateSession)
        ps.fault = False; ps.coordinator = object(); ps.current = None
        params = dict(record_id=1, d=3, s=-1, ch1_delay_ticks=100,
            ch1_duration_ticks=100, ch0_delay_ticks=100, ch0_duration_ticks=100)
        with self.assertRaises(ValueError):
            ps.prepare_flight(2, b'', **{**params, 's': 2})
        with self.assertRaises(ValueError):
            ps.prepare_flight(2, b'', **{**params, 'ch0_delay_ticks': 0})
        self.assertFalse(ps.fault)

    def test_wrong_bank_ID_no_writes_or_session_files(self):
        class Bus:
            def __init__(self, identity): self.identity = identity; self.writes = []
            def read(self, a): return self.identity
            def write(self, a, v): self.writes.append((a, v))
        buses = {name: Bus(i) for name, (_, _, i) in BANKS.items()}
        buses['MAP'].identity = 0
        root = ROOT/'evidence/offline_production_tests'/uuid.uuid4().hex
        with self.assertRaises(RuntimeError): CandidateSession(buses, root,
            local_epoch=1, peer_epoch=101, session=7, control_epoch=3, exclusive_owner=True)
        self.assertFalse(root.exists())
        self.assertFalse(any(b.writes for b in buses.values()))

    def boot(self, reject=False, authorized_status=0x221):
        class EmptyBank:
            def __init__(self, identity): self.identity = identity
            def read(self, a): return self.identity if a == 0 else 0
            def write(self, a, v): raise AssertionError('unexpected bank write')
        class FreshSys(EmptyBank):
            def read(self, a):
                if a == 8: return 100000000
                return super().read(a)
        class Remote:
            def __init__(self): self.reg = {}; self.active = False; self.cache = None
            def read(self, a):
                if a == 0: return 0x48354531
                if a == 0xd00: return 0x48505131
                if a == 4:
                    if self.cache is not None and self.cache.sealed: return 0x87
                    return authorized_status if self.active else 0x20
                if a in (0x24, 0x28, 0x2c):
                    return self.reg[{0x24:0x10, 0x28:0x14, 0x2c:0x18}[a]] if self.active else 0
                if self.cache is not None: return self.cache.read(a)
                raise AssertionError(a)
            def write(self, a, v):
                if a == 0x1c: self.active = not reject
                elif a in (0x10, 0x14, 0x18): self.reg[a] = v
                else:
                    self.cache.write(a, v)
                    if a == 0x64 and not self.cache.sealed:
                        h1.queue.append(reply(b'', 0x80, seq=0, crc=0, credit=1))
        root = ROOT/'evidence/offline_production_tests'/uuid.uuid4().hex
        buses = {name: EmptyBank(i) for name, (_, _, i) in BANKS.items()}
        buses['SYS'] = FreshSys(0x48375331)
        buses['CTRL'] = RuntimeModel()
        buses['CH0'] = r.reg.Bus()
        buses['PROFILE'] = r.v.profilemodel.Bus()
        h1 = HelloBus(None); buses['H1'] = h1
        ps = CandidateSession(buses, root, local_epoch=1, peer_epoch=101,
            session=0x10203040, control_epoch=3, exclusive_owner=True, poll_limit=3)
        self.addCleanup(ps.close); h1.upload = ps.upload
        remote = Remote()
        h1.defer_reply = True
        h1.on_launch = lambda: setattr(remote, 'cache', PeerCache(root/'peer', ps.upload, epoch=101))
        wire = r.v.app.WirePeer(remote, 0)
        return ps, wire, buses

    def test_session_initializes_real_driver_namespaces_and_single_saved_HELLO(self):
        ps, wire, buses = self.boot()
        ps.initialize(wire)
        self.assertEqual(ps.runtime._read(8), 1)
        self.assertEqual(ps.peer.read(0x24), 101)
        self.assertEqual(ps.peer.read(4), 0x221)
        self.assertEqual(ps.upload.credit, 1)
        self.assertFalse(ps.completion.done)
        self.assertEqual(sum(a == 0x18 for a, v in buses['H1'].writes), 1)
        self.assertIs(ps.runtime.system_gate, ps.gate)
        self.assertEqual(buses['SYS'].read(0x20), 0)
        records = [json.loads(line) for line in ps.upload.path.read_text().splitlines()]
        events = [row['event'] for row in records]
        self.assertLess(events.index('peer_raw_saved'), events.index('hello_ready'))
        self.assertEqual(wire.cache.cache.meta[5:7], [0, 0xffff])
        self.assertEqual(wire.cache.cache.last_id, 0xffffffff)

    def test_HELLO_peer_fsync_failure_holds_raw_and_has_no_READY(self):
        ps, wire, buses = self.boot()
        with patch('ch1_peer_archive_driver.persist_exact', side_effect=OSError('disk')):
            with self.assertRaises(OSError): ps.initialize(wire)
        self.assertTrue(wire.cache.cache.sealed)
        self.assertEqual(buses['H1'].queue, [])
        self.assertEqual(sum(a == 0x18 for a, v in buses['H1'].writes), 1)
        self.assertTrue(ps.fault)

    def test_HELLO_lost_peer_proof_reply_never_retries_or_consumes_READY(self):
        ps, wire, buses = self.boot()
        launch = buses['H1'].on_launch
        def lost():
            launch(); wire.cache.cache.lost = True
        buses['H1'].on_launch = lost
        with self.assertRaises(OSError): ps.initialize(wire)
        self.assertTrue(ps.fault)
        self.assertFalse(any(a == 0x30 for a, v in buses['H1'].writes))
        with self.assertRaises(RuntimeError): ps.initialize(wire)

    def test_reserved_peer_status_bit_denies_before_HELLO(self):
        ps, wire, buses = self.boot(authorized_status=0x621)
        with self.assertRaises(RuntimeError): ps.initialize(wire)
        self.assertEqual(buses['CTRL'].epoch, 0)
        self.assertEqual(buses['H1'].writes, [])

    def test_peer_authorization_failure_sends_no_HELLO_or_local_epoch(self):
        ps, wire, buses = self.boot(reject=True)
        with self.assertRaises(RuntimeError): ps.initialize(wire)
        self.assertEqual(buses['CTRL'].epoch, 0)
        self.assertEqual(buses['H1'].writes, [])
        self.assertTrue(ps.fault)


if __name__ == '__main__': unittest.main()
