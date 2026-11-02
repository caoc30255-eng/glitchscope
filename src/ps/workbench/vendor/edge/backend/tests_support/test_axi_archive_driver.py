"""Offline synchronous register model + real local fsync; no board/RTL execution."""
from pathlib import Path
import sys,uuid,json,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'));sys.path.insert(0,str(ROOT/'tests'))
import ch1_evidence_store as store
import ch1_aux_store as aux
from ch1_axi_archive_driver import CH1ArchiveDriver
from test_evidence_store import fixture,packed

class MainModel:
    def __init__(self,root,d,s):
        self.root=root;self.d=d;self.s=s;self.binding=store.descriptor_decode(d)
        self.count=self.binding['raw_count'];self.phase=5;self.fault=False
        self.coverage=set();self.writes=[];self.staging={};self.effects=0
        self.bad_crc=False;self.bad_padding=False;self.lost_reply=False
    def read(self,address):
        if address==0:return 0x48314331
        if address==4:return 1|2|(4 if self.phase==6 else 0)|(8 if self.phase==7 else 0)|(16 if self.fault else 0)|(self.phase<<8)
        if 0x100<=address<=0x150 and address%4==0:
            self.coverage.add(address);return int.from_bytes(self.d[address-0x100:address-0x100+4],'big')
        if 0x400<=address<0x400+16*self.count and address%16 in (0,4,8):
            index=(address-0x400)//16;part=(address%16)//4;self.coverage.add(address)
            raw=self.s[index*10:(index+1)*10]+b'\0\0'
            if self.bad_padding and part==2:raw=raw[:-1]+b'\1'
            return int.from_bytes(raw[part*4:part*4+4],'big')
        if address in (8,0x14,0x18):
            self.coverage.add(address)
            return {8:self.count,0x14:store.crc16(self.d),0x18:store.crc16(self.s)^(1 if self.bad_crc else 0)}[address]
        if address==0x20:return len(self.coverage)
        raise AssertionError(f'Unexpected main read {address:x}')
    def write(self,address,value):
        self.writes.append((address,value))
        if address!=0x60:
            if self.phase!=5:raise AssertionError('Retry incorrectly rewrote immutable staging')
            self.staging[address]=value;return
        if self.fault:raise RuntimeError('Bus denied faulted main proof')
        directory=self.root/'main'/f"epoch_{self.binding['epoch']:08x}_record_{self.binding['record_id']:08x}"
        # The model rejects confirmation before the real archive commit exists.
        manifest=json.loads((directory/'committed.json').read_text())
        if (directory/'descriptor.bin').read_bytes()!=self.d or (directory/'samples.bin').read_bytes()!=self.s:
            raise AssertionError('ACK before exact record persistence')
        if len(self.coverage)!=24+3*self.count:raise AssertionError('Missing actual delivered reads')
        expected={0x30:self.binding['epoch'],0x34:self.binding['record_id'],0x38:self.count,
                  0x3c:(store.crc16(self.d)<<16)|store.crc16(self.s)}
        for i in range(8):expected[0x40+i*4]=(self.binding['identity']>>(224-i*32))&0xffffffff
        if self.staging!=expected:raise AssertionError('Wrong main proof identity/fingerprints')
        if manifest['confirmation']['raw_count']!=self.count:raise AssertionError('Wrong saved archive')
        if self.phase==5:self.effects+=1;self.phase=7
        if self.lost_reply:self.lost_reply=False;raise OSError('Injected lost post-execution main reply')

