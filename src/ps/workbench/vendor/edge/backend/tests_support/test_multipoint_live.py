"""Software protocol/ownership/physical-sample models only; no board access."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import sys,json,unittest,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import test_fault_mark_candidate as marks
from multi_point_profile import MultiPointProfile
from mpg1_trial_monitor import MPG1TrialMonitor
from multipoint_pilot import MultiPointPilot
from ch1_control_session import PeerControlSession,ApplicationJournal,event_payload,frame,decode_frame
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/multipoint_models'/uuid.uuid4().hex
        self.j=ApplicationJournal(self.root,9);self.addCleanup(self.j.close)
        self.identity=store.descriptor_decode(__import__('test_evidence_store').fixture()[0])['identity']
        self.owner=NS(binding=NS(record_id=1,epoch=9,identity=self.identity),started=True,done=True)
        self.sys=NS(read=Mock(return_value=0))
        native=int.from_bytes(event_payload(self.identity,0),'little')
        self.reg={0xd20:0x4d504731,0xd24:0,0xd28:1}
        self.reg.update({0xd30+4*i:(native>>(224-32*i))&0xffffffff for i in range(8)})
        self.peer=NS(read=Mock(side_effect=lambda a:self.reg[a]))
        self.s=NS(root=self.root,local_epoch=9,fault=False,current=None,config_owner=None,
            peer=self.peer,journal=self.j,last_retired_owner=None)
        persist_exact(self.root/'MPG1/preflight',{'preflight.json':store._json({
            'session':self.root.name,'counts_after':[0,0],'native_identity_words':[0]*8})})
        self.m=MPG1TrialMonitor(self.s,{'SYS':self.sys});self.s.current=self.owner
    def test_exact_live_identity_and_done_fence_saved_before_retirement(self):
        p=self.m.verify_completed(self.owner,0)
        self.assertTrue(p['actual_DONE_fenced']);self.assertEqual(p['emitted_points'],0)
        self.assertFalse(p['all_points_waveform_verified']);self.assertEqual(set(self.m.receipts),{1})
    def test_after_retirement_fence_zero_is_not_completion_proof(self):
        self.reg[0xd28]=0
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_source_fault_denied(self):
        self.reg[0xd28]=3
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_reserved_status_denied(self):
        self.reg[0xd28]=5
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_wrong_native_identity_denied(self):
        self.reg[0xd4c]^=1
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_wrong_point_count_denied(self):
        self.reg[0xd24]=(4<<9)|3
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_changed_readback_denied(self):
        def read(a):
            value=self.reg[a]
            if a==0xd24:self.reg[a]=1
            return value
        self.peer.read.side_effect=read
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_duplicate_evidence_cannot_replace_record(self):
        self.m.verify_completed(self.owner,0)
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_wrong_owner_and_order_denied(self):
        with self.assertRaises(ValueError):self.m.verify_completed(NS(**vars(self.owner)),0)
        self.owner.binding.record_id=2
        with self.assertRaises(ValueError):self.m.verify_completed(self.owner,0)
    def test_retirement_already_advanced_denied(self):
        self.sys.read.return_value=1
        with self.assertRaises(RuntimeError):self.m.verify_completed(self.owner,0)
    def test_policy_tamper_denied(self):
        (self.m.root/'policy/policy.json').write_bytes(b'{}')
        with self.assertRaises(RuntimeError):self.m.verify_completed(self.owner,0)
    def test_prior_count_evidence_tamper_denied(self):
        self.m.verify_completed(self.owner,0)
        self.m.receipts[1][0].write_bytes(b'{}')
        with self.assertRaises(ValueError):self.m._verify()
    def test_early_type3c_has_no_profile_tx(self):
        inner=__import__('ch1_completion_ledger')._codec().encode_item(1,2,3,4,64,1,0,bytes(range(256)))
        with self.assertRaises(RuntimeError):self.m.authorize_multi_profile(self.identity,MultiPointProfile(20,4,0,15,20),inner)
    def test_unapproved_range_denied(self):
        with self.assertRaises(ValueError):self.m.authorize_multi_profile(self.identity,MultiPointProfile(20,5,0,15,20),b'')
    def test_four_points_saved_only_at_record4(self):
        for rid,points in enumerate((0,0,1,4),1):
            self.owner.binding.record_id=rid;self.sys.read.return_value=rid-1
            self.reg[0xd24]=points|(points<<9)
            p=self.m.verify_completed(self.owner,points)
            self.assertEqual(p['configured_points'],points)
        self.assertEqual(set(self.m.receipts),{1,2,3,4})
    def test_type3c_authorized_after_exact_three_retirements(self):
        for rid,points in enumerate((0,0,1),1):
            self.owner.binding.record_id=rid;self.sys.read.return_value=rid-1
            self.reg[0xd24]=points|(points<<9);self.m.verify_completed(self.owner,points)
        fields=store._fields(self.identity,store.IDENTITY);fields.update(seq=3,run_id=9,generation=3)
        def pack(fields):
            out=0
            for name,width in store.IDENTITY:out=out<<width|fields[name]
            return out
        self.s.last_retired_owner=NS(phase='RETIRED',binding=NS(record_id=3,epoch=9,identity=pack(fields)))
        self.sys.read.return_value=3;fields.update(seq=4,generation=4)
        inner=__import__('ch1_completion_ledger')._codec().encode_item(
            9,fields['image_id'],fields['trial_id'],fields['item_index'],64,fields['attempt_id'],0,bytes(range(256)))
        self.assertTrue(self.m.authorize_multi_profile(pack(fields),MultiPointProfile(20,4,0,15,20),inner))
        fields['route_epoch']+=1
        with self.assertRaises(ValueError):self.m.authorize_multi_profile(pack(fields),MultiPointProfile(20,4,0,15,20),inner)
    def test_epoch_change_blocks_monitor(self):
        self.s.local_epoch+=1
        with self.assertRaises(RuntimeError):self.m._verify()


class MultiWireTests(unittest.TestCase):
    setUp=marks.MarkTests.setUp
    def peer(self,mode='ok'):
        calls=[]
        def exchange(request,expected):
            calls.append(request);typ,p=decode_frame(request)
            self.assertEqual((typ,expected),(0x3c,0x7c))
            if mode=='count':p=p[:-1]+b'\x04'
            raw=frame(0x7a if mode=='type' else 0x7c,p)
            if mode=='crc':raw=raw[:-1]+bytes([raw[-1]^1])
            return raw
        peer=PeerControlSession(NS(exchange=exchange),self.j,1)
        peer.mpg1_monitor=NS(session=NS(peer=peer),authorize_multi_profile=Mock())
        return peer,calls
    def test_exact_actual_protocol_ACK7C_is_durable(self):
        peer,calls=self.peer();result=peer.request_profile_fault(self.identity,MultiPointProfile(20,4,0,15,20),self.inner)
        self.assertEqual(len(calls[0]),39);self.assertEqual(decode_frame(calls[0])[1][-1],3)
        self.assertTrue(result['mark_required']);self.assertIn('control_rx_stream',self.j.path.read_text())
    def test_changed_count_type_crc_all_stop_without_retry(self):
        for mode in ('count','type','crc'):
            peer,calls=self.peer(mode)
            with self.assertRaises(ValueError):peer.request_profile_fault(self.identity,MultiPointProfile(20,4,0,15,20),self.inner)
            self.assertTrue(peer.fault);self.assertEqual(len(calls),1)
    def test_no_monitor_cannot_send_new_command(self):
        peer,calls=self.peer();del peer.mpg1_monitor
        with self.assertRaises(RuntimeError):peer.request_profile_fault(self.identity,MultiPointProfile(20,4,0,15,20),self.inner)
        self.assertEqual(calls,[])
    def test_raw_capture_reports_first_point_only(self):
        self.cap.arm(self.binding,self.inner,MultiPointProfile(20,4,0,15,20));self.bus.trigger()
        receipt=self.cap.archive(self.binding,self.event)
        analysis=json.loads((Path(receipt.evidence_dir)/'context.json').read_bytes())['analysis']
        self.assertTrue(analysis['first_point_physical_inversion_verified'])
        self.assertFalse(analysis['all_points_waveform_verified']);self.assertEqual(analysis['configured_points'],4)
        self.assertNotIn('physical_inversion_verified',analysis)
    def test_wrong_payload_cannot_arm(self):
        bad=bytearray(self.inner);bad[20]^=1
        with self.assertRaises(ValueError):self.cap.arm(self.binding,bad,MultiPointProfile(20,4,0,15,20))
        self.assertEqual(self.bus.writes,[])
    def test_legacy_retired_snapshot_to_multi_successor_keeps_both_originals(self):
        import test_controlled_executor as ce
        helper=ce.SuccessorTests('test_no_retirement_seal_denies_successor')
        helper.setUp()
        try:
            helper.prepare();old=(Path(helper.receipt.evidence_dir)/'samples.bin').read_bytes()
            new=helper.successor();binding,inner=helper.next_binding();helper.s.mark_capture=new
            new.arm(binding,inner,MultiPointProfile(20,4,0,15,20));helper.bus.trigger(width=41)
            event=__import__('ch1_control_session').decode_event(frame(0x33,event_payload(binding.identity,0)))
            receipt=new.archive(binding,event)
            self.assertEqual(old,(Path(helper.receipt.evidence_dir)/'samples.bin').read_bytes())
            self.assertEqual(json.loads((Path(receipt.evidence_dir)/'context.json').read_bytes())['analysis']['inverted_samples'],41)
            self.assertEqual([v for a,v in helper.bus.writes if a==0],[1,1])
            self.assertTrue(helper.cap.verify_archived(helper.receipt,helper.binding)['historical_archive_integrity_verified'])
            with self.assertRaises(RuntimeError):helper.cap.verify_saved(helper.receipt,helper.binding)
        finally:helper.doCleanups()


class PilotPlanTests(unittest.TestCase):
    def test_frozen_factory_exact_four_records_without_execution(self):
        session=NS()
        with patch('multipoint_pilot.MPG1TrialMonitor'),patch('multipoint_pilot.ControlledTrialExecutor') as factory,patch('multipoint_pilot.persist_exact'):
            factory.return_value.root=ROOT/'evidence/model_only'
            pilot=MultiPointPilot(session,{},bytes(range(256))*3)
            args=factory.call_args
            self.assertEqual(args.kwargs['max_physical_starts'],4)
            self.assertEqual([r.fault for r in args.args[3]],[None,__import__('fault_profile').FaultProfile(20,0,15,20),MultiPointProfile(20,4,0,15,20)])
            factory.return_value.run_next.assert_not_called();self.assertFalse(pilot.used)
    def test_different_payload_rejected_before_monitor(self):
        with patch('multipoint_pilot.MPG1TrialMonitor') as monitor:
            with self.assertRaises(ValueError):MultiPointPilot(NS(),{},bytes(768))
            monitor.assert_not_called()
    def test_failure_permanently_stops_without_retry(self):
        pilot=object.__new__(MultiPointPilot);pilot.used=False;pilot.session=NS(_stop=Mock())
        pilot.executor=NS(index=0,attempts=0,stopped=False,run_next=Mock(side_effect=TimeoutError('uncertain')))
        pilot.source=Path(__file__);pilot.source_sha=store.sha(pilot.source.read_bytes())
        with self.assertRaises(TimeoutError):pilot.run()
        self.assertTrue(pilot.used and pilot.executor.stopped)
        with self.assertRaises(RuntimeError):pilot.run()
        self.assertEqual(pilot.executor.run_next.call_count,1)

if __name__=='__main__':unittest.main()
