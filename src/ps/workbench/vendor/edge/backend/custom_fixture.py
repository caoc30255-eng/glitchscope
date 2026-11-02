"""Modeled register/serial fixtures exercise the reviewed executor methods and raw verifier.

Nothing connects to FPGA, a serial device or the network.

"""

from pathlib import Path

from types import SimpleNamespace as NS,ModuleType

from unittest.mock import Mock,patch

import importlib,json,sys,tempfile,threading,unittest



W=Path(__file__).resolve().parent;KIT=W

OLD=W/'tests_support'

sys.path[:0]=[str(KIT/'runtime/host'),str(KIT),str(OLD)]

for name in ('ps_candidate_session','controlled_trial_executor','raw_mark_snapshot','scan_executor'):

    m=importlib.import_module(name);assert Path(m.__file__).resolve().parent==KIT/'runtime/host'

import test_controlled_executor as ce

from scan_executor import BoundedScanExecutor



from scan_feedback import ScanFeedback

from ch1_completion_ledger import _codec

from ch1_runtime_driver import Binding

from ch1_control_session import event_payload,frame,decode_event

from ch1_peer_archive_driver import persist_exact

from raw_mark_snapshot import RawMarkCapture

import ch1_evidence_store as store



def packed(parts):

    n=bits=0

    for width,value in parts:n=(n<<width)|value;bits+=width

    return n.to_bytes((bits+7)//8,'big')



class Integration(unittest.TestCase):

    def setUp(self):

        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

        ce.marks.ROOT=Path(self.tmp.name);ce.marks.MarkTests.setUp(self)

        self.bus=ce.ReArmBus();self.bus.live=3;self.cap=RawMarkCapture(self.bus,self.j.path.parent/'MARK')

        self.s,self.b=ce.session_fixture(self);self.s.control_transport.close=Mock();self.counter=0

        self.addCleanup(lambda:[h.close() for h in self.s.handles])

        original=self.b['SYS'].read;self.b['SYS'].read=lambda a:self.counter if a in (0x18,0x1c) else original(a)

        persist_exact(self.s.root/'MARK/preflight',{'preflight.json':store._json({'fresh':True})})

        persist_exact(self.s.root/'MPG1/preflight',{'preflight.json':store._json(dict(session=self.s.root.name,counts_after=[0,0],native_identity_words=[0]*8))})

        self.reg={0xd20:0x4d504731};self.s.peer.read=Mock(side_effect=lambda a:self.reg[a])

        self.lock=(self.s.root.parent/'exclusive.lock').open('a+');self.addCleanup(self.lock.close)

    def owner(self):

        f=ModuleType('fcntl');f.LOCK_EX=2;f.LOCK_NB=4;f.flock=lambda *a:None

        with patch.dict(sys.modules,{'fcntl':f}):self.o=ScanOwner(self.s,self.b,self.lock,KIT)

        return self.o

    def one(self,session,b,kind,inner,rid,**kw):

        s=session

        if getattr(self,'raise_at',None)==rid:raise TimeoutError('modeled uncertain record effect')

        codec=_codec();config=kind==2;r=codec.decode_config(inner) if config else codec.decode_item(inner)

        fields=store._fields(self.identity,store.IDENTITY);fields.update(seq=rid,generation=rid,run_id=9,image_id=1,attempt_id=0,route_mode=0,trial_id=r.get('trial_id',0),item_index=r.get('item_index',0))

        identity=ce.word_for(fields);wirekind=2 if config else 1;binding=Binding(9,rid,wirekind,identity,50,800000)

        p=kw['profile'];correct=p is None or (p.width<10 and not getattr(self,'all_marked_fail',False))
        if p and getattr(self,'mixed_faults',False):correct=(rid%2)==1
        if p is None and getattr(self,'baseline_failure_at',None)==rid:correct=False

        payload=None if config else bytes(r['payload']);received=payload

        if not config and not correct:received=bytes([payload[0]^1])+payload[1:]

        raw=codec.encode_config_ack(9,1) if config else codec.encode_report(9,1,r['trial_id'],r['item_index'],0,0,0,0 if correct else 1,received)

        descriptor=packed([(32,9),(1,0),(256,identity),(32,rid),(2,wirekind),(8,1),(16,len(raw)),(64,50),(64,800000),(64,500000),(1,1),(8,0 if correct else 1),(8,0),(16,0),(32,0),(4,0),(64,0)])

        samples=lambda data:b''.join(((v<<68)|(100+i*1000)).to_bytes(10,'big') for i,v in enumerate(data))

        saved=store.persist_record(s.root/'CH1/main',descriptor,samples(raw),store.crc16(descriptor),store.crc16(samples(raw)),errors=[],orphans=[],watermark_tick=500001,expected_payload=payload)

        one=Path(saved['evidence_dir']);cl=json.loads((one/'classification.json').read_bytes())

        suffix='epoch_00000009_record_%08x'%rid;zero=s.root/'CH0'/suffix

        byte=p.byte if p else 20;bit=p.bit if p else 0
        lane=inner if correct else inner[:byte]+bytes([inner[byte]^(1<<bit)])+inner[byte+1:]

        meta=dict(binding=dict(identity=identity,epoch=9,record_id=rid,start=50,deadline=800000),status=3,first_fault=0,a_errors=0,b_errors=0)

        cc=dict(a_source_match=correct,a_reception_success=correct,b_source_match=correct,b_reception_success=correct)

        bcorrect=correct

        if getattr(self,'reference_good',False) and 4<=rid<=6:bcorrect=True

        if getattr(self,'candidate_bad',False) and 7<=rid<=9:bcorrect=False

        if getattr(self,'validation_bad',False) and 10<=rid<=12:bcorrect=False

        blane=inner if bcorrect else lane

        cc.update(b_source_match=bcorrect,b_reception_success=bcorrect)

        persist_exact(zero,{'expected_request.bin':inner,'descriptor.json':store._json(meta),'a_raw.bin':lane,'b_raw.bin':blane,'a_samples.bin':samples(lane),'b_samples.bin':samples(blane)})

        if p is None and not correct:raise ValueError('Modeled unmarked baseline source/business failure; retain raw and stop')
        expected=dict(d=3,s=-1) if config else self.owner.plan['receiver_B']

        assert kw['d']==expected['d'] and kw['s']==expected['s']

        applied=dict(d=3 if getattr(self,'force_wrong_d3',False) else kw['d'],s=kw['s'],profile_seq=rid,RX_profile_verified=True)

        persist_exact(s.root/'admission'/suffix,{'admission.json':store._json(dict(context=dict(epoch=9,identity=identity,kind=wirekind,record_id=rid),profile=applied))})

        owner=NS(phase='RETIRED',fault=False,mark_required=p is not None,mark_capture=s.mark_capture,local_retired=True,peer_retired=True,retire_sent=True,binding=binding,journal=s.journal,_strict_local_recheck=Mock(),started=True,done=True)

        if p and hasattr(p,'count'):
            s.mpg1_monitor.authorize_multi_profile(identity,p,inner)
            request=p.build_request(identity,inner)
            ack=frame(0x7c,request[5:-2] if not getattr(self,'bad_multi_ack',False) else bytes(32))
            persist_exact(s.root/'TYPE3C'/suffix,{'request.bin':request,'ack.bin':ack})
            p.verify_ack(request,ack)
        if p:

            cap=s.mark_capture;cap.arm(binding,inner,p);self.bus.trigger(width=p.width*2)
            if (inner[p.byte]>>p.bit)&1:self.bus.words=bytearray(v^1 for v in self.bus.words)

            owner.mark_receipt=cap.archive(binding,decode_event(frame(0x33,event_payload(identity,0))))

        s.current=owner

        points=0 if p is None else getattr(p,"count",1);self.reg.update({0xd24:points|((points+int(bool(getattr(self,'wrong_point_count',False) and rid>=3)))<<9),0xd28:1})

        native=int.from_bytes(event_payload(identity,0),'little')

        self.reg.update({0xd30+i*4:(native>>(32*(7-i)))&0xffffffff for i in range(8)})

        proof=s.mpg1_monitor.verify_completed(owner,points) if getattr(s,'mpg1_monitor',None) else None

        s.current=None;s.last_retired_owner=owner;s.upload.seq=rid;self.counter=rid

        if config:s.config_owner=owner

        return dict(record_id=rid,kind='CONFIG' if config else 'ITEM',business_success=cl['business_success'],CH0_classification=cc,CH1_classification=cl,CH0_evidence_dir=str(zero),CH1_evidence_dir=str(one),retirement={k:True for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')},next_credit=dict(next_item_allowed=True,last_seq=rid),MPG1_pre_retirement=proof)