class AuxModel:
    def __init__(self,root,events=()):
        self.root=root;self.queues={0:[],1:[]};self.snapshot=None;self.coverage=set()
        self.writes=[];self.staging={};self.pops=0;self.fault=False;self.bad_crc=False;self.lost_reply=False
        for raw in events:self.queues[aux.decode(raw)['kind']].append(raw)
    def read(self,address):
        if address==0:return 0x48314a31
        if address==4:return int(self.snapshot is not None)|(2 if self.fault else 0)
        if address in (8,12):return len(self.queues[0 if address==8 else 1])
        if 0x100<=address<=0x134 and address%4==0:
            if self.snapshot is None:raise AssertionError('No snapshot')
            self.coverage.add(address);offset=address-0x100
            return int.from_bytes((self.snapshot+b'\0\0')[offset:offset+4],'big')
        if address==0x18:
            self.coverage.add(address);return store.crc16(self.snapshot)^(1 if self.bad_crc else 0)
        if address==0x48:return 0x7fff if len(self.coverage)==15 else 0
        raise AssertionError(f'Unexpected aux read {address:x}')
    def write(self,address,value):
        self.writes.append((address,value))
        if address==0x10:
            if self.snapshot is not None:raise AssertionError('Snapshot replaced')
            self.snapshot=self.queues[value-1][0];self.coverage=set();self.staging={};return
        if address!=0x14:self.staging[address]=value;return
        event=aux.decode(self.snapshot)
        directory=self.root/'aux'/f"event_{event['epoch']:08x}_{event['kind']}_{event['seq']:08x}"
        json.loads((directory/'committed.json').read_text())
        if (directory/'event.bin').read_bytes()!=self.snapshot:raise AssertionError('Aux ACK before persistence')
        if len(self.coverage)!=15 or self.staging!={0x20:event['epoch'],0x24:event['seq'],0x28:event['kind'],0x2c:store.crc16(self.snapshot)}:
            raise AssertionError('Wrong auxiliary proof or missing reads')
        self.queues[event['kind']].pop(0);self.snapshot=None;self.pops+=1
        if self.lost_reply:self.lost_reply=False;raise OSError('Injected lost post-pop auxiliary reply')

def event_raw(d,kind=0,seq=1,tick=27100,has_byte=False,data=0x73,flags=2,bound=True):
    binding=store.descriptor_decode(d)
    return packed([(1,0),(32,binding['epoch']),(32,seq),(1,int(bound)),(1,kind),
                   (256,binding['identity'] if bound else 0),(32,binding['record_id'] if bound else 0),
                   (4,flags),(1,int(has_byte)),(8,data),(64,tick)])

