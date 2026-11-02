"""Offline synthetic descriptors around frozen real protocol bytes; no hardware."""
from pathlib import Path
import sys,json,uuid,unittest,binascii
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
import ch1_evidence_store as store

def packed(parts):
    value=0;bits=0
    for width,item in parts:value=(value<<width)|item;bits+=width
    return value.to_bytes((bits+7)//8,'big')

def fixture(name='normal',kind=1,reason=1,errors=()):
    raw=bytes(int(x,16) for x in (ROOT/'vectors'/f'{name}.mem').read_text().split())
    identity=int.from_bytes(packed([(37,0),(32,0x10203040),(32,7),(32,1),(3,0),(32,1),
                                    (32,1),(8,2),(16,3),(16,4),(8,1),(8,0)]),'big')
    ticks=[100+1000*i for i in range(len(raw))];close=(ticks[-1]+2000) if ticks else 800000
    if reason==5:close=800000
    observed=0
    for error in errors:observed|=error['flags']
    descriptor=packed([(32,1),(1,0),(256,identity),(32,17),(2,kind),(8,reason),(16,len(raw)),
                       (64,50),(64,800000),(64,close),(1,int(reason==1)),
                       (8,raw[15] if kind==1 and len(raw)>15 else 0),
                       (8,raw[14] if kind==1 and len(raw)>14 else 0),
                       (16,int.from_bytes(raw[8:10],'big') if kind!=1 else 0),
                       (32,len(errors)),(4,observed),(64,errors[0]['tick'] if errors else 0)])
    samples=b''.join(((byte<<68)|tick).to_bytes(10,'big') for byte,tick in zip(raw,ticks))
    return descriptor,samples,raw,close+1

class EvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_store_tests'/('test_'+uuid.uuid4().hex)
    def save(self,name='normal',kind=1,reason=1,errors=(),expected=True,**kwargs):
        d,s,raw,watermark=fixture(name,kind,reason,errors)
        source=raw[18:-2] if expected and kind==1 else None
        args={'errors':errors,'orphans':[],'watermark_tick':watermark,'expected_payload':source}
        args.update(kwargs)
        return store.persist_record(self.root,d,s,binascii.crc_hqx(d,0xffff),binascii.crc_hqx(s,0xffff),**args)
    def test_max_packet_exact_archive_and_full_samples(self):
        result=self.save('max');self.assertTrue(result['business_success']);self.assertEqual(result['raw_count'],532)
        path=Path(result['evidence_dir']);raw=fixture('max')[2]
        self.assertEqual((path/'raw_packet.bin').read_bytes(),raw)
        self.assertEqual(len((path/'samples.bin').read_bytes()),5320)
        self.assertTrue((path/'committed.json').is_file())
    def test_exact_retry_cached_and_verified(self):
        first=self.save();second=self.save();self.assertFalse(first['cached']);self.assertTrue(second['cached'])
        self.assertEqual(first['identity_hex'],second['identity_hex'])
    def test_packet_crc_alone_cannot_prove_source_pixels(self):
        result=self.save(expected_payload=b'wrong source')
        self.assertFalse(result['business_success']);self.assertEqual(result['raw_count'],276)
    def test_no_source_reference_cannot_claim_image_success(self):
        self.assertFalse(self.save(expected=False)['business_success'])
    def test_good_and_error_management_acks_remain_distinct(self):
        good=self.save('config_ack',kind=2,expected=False);self.assertTrue(good['business_success'])
        self.root=ROOT/'evidence/offline_store_tests'/('test_'+uuid.uuid4().hex)
        bad=self.save('config_ack_error',kind=2,expected=False);self.assertFalse(bad['business_success'])
    def test_bad_report_crc_preserved_as_failure_evidence(self):
        result=self.save('bad_crc',reason=2)
        self.assertFalse(result['business_success'])
        self.assertEqual((Path(result['evidence_dir'])/'raw_packet.bin').read_bytes(),fixture('bad_crc',reason=2)[2])
    def test_wrong_wire_identity_preserved_and_never_success(self):
        result=self.save('wrong_id',reason=2);self.assertFalse(result['business_success'])
    def test_valid_flag_only_uart_failure_never_invents_byte(self):
        errors=[{'tick':27100,'flags':2,'has_byte':False,'data':0x73}]
        result=self.save('partial_error',reason=2,errors=errors)
        self.assertFalse(result['business_success']);self.assertEqual(result['raw_count'],27)
        path=Path(result['evidence_dir'])
        self.assertEqual(len((path/'raw_packet.bin').read_bytes()),27)
        self.assertFalse(json.loads((path/'auxiliary.json').read_text())['errors'][0]['has_byte'])
    def test_missing_uart_error_journal_no_confirmation(self):
        errors=[{'tick':27100,'flags':2,'has_byte':False,'data':0}]
        d,s,_,watermark=fixture('partial_error',reason=2,errors=errors)
        with self.assertRaises(ValueError):store.persist_record(self.root,d,s,store.crc16(d),store.crc16(s),errors=[],orphans=[],watermark_tick=watermark)
        self.assertFalse(list(self.root.glob('epoch_*/committed.json')))
    def test_prefix_even_with_recomputed_stream_crc_no_confirmation(self):
        d,s,_,watermark=fixture();s=s[:-10]
        with self.assertRaises(ValueError):store.persist_record(self.root,d,s,store.crc16(d),store.crc16(s),errors=[],orphans=[],watermark_tick=watermark)
        failed=next(self.root.glob('failed_*'));self.assertEqual((failed/'samples.bin').read_bytes(),s)
    def test_wrong_footer_no_confirmation(self):
        d,s,_,watermark=fixture()
        with self.assertRaises(ValueError):store.persist_record(self.root,d,s,store.crc16(d)^1,store.crc16(s),errors=[],orphans=[],watermark_tick=watermark)
    def test_same_record_context_change_preserves_original(self):
        first=self.save();path=Path(first['evidence_dir']);before=(path/'committed.json').read_bytes()
        with self.assertRaises(ValueError):self.save(expected_payload=b'different reference')
        self.assertEqual((path/'committed.json').read_bytes(),before);self.assertTrue(list(self.root.glob('conflict_*')))
    def test_tampered_existing_archive_never_cached_confirmation(self):
        result=self.save();path=Path(result['evidence_dir']);(path/'raw_packet.bin').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.save()
    def test_commit_failure_returns_no_confirmation_and_retry_resyncs(self):
        original=store._write
        def interrupted(path,raw):
            if path.name=='committed.json':
                with path.open('xb') as handle:handle.write(raw);handle.flush()
                raise OSError('injected commit fsync failure')
            original(path,raw)
        with patch.object(store,'_write',side_effect=interrupted):
            with self.assertRaises(OSError):self.save()
        real_sync=store.os.fsync
        with patch.object(store.os,'fsync',side_effect=real_sync) as sync:
            result=self.save();self.assertTrue(result['cached']);self.assertGreaterEqual(sync.call_count,8)
    def test_watermark_not_after_close_no_confirmation(self):
        d,s,_,watermark=fixture()
        with self.assertRaises(ValueError):store.persist_record(self.root,d,s,store.crc16(d),store.crc16(s),errors=[],orphans=[],watermark_tick=watermark-1)

    def test_overflow_byte_error_matches_exact_orphan_without_inventing_sample(self):
        event={'tick':27100,'flags':2,'has_byte':True,'data':0xa6}
        result=self.save('partial_error',reason=7,errors=[event],orphans=[event])
        self.assertFalse(result['business_success']);self.assertEqual(result['raw_count'],27)
        self.root=ROOT/'evidence/offline_store_tests'/('test_'+uuid.uuid4().hex)
        with self.assertRaises(ValueError):self.save('partial_error',reason=7,errors=[event],orphans=[dict(event,data=0xa7)])

    def test_nonoverflow_orphan_cannot_substitute_for_missing_error_sample(self):
        event={'tick':27100,'flags':2,'has_byte':True,'data':0xa6}
        with self.assertRaises(ValueError):self.save('partial_error',reason=2,errors=[event],orphans=[event])

    def test_crc_valid_dut_error_is_archived_but_never_image_success(self):
        result=self.save('dut_error',expected_payload=b'')
        self.assertFalse(result['business_success']);self.assertEqual(result['raw_count'],20)
        classification=json.loads((Path(result['evidence_dir'])/'classification.json').read_text())
        self.assertTrue(classification['capture_valid'])
        self.assertTrue(classification['raw_frame_crc_and_format_valid'])
        self.assertFalse(classification['business_success'])

if __name__=='__main__':unittest.main(verbosity=2)
