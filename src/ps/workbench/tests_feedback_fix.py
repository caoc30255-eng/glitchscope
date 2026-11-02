"""Production receipt schema, durable JSON publication and append-only repair tests."""
import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from common import ROOT,write
from feedback_contract import validate_feedback,verify_owner_receipt
from demo_authority import Authority,default_scope
JOB="4bbf6baf646e48499a9dd7763ffcfad2"
SESSION="session_00000050"

def receipt():
    return dict(record_id=1,kind='CONFIG',identity_hex='1234',result_sha256='a'*64,actual_receiver_B=dict(d=3,s=-1),labels={},evidence_quality='VALID',strict_retirement_verified=True,actual_READY_saved=True)

class FixTests(unittest.TestCase):
    def test_actual_feedback_shape_passes_without_translated_fields(self):
        r=receipt();self.assertNotIn('status',r);self.assertNotIn('strict_retired',r)
        o=SimpleNamespace(executor=SimpleNamespace(index=1),receipts=[r],feedback=SimpleNamespace(_feedback=lambda rid:copy.deepcopy(r)))
        self.assertEqual(verify_owner_receipt(o,1),r)
    def test_translated_record_not_feedback(self):
        with self.assertRaises(ValueError):validate_feedback(dict(record_id=1,status='VALID',strict_retired=True),1)
    def test_missing_strict_ready_and_bad_index_refused(self):
        for field,value in [('evidence_quality','UNKNOWN'),('strict_retirement_verified',False),('actual_READY_saved',False),('record_id',2),('kind','ITEM')]:
            r=receipt();r[field]=value
            with self.assertRaises(ValueError):validate_feedback(r,1)
    def test_original_recheck_failure_propagates(self):
        o=SimpleNamespace(executor=SimpleNamespace(index=1),receipts=[receipt()],feedback=SimpleNamespace(_feedback=lambda rid:dict()))
        with self.assertRaises(ValueError):verify_owner_receipt(o,1)
    def test_atomic_publication_no_overwrite_or_partial_target(self):
        p=Path(tempfile.mkdtemp())/'result.json'
        import common,os
        link=os.link
        def publish(a,b):
            self.assertFalse(Path(b).exists());json.loads(Path(a).read_bytes());link(a,b)
        with patch.object(common.os,'link',publish):write(p,dict(ok=True))
        with self.assertRaises(FileExistsError):write(p,dict(ok=False))
        self.assertEqual(json.loads(p.read_bytes()),dict(ok=True));self.assertEqual(len(list(p.parent.iterdir())),1)
if __name__=='__main__':unittest.main(verbosity=2)