class DriverTests(unittest.TestCase):
    def setUp(self):self.root=ROOT/'evidence/offline_driver_tests'/('test_'+uuid.uuid4().hex)
    def setup_record(self,name='max',reason=1,errors=(),events=()):
        d,s,raw,watermark=fixture(name,reason=reason,errors=errors)
        self.main=MainModel(self.root,d,s);self.bus=AuxModel(self.root,events)
        self.driver=CH1ArchiveDriver(self.main,self.bus,self.root)
        return d,s,raw,watermark
    def run_record(self,watermark,source=None):
        return self.driver.archive_current(watermark_epoch=1,watermark_tick=watermark,expected_payload=source)
    def test_maximum_all_reads_actual_files_then_one_proof(self):
        d,s,raw,w=self.setup_record();result=self.run_record(w,raw[18:-2])
        self.assertTrue(result['business_success']);self.assertFalse(result['hardware_retirement_verified'])
        self.assertEqual(len(self.main.coverage),1620);self.assertEqual(self.main.effects,1)
        self.assertEqual((Path(result['evidence_dir'])/'samples.bin').read_bytes(),s)
    def test_constructor_wrong_identity_performs_no_writes(self):
        self.setup_record();self.main.read=lambda address:0
        with self.assertRaises(RuntimeError):CH1ArchiveDriver(self.main,self.bus,self.root)
        self.assertFalse(self.main.writes);self.assertFalse(self.bus.writes)
    def test_sample_padding_denies_proof(self):
        _,_,_,w=self.setup_record();self.main.bad_padding=True
        with self.assertRaises(ValueError):self.run_record(w)
        self.assertFalse(self.main.writes)
    def test_bad_main_fingerprint_denies_proof(self):
        _,_,_,w=self.setup_record();self.main.bad_crc=True
        with self.assertRaises(ValueError):self.run_record(w)
        self.assertFalse(self.main.writes)
    def test_wrong_or_unfinalized_watermark_denies_proof(self):
        _,_,_,w=self.setup_record()
        with self.assertRaises(ValueError):self.driver.archive_current(watermark_epoch=2,watermark_tick=w)
        with self.assertRaises(ValueError):self.run_record(w-1)
        self.assertFalse(self.main.writes)
    def test_flag_only_event_saved_and_popped_before_main_proof(self):
        errors=[{'tick':27100,'flags':2,'has_byte':False,'data':0x73}]
        d,s,raw,w=self.setup_record('partial_error',2,errors)
        self.bus.queues[0].append(event_raw(d));result=self.run_record(w)
        self.assertEqual(self.bus.pops,1);self.assertFalse(result['business_success'])
        saved=json.loads((Path(result['evidence_dir'])/'auxiliary.json').read_text())
        self.assertEqual(saved['errors'],errors);self.assertEqual(len((Path(result['evidence_dir'])/'raw_packet.bin').read_bytes()),27)
    def test_bad_aux_crc_retains_queue_and_raw_diagnostic(self):
        d,_,_,w=self.setup_record();self.bus.queues[1].append(event_raw(d,1,tick=w+1));self.bus.bad_crc=True
        with self.assertRaises(ValueError):self.run_record(w)
        self.assertEqual(self.bus.pops,0);self.assertFalse(self.main.writes)
        self.assertTrue(list((self.root/'aux').glob('failed_*/event.bin')))
    def test_aux_commit_fsync_failure_never_pops(self):
        d,_,_,w=self.setup_record();self.bus.queues[1].append(event_raw(d,1,tick=w+1))
        original=store._write
        def failure(path,data):
            if path.name=='committed.json':raise OSError('Injected fsync failure')
            return original(path,data)
        with patch.object(store,'_write',side_effect=failure):
            with self.assertRaises(OSError):self.run_record(w)
        self.assertEqual(self.bus.pops,0);self.assertFalse(self.main.writes)
    def test_lost_aux_pop_reply_retry_rejoins_durable_error(self):
        errors=[{'tick':27100,'flags':2,'has_byte':False,'data':0x73}]
        d,_,_,w=self.setup_record('partial_error',2,errors);self.bus.queues[0].append(event_raw(d));self.bus.lost_reply=True
        with self.assertRaises(OSError):self.run_record(w)
        result=self.run_record(w+1)
        self.assertEqual(self.bus.pops,1);self.assertEqual(self.main.effects,1)
        self.assertEqual(json.loads((Path(result['evidence_dir'])/'auxiliary.json').read_text())['errors'],errors)
    def test_lost_main_commit_reply_cached_retry_does_not_restage_or_apply_twice(self):
        _,_,raw,w=self.setup_record();self.main.lost_reply=True
        with self.assertRaises(OSError):self.run_record(w,raw[18:-2])
        writes=len(self.main.writes);result=self.run_record(w+10,raw[18:-2])
        self.assertTrue(result['cached']);self.assertEqual(self.main.writes[writes:],[(0x60,1)])
        self.assertEqual(self.main.effects,1)
    def test_late_orphan_archived_independently_does_not_mutate_cached_main(self):
        d,_,raw,w=self.setup_record();first=self.run_record(w,raw[18:-2])
        self.bus.queues[1].append(event_raw(d,1,tick=w+2,has_byte=True,data=0xc7,flags=0))
        second=self.run_record(w+10,raw[18:-2]);self.assertTrue(second['cached']);self.assertEqual(self.bus.pops,1)
        self.assertEqual(json.loads((Path(first['evidence_dir'])/'auxiliary.json').read_text())['orphans'],[])
    def test_tampered_popped_aux_archive_blocks_main_proof(self):
        d,_,_,w=self.setup_record();self.bus.queues[1].append(event_raw(d,1,tick=w+1))
        saved=self.driver.drain_aux()[0];(Path(saved['evidence_dir'])/'event.json').write_text('{}')
        with self.assertRaises(ValueError):self.run_record(w)
        self.assertFalse(self.main.writes)
    def test_main_disk_failure_withholds_hardware_confirmation(self):
        _,_,_,w=self.setup_record();original=store._write
        def failure(path,data):
            if path.name=='committed.json':raise OSError('Injected main fsync failure')
            return original(path,data)
        with patch.object(store,'_write',side_effect=failure):
            with self.assertRaises(OSError):self.run_record(w)
        self.assertFalse(self.main.writes)
    def test_fault_after_disk_commit_keeps_archive_and_withholds_proof(self):
        _,_,_,w=self.setup_record();original=store.persist_record
        def fault(*args,**kwargs):
            result=original(*args,**kwargs);self.main.fault=True;return result
        with patch.object(store,'persist_record',side_effect=fault):
            with self.assertRaises(RuntimeError):self.run_record(w)
        self.assertFalse(self.main.writes);self.assertTrue(list((self.root/'main').glob('*/committed.json')))
    def test_dut_error_saved_as_failure_despite_valid_frame(self):
        _,_,_,w=self.setup_record('dut_error');result=self.run_record(w,b'')
        self.assertFalse(result['business_success']);self.assertEqual(self.main.effects,1)

    def test_empty_deadline_requires_descriptor_footer_only_and_real_archive(self):
        d=bytes.fromhex((ROOT/'vectors/axi_cache/empty_descriptor.mem').read_text().strip())
        self.main=MainModel(self.root,d,b'');self.bus=AuxModel(self.root)
        self.driver=CH1ArchiveDriver(self.main,self.bus,self.root)
        result=self.run_record(self.main.binding['close']+1)
        self.assertEqual(len(self.main.coverage),24);self.assertEqual(result['raw_count'],0)
        self.assertFalse(result['business_success']);self.assertEqual((Path(result['evidence_dir'])/'samples.bin').read_bytes(),b'')
    def test_missing_unique_read_coverage_denies_proof(self):
        _,_,_,w=self.setup_record();original=self.main.read
        self.main.read=lambda address:1619 if address==0x20 else original(address)
        with self.assertRaises(RuntimeError):self.run_record(w)
        self.assertFalse(self.main.writes)
    def test_exact_aux_snapshot_retry_resyncs_then_pops_once(self):
        d,_,_,w=self.setup_record();raw=event_raw(d,1,tick=w+1)
        first=aux.persist_event(self.root/'aux',raw,store.crc16(raw))
        self.bus.queues[1].append(raw)
        saved=self.driver.drain_aux()[0]
        self.assertTrue(saved['cached']);self.assertEqual(saved['evidence_dir'],first['evidence_dir']);self.assertEqual(self.bus.pops,1)
    def test_changed_same_aux_sequence_preserves_original_and_denies_ack(self):
        d,_,_,w=self.setup_record();raw=event_raw(d,1,tick=w+1)
        first=aux.persist_event(self.root/'aux',raw,store.crc16(raw))
        self.bus.queues[1].append(event_raw(d,1,tick=w+1,data=0x74))
        with self.assertRaises(ValueError):self.driver.drain_aux()
        self.assertEqual(self.bus.pops,0);self.assertEqual((Path(first['evidence_dir'])/'event.bin').read_bytes(),raw)
    def test_journal_fault_stays_latched_after_durable_drain_and_main_proof_is_withheld(self):
        d,_,_,w=self.setup_record();self.bus.queues[1].append(event_raw(d,1,tick=w+1));self.bus.fault=True
        with self.assertRaises(RuntimeError):self.run_record(w)
        self.assertEqual(self.bus.pops,1);self.assertTrue(self.bus.fault);self.assertFalse(self.main.writes)
    def test_missing_bound_error_cannot_be_replaced_by_another_record(self):
        errors=[{'tick':27100,'flags':2,'has_byte':False,'data':0x73}]
        d,_,_,w=self.setup_record('partial_error',2,errors)
        unrelated=bytearray(event_raw(d));value=int.from_bytes(unrelated,'big')
        value^=1<<77 # record_id bit, preserves otherwise valid event
        self.bus.queues[0].append(value.to_bytes(54,'big'))
        with self.assertRaises(ValueError):self.run_record(w)
        self.assertEqual(self.bus.pops,1) # unrelated event safely archived independently
        self.assertFalse(self.main.writes) # cannot prove the main's missing UART error

if __name__=='__main__':unittest.main(verbosity=2)
