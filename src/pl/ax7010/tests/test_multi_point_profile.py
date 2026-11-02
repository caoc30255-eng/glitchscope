import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT.parent/'PS_UNKNOWN_Stop_v0_5_2026-10-17/host')]
from multi_point_profile import MultiPointProfile,decode_stats
from ch1_completion_ledger import _codec
from ch1_control_session import frame,decode_frame
from fault_profile import FaultProfile
import ch1_evidence_store as store

def binding():
    fields=dict(reserved=0,session=0x30000021,seq=2,route_epoch=0x20000021,slot=0,
        generation=2,run_id=0x10000021,image_id=1,trial_id=157,item_index=0,attempt_id=0,route_mode=0)
    value=0
    for k,width in store.IDENTITY:value=value<<width|fields[k]
    return value

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.inner=_codec().encode_item(0x10000021,1,157,0,64,0,0,bytes(range(256)))
        self.identity=binding()
    def test_full_payload_256_byte_range_fits_one_39byte_command(self):
        p=MultiPointProfile(20,256,0,15,20)
        request=p.build_request(self.identity,self.inner)
        kind,body=decode_frame(request)
        self.assertEqual(kind,0x3c);self.assertEqual(len(request),39)
        self.assertEqual(body[-1],255)
        self.assertTrue(p.verify_ack(request,frame(0x7c,body)))
    def test_one_point_payload_matches_legacy_suffix_but_type_is_distinct(self):
        p=MultiPointProfile(20,1,0,15,20)
        kind,body=decode_frame(p.build_request(self.identity,self.inner))
        self.assertEqual(body[-9:],FaultProfile(20,0,15,20).wire_suffix())
        with self.assertRaises(ValueError):p.verify_ack(frame(kind,body),frame(0x7a,body))
    def test_every_legal_count_is_encodable_without_wrapping(self):
        for count in range(1,257):
            p=MultiPointProfile(20,count,7,5,40)
            kind,body=decode_frame(p.build_request(self.identity,self.inner))
            self.assertEqual(body[-1]+1,count)
    def test_payload_end_does_not_touch_crc(self):
        self.assertEqual(MultiPointProfile(275,1,0,15,20).validate(self.inner)['count'],1)
        for first,count in ((19,1),(275,2),(20,257),(20,0),(276,1),(65535,2)):
            with self.subTest(first=first,count=count):
                with self.assertRaises(ValueError):MultiPointProfile(first,count,0,15,20).validate(self.inner)
    def test_wrong_identity_cannot_prepare_another_frame(self):
        wrong=_codec().encode_item(0x10000021,1,158,0,64,0,0,bytes(range(256)))
        with self.assertRaises(ValueError):MultiPointProfile(20,4,0,15,20).build_request(self.identity,wrong)
    def test_invalid_crc_and_gateway_rejected(self):
        bad=bytearray(self.inner);bad[20]^=1
        gateway=_codec().encode_item(0x10000021,1,157,0,64,0,1,bytes(range(256)))
        for inner in (bad,gateway):
            with self.assertRaises(ValueError):MultiPointProfile(20,4,0,15,20).validate(inner)
    def test_boolean_float_and_outside_interior_rejected(self):
        for args in ((20,True,0,15,20),(20,4.0,0,15,20),(20,4,8,15,20),
                     (20,4,0,4,20),(20,4,0,30,20),(20,4,0,15,0)):
            with self.assertRaises((ValueError,TypeError)):MultiPointProfile(*args).validate(self.inner)
    def test_changed_count_ack_denied(self):
        p=MultiPointProfile(20,4,0,15,20);request=p.build_request(self.identity,self.inner)
        kind,body=decode_frame(request)
        with self.assertRaises(ValueError):p.verify_ack(request,frame(0x7c,body[:-1]+b'\x04'))
    def test_statistics_are_counts_not_waveform_or_business_label(self):
        stats=decode_stats(0x4d504731,(4<<9)|4,1,[0]*7+[1])
        self.assertEqual(stats['expected_points'],4);self.assertEqual(stats['emitted_points'],4)
        self.assertTrue(stats['tx_done_fenced']);self.assertFalse(stats['source_fault'])
        self.assertNotIn('business_success',stats)
        with self.assertRaises(ValueError):decode_stats(0x48505131,0,0,[0]*8)
        with self.assertRaises(ValueError):decode_stats(0x4d504731,1<<18,0,[0]*8)

if __name__=='__main__':unittest.main()
