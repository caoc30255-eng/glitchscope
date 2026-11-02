"""RAM/filesystem protocol models only. No hardware operations or real UART."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import sys,json,copy,uuid,unittest,struct,zlib
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
from random_image_plan import make_schedule,validate_schedule,Draws,IMAGE_SHA
from random_image_executor import RandomImageExecutor
from random_image_monitor import RandomImageMonitor
from random_image_render import png_gray,metrics,archive_images
from random_image_pilot import RandomImagePilot
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from multi_point_profile import MultiPointProfile
from ch1_control_session import ApplicationJournal,event_payload,frame,decode_event
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from ch1_runtime_driver import Binding
from raw_mark_snapshot import RawMarkCapture
import ch1_evidence_store as store
import test_controlled_executor as ce
from test_evidence_store import packed,fixture

def image():return (ROOT/'image_source.bin').read_bytes()
def identity(rid,trial=0,index=0):
    f=dict(reserved=0,session=0x30000009,seq=rid,route_epoch=0x20000009,slot=0,
        generation=rid,run_id=9,image_id=1,trial_id=trial,item_index=index,attempt_id=0,route_mode=0)
    return ce.word_for(f)

class ScheduleTests(unittest.TestCase):
    def test_known_cross_version_random_vector(self):
        p=make_schedule();self.assertEqual(p,make_schedule())
        self.assertEqual(p['items'][0]['profile'],dict(first_byte=184,count=70,bit=5,phase=37,width=3))
        self.assertEqual(sum(e['count'] for e in p['items']),8394)
    def test_different_seed_changes_schedule(self):self.assertNotEqual(make_schedule(1)['items'],make_schedule(2)['items'])
    def test_all_samples_obey_joint_window_and_payload_bounds(self):
        counts=set();bits=set()
        for seed in range(100):
            for e in make_schedule(seed)['items']:
                counts.add(e['count'])
                if e['count']==0:self.assertIsNone(e['profile']);continue
                p=e['profile'];bits.add(p['bit'])
                self.assertTrue(20<=p['first_byte'] and p['first_byte']+p['count']<=276)
                self.assertTrue(5<=p['phase'] and 1<=p['width'] and p['phase']+p['width']<=45)
        self.assertEqual(counts,set(range(256)));self.assertEqual(bits,set(range(8)))
    def test_boolean_negative_or_oversize_seed_rejected(self):
        for seed in (True,-1,2**64,3.5):
            with self.assertRaises(ValueError):make_schedule(seed)
    def test_saved_schedule_tamper_is_not_new_random_draw(self):
        p=make_schedule();p['items'][0]['profile']['width']+=1
        with self.assertRaises(ValueError):validate_schedule(p)
    def test_zero_is_disabled_never_wrapped_256(self):
        entries=[e for seed in range(20) for e in make_schedule(seed)['items'] if e['count']==0]
        self.assertTrue(entries);self.assertTrue(all(e['profile'] is None for e in entries))
    def test_255_count_encodes_254_not_255(self):
        p=MultiPointProfile(20,255,7,5,40)
        inner=_codec().encode_item(9,1,165,0,64,0,0,image()[:256])
        raw=p.build_request(identity(2,165),inner);self.assertEqual(raw[-3],254)
    def test_default_schedule_validates_and_has_exact65_allowance(self):
        p=make_schedule();self.assertTrue(validate_schedule(p));self.assertEqual(p['max_records_including_CONFIG'],65)
    def test_image_source_matches_previous_real_image(self):self.assertEqual(store.sha(image()),IMAGE_SHA)

class ImageExecutorTests(unittest.TestCase):
    setUp=ce.marks.MarkTests.setUp
    def service(self,seed=20261018):
        self.bus=ce.ReArmBus();self.bus.live=3;self.cap=RawMarkCapture(self.bus,self.j.path.parent/'MARK')
        self.s,self.b=ce.session_fixture(self)
        persist_exact(self.s.root/'MARK/preflight',{'preflight.json':store._json({'fresh':True})})
        return RandomImageExecutor(self.s,self.b,image(),make_schedule(seed),exclusive_owner=True)
    def test_constructor_plan_and_config_are_real128x128_64_chunks(self):
        ex=self.service();cfg=_codec().decode_config(ex._frozen_config)
        self.assertEqual((cfg['width'],cfg['height'],cfg['item_total'],cfg['total_bytes']),(128,128,64,16384))
        self.assertEqual(ex.max_attempts,65);self.assertEqual(len(ex.parts),64)
        self.assertEqual(ex.index,0);self.assertEqual(self.bus.writes,[]);ex._verify_plan()
    def test_old_executor_still_rejects_more_than_three_items(self):
        with self.assertRaises(ValueError):ControlledTrialExecutor(NS(),{},image(),[TrialRequest('x',3,-1)]*64,max_physical_starts=65,exclusive_owner=True)
    def test_schedule_changed_before_record_has_no_execution(self):
        ex=self.service();(ex.root/'random_schedule/schedule.json').write_bytes(b'{}')
        with patch('controlled_trial_executor._one') as one:
            with self.assertRaises(ValueError):ex.run_next()
            one.assert_not_called()
        self.assertTrue(ex.stopped and self.s.fault)
    def test_source_changed_before_record_has_no_execution(self):
        ex=self.service();(ex.root/'plan/source.bin').write_bytes(bytes(16384))
        with patch('controlled_trial_executor._one') as one:
            with self.assertRaises(ValueError):ex.run_next()
            one.assert_not_called()
    def test_timeout_keeps_attempt_and_denies_resume(self):
        ex=self.service()
        with patch('controlled_trial_executor._one',side_effect=TimeoutError('uncertain')) as one:
            with self.assertRaises(TimeoutError):ex.run_next()
            with self.assertRaises(RuntimeError):ex.run_next()
            self.assertEqual(one.call_count,1)
        self.assertEqual(ex.attempts,1);self.assertEqual(ex.index,0)
        diagnostic=json.loads(next(ex.root.glob('STOP_*/diagnostic.json')).read_bytes())
        self.assertEqual(diagnostic['execution_effect'],'UNKNOWN')
    def modeled(self,session,buses,kind,inner,rid,**kw):
        item=_codec().decode_config(inner) if kind==2 else _codec().decode_item(inner)
        word=identity(rid,item.get('trial_id',0),item.get('item_index',0));binding=Binding(9,rid,2 if kind==2 else 1,word,100,10000)
        owner=NS(phase='RETIRED',fault=False,mark_required=kw['profile'] is not None,
            mark_capture=session.mark_capture,local_retired=True,peer_retired=True,retire_sent=True,
            binding=binding,journal=session.journal,_strict_local_recheck=Mock())
        if kw['profile'] is not None:
            p=kw['profile'];cap=session.mark_capture;cap.arm(binding,inner,p)
            bit=(inner[p.first_byte]>>p.bit)&1
            self.bus.trigger(width=p.width*2)
            for i in range(4096):self.bus.words[i]=(self.bus.words[i]&~1)|bit
            for i in range(2048,2048+p.width*2):self.bus.words[i]^=1
            owner.mark_receipt=cap.archive(binding,decode_event(frame(0x33,event_payload(word,0))))
        session.last_retired_owner=owner;session.upload.seq=rid
        if kind==2:session.config_owner=owner
        profile={'d':3,'s':-1,'profile_seq':rid,'RX_profile_verified':True}
        persist_exact(session.root/'admission'/('epoch_00000009_record_%08x'%rid),{'admission.json':store._json({'profile':profile})})
        correct=kw['profile'] is None
        return {'record_id':rid,'business_success':correct,'CH0_classification':{
            'a_source_match':correct,'a_reception_success':correct,'b_source_match':correct,'b_reception_success':correct},
            'CH1_classification':{'capture_valid':True,'raw_frame_crc_and_format_valid':True,'wire_identity_match':True}}
    def test_65_model_records_rearm_different_bits_widths_and_no66th(self):
        ex=self.service()
        with patch('controlled_trial_executor._one',side_effect=self.modeled):
            for rid in range(1,66):self.assertEqual(ex.run_next()['record_id'],rid)
            with self.assertRaises(RuntimeError):ex.run_next()
        self.assertEqual(ex.attempts,65);self.assertEqual(len(ex.results),65)
        self.assertEqual(len(list(self.cap.root.glob('epoch_*/saved/samples.bin'))),64)
        self.assertEqual([v for a,v in self.bus.writes if a==0],[1]*64)
        self.assertEqual(len(list((self.s.root.parent/'trial_registry').glob('trial_*.json'))),64)
    def test_zero_point_between_marked_items_has_no_ARM_and_keeps_retired_successor(self):
        ex=self.service(seed=71)
        self.assertEqual([e['count'] for e in make_schedule(71)['items'][:3]],[5,0,33])
        with patch('controlled_trial_executor._one',side_effect=self.modeled):
            ex.run_next();ex.run_next()
            old=self.s.mark_capture;raw=next(old.root.glob('epoch_*/saved/samples.bin')).read_bytes()
            ex.run_next()
            self.assertIs(self.s.mark_capture,old)
            self.assertEqual([v for a,v in self.bus.writes if a==0],[1])
            ex.run_next()
        self.assertEqual([v for a,v in self.bus.writes if a==0],[1,1])
        self.assertEqual(next(old.root.glob('epoch_00000009_record_00000002/saved/samples.bin')).read_bytes(),raw)

class ImageMonitorTests(unittest.TestCase):
    def setUp(self):
        root=ROOT/'evidence/random_monitor_models'/uuid.uuid4().hex
        self.j=ApplicationJournal(root,9);self.addCleanup(self.j.close)
        self.reg={0xd20:0x4d504731,0xd24:0,0xd28:1}
        self.peer=NS(read=Mock(side_effect=lambda a:self.reg[a]))
        self.sys=NS(read=Mock(return_value=0));self.s=NS(root=root,local_epoch=9,fault=False,current=None,
            config_owner=None,peer=self.peer,journal=self.j,last_retired_owner=None)
        self.schedule=make_schedule();self.ex=NS(session=self.s,buses={'SYS':self.sys},index=0,
            _frozen_plan=b'plan',_schedule=store._json(self.schedule),parts=tuple(image()[i:i+256] for i in range(0,16384,256)))
        persist_exact(root/'MPG1/preflight',{'preflight.json':store._json({'session':root.name,'counts_after':[0,0],'native_identity_words':[0]*8})})
        self.m=RandomImageMonitor(self.ex,self.schedule)
    def active(self,rid):
        word=identity(rid,0 if rid==1 else 164+rid,rid-2 if rid>1 else 0)
        native=int.from_bytes(event_payload(word,0),'little')
        for i in range(8):self.reg[0xd30+4*i]=(native>>(224-32*i))&0xffffffff
        self.reg[0xd24]=self.m.expected[rid-1]*(1+512);self.sys.read.return_value=rid-1
        owner=NS(binding=Binding(9,rid,2 if rid==1 else 1,word,100,10000),started=True,done=True)
        self.s.current=owner;return owner
    def test_all65_actual_counter_models_match_frozen_counts_before_retirement(self):
        for rid,n in enumerate(self.m.expected,1):self.assertEqual(self.m.verify_completed(self.active(rid),n)['emitted_points'],n)
        self.assertEqual(len(self.m.receipts),65)
    def test_first_random_profile_can_follow_config_retirement(self):
        old=self.active(1);self.m.verify_completed(old,0);old.phase='RETIRED';self.s.last_retired_owner=old
        new=self.active(2);inner=_codec().encode_item(9,1,166,0,64,0,0,image()[:256])
        self.m.authorize_multi_profile(new.binding.identity,MultiPointProfile(**self.schedule['items'][0]['profile']),inner)
    def test_profile_outside_saved_random_draw_rejected(self):
        old=self.active(1);self.m.verify_completed(old,0);old.phase='RETIRED';self.s.last_retired_owner=old
        new=self.active(2);inner=_codec().encode_item(9,1,166,0,64,0,0,image()[:256])
        with self.assertRaises(ValueError):self.m.authorize_multi_profile(new.binding.identity,MultiPointProfile(20,4,0,15,20),inner)
    def test_count_fault_identity_and_fence_fail_closed(self):
        owner=self.active(1)
        for reg,value in ((0xd24,1),(0xd28,0),(0xd28,3),(0xd4c,0)):
            saved=self.reg[reg];self.reg[reg]=value
            with self.assertRaises(ValueError):self.m.verify_completed(owner,0)
            self.reg[reg]=saved
        self.assertEqual(self.m.receipts,{})
    def test_nonsequential_owner_cannot_skip_config(self):
        with self.assertRaises(ValueError):self.m.verify_completed(self.active(2),self.m.expected[1])
    def test_saved_count_tamper_blocks_next_record(self):
        self.m.verify_completed(self.active(1),0);self.m.receipts[1][0].write_bytes(b'{}')
        with self.assertRaises(ValueError):self.m._verify()
    def test_changed_expected_list_or_epoch_blocks(self):
        expected=self.m.expected;self.m.expected=(1,)+expected[1:]
        with self.assertRaises(ValueError):self.m._verify()
        self.m.expected=expected;self.s.local_epoch=10
        with self.assertRaises(RuntimeError):self.m._verify()

class RenderTests(unittest.TestCase):
    def test_png_is_exact_original_bytes_and_valid_chunk_crcs(self):
        raw=image();png=png_gray(raw);pos=8;compressed=b''
        while pos<len(png):
            n=struct.unpack('>I',png[pos:pos+4])[0];kind=png[pos+4:pos+8];data=png[pos+8:pos+8+n]
            self.assertEqual(zlib.crc32(kind+data)&0xffffffff,struct.unpack('>I',png[pos+8+n:pos+12+n])[0])
            if kind==b'IDAT':compressed+=data
            pos+=12+n
        rows=zlib.decompress(compressed)
        self.assertEqual(b''.join(rows[i+1:i+129] for i in range(0,len(rows),129)),raw)
    def test_metrics_keep_planned_targets_separate_from_actual_bit_errors(self):
        source=bytes(16384);raw=bytearray(source);raw[2]=128
        m=metrics(source,raw,bytes([255])*16384)
        self.assertEqual(m['changed_pixels'],1);self.assertEqual(m['bit_errors'],1)
        self.assertEqual(m['maximum_absolute_gray_error'],128)
    def test_partial_images_are_not_zero_filled(self):
        with self.assertRaises(ValueError):png_gray(bytes(100))
        with self.assertRaises(RuntimeError):archive_images(NS(index=64,attempts=64,results=[None]*64,stopped=False))
    def modeled_archives(self):
        root=ROOT/'evidence/random_render_models'/uuid.uuid4().hex
        source=image();schedule=make_schedule();results=[{'record_id':1}]
        for index,entry in enumerate(schedule['items']):
            rid=index+2;word=identity(rid,200+index,index);part=source[index*256:(index+1)*256]
            request=_codec().encode_item(9,1,200+index,index,64,0,0,part)
            damaged=bytearray(part);p=entry['profile'];damaged[p['first_byte']-20]^=1<<p['bit']
            bad=request[:20]+damaged+request[-2:]
            binding={'identity':word,'epoch':9,'record_id':rid,'start':50,'deadline':800000}
            def samples(raw):return b''.join(((b<<68)|(100+i*1000)).to_bytes(10,'big') for i,b in enumerate(raw))
            zero=root/'CH0'/('epoch_00000009_record_%08x'%rid)
            persist_exact(zero,{'expected_request.bin':request,'a_raw.bin':request,'b_raw.bin':bad,
                'a_samples.bin':samples(request),'b_samples.bin':samples(bad),
                'descriptor.json':store._json({'binding':binding,'status':3,'first_fault':0,'a_errors':0,'b_errors':0})})
            report=_codec().encode_report(9,1,200+index,index,0,0,0,1,damaged)
            values=dict(epoch=9,reserved=0,identity=word,record_id=rid,kind=1,reason=1,raw_count=276,
                start=50,deadline=800000,close=400000,frame_valid=1,report_status=1,report_flags=0,
                management_status=0,uart_errors=0,observed_flags=0,first_error_tick=0)
            descriptor=packed([(width,values[name]) for name,width in store.FIELDS]);rawsamples=samples(report)
            classification=store.classify(report,store.descriptor_decode(descriptor),store.samples_decode(rawsamples,values),part)
            one=root/'CH1/main'/('epoch_00000009_record_%08x'%rid)
            persist_exact(one,{'descriptor.bin':descriptor,'samples.bin':rawsamples,'raw_packet.bin':report,'classification.json':store._json(classification)})
            result={'record_id':rid,'identity_hex':'%064x'%word,'receiver_A_frame_correct':True,
                'receiver_B_frame_correct':False,'STM_business_success':False}
            persist_exact(root/'EXECUTOR'/('record_%08x'%rid)/'result',{'result.json':store._json(result)})
            results.append(result)
        return NS(index=65,attempts=65,results=results,stopped=False,_verify_plan=Mock(),root=root/'EXECUTOR',
            session=NS(root=root,local_epoch=9,journal=NS(record=Mock())),_frozen_source=source,
            _schedule=store._json(schedule),parts=tuple(source[i:i+256] for i in range(0,16384,256)))
    def test_full_reconstruction_uses_actual_modeled_reports_not_planned_mask(self):
        e=self.modeled_archives();info=archive_images(e)
        self.assertEqual(info['receivers']['A']['changed_pixels'],0)
        self.assertEqual(info['receivers']['B']['changed_pixels'],64)
        self.assertEqual(info['receivers']['STM']['changed_pixels'],64)
        self.assertEqual(info['planned_points'],8394);self.assertFalse(info['image_acceptance_claimed'])
        self.assertTrue((e.session.root/'IMAGE_VIEW/图片对照.html').is_file())
    def test_original_packet_tamper_prevents_render(self):
        e=self.modeled_archives();p=e.session.root/'CH1/main/epoch_00000009_record_00000002/raw_packet.bin'
        p.write_bytes(bytes(276))
        with self.assertRaises(ValueError):archive_images(e)

class PilotTests(unittest.TestCase):
    def test_stop_once_even_when_failure_happens_before_first_completion(self):
        p=object.__new__(RandomImagePilot);p.used=False;p.session=NS(_stop=Mock())
        p.executor=NS(index=0,attempts=0,stopped=False,run_next=Mock(side_effect=TimeoutError('unknown')))
        p.source=Path(__file__);p.source_sha=store.sha(p.source.read_bytes());p.schedule=make_schedule();p._schedule=store._json(p.schedule)
        p._verify_policy=Mock()
        with self.assertRaises(TimeoutError):p.run()
        with self.assertRaises(RuntimeError):p.run()
        self.assertEqual(p.executor.run_next.call_count,1);self.assertTrue(p.executor.stopped)

if __name__=='__main__':unittest.main()
