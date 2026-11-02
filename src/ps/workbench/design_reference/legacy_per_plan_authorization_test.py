"""Only filesystem/HTTP admission contracts. Synthetic approval fixtures never run live."""
import json,tempfile,sys,unittest
from pathlib import Path
from unittest.mock import patch
import server
from common import ROOT,sha

class ApprovalFlow(unittest.TestCase):
    def setUp(self):
        self.base=Path(tempfile.mkdtemp(prefix='approval_flow_test_',dir=str(ROOT.parent)))
        self.approvals=self.base/'approvals';self.approvals.mkdir();self.runs=self.base/'runs';self.runs.mkdir()
        self.plan=dict(sha256='a'*64,max_records=44)
        self.assets={k:str(self.base/k) for k in ('bit','hwh','native')}
        self.app=server.App(self.base/'data',live=dict(approvals=str(self.approvals),runs=str(self.runs),assets=self.assets))
    def test_1_missing_is_pending_and_writes_nothing(self):
        p=self.app.plan_authorization('scan',self.plan);self.assertFalse(p['ready']);self.assertEqual(p['state'],'WAITING_USER_APPROVAL');self.assertEqual(p['max_records'],44)
        self.assertFalse(list(self.approvals.iterdir()));self.assertFalse(list((self.app.data/'jobs').iterdir()))
    def test_2_missing_cannot_create_live_worker_job(self):
        with self.assertRaisesRegex(ValueError,'PLAN_NOT_AUTHORIZED'):
            self.app.submit('live_scan',dict(plan=self.plan,confirmation='START '+self.plan['sha256'][:12],manual_7010_ready=True))
        self.assertFalse(self.app.active);self.assertFalse(list((self.app.data/'jobs').iterdir()));self.assertNotIn('pynq',sys.modules)
    def test_3_unapproved_and_different_version_are_rejected(self):
        p=self.approvals/(self.plan['sha256']+'.json');p.write_text(json.dumps(dict(approved_by_user=False,reviewed_by_owner=False)),encoding='utf-8')
        self.assertEqual(self.app.plan_authorization('scan',self.plan)['state'],'APPROVAL_NEEDS_REVIEW')
        p.write_text(json.dumps(dict(approved_by_user=True,reviewed_by_owner=True,approval_reference='SYNTHETIC_NOT_HIL',schema='GLITCHSCOPE_UI_APPROVAL_V1',kind='scan',plan_sha256=self.plan['sha256'],max_records=44,ui_manifest_sha256='wrong-version')),encoding='utf-8')
        self.assertFalse(self.app.plan_authorization('scan',self.plan)['ready'])
    def test_4_ready_advisory_and_once_only_receipt(self):
        # Advisory-only fixture: hash reads are mocked for non-existent assets; no live worker is submitted.
        from live import ORIGINAL_ASSETS
        inner=dict(approved_by_user=True,reviewed_by_owner=True,plan_sha256=self.plan['sha256'],max_records=44,runs_directory=str(self.runs),asset_sha256=ORIGINAL_ASSETS,stages=dict(local_read_preflight=True,initialize_namespace_and_receiver=True,physical_records=True))
        a=dict(schema='GLITCHSCOPE_UI_APPROVAL_V1',approved_by_user=True,reviewed_by_owner=True,approval_reference='SYNTHETIC_NOT_HIL',kind='scan',plan_sha256=self.plan['sha256'],max_records=44,ui_manifest_sha256=sha(ROOT/'manifest.json'),runs_directory=str(self.runs),automatic_retry=False,automatic_reset=False,resume_allowed=False,training_authorized=False,stages=dict(overlay=True,initialize=True,physical_records=True),prior_occupied=707,cumulative_limit=751,asset_sha256=ORIGINAL_ASSETS,scanner_approval=inner)
        p=self.approvals/(self.plan['sha256']+'.json');p.write_text(json.dumps(a),encoding='utf-8');p.with_name(self.plan['sha256']+'.scanner.json').write_text(json.dumps(inner),encoding='utf-8')
        actual_sha=server.sha
        def mock_asset_hash(path):
            for k,v in self.assets.items():
                if str(path)==v:return ORIGINAL_ASSETS[k]
            return actual_sha(path)
        with patch.object(server,'sha',side_effect=mock_asset_hash):
            self.assertTrue(self.app.plan_authorization('scan',self.plan)['ready'])
            consumed=self.runs/'unified_ui_approval_consumed';consumed.mkdir();(consumed/(actual_sha(p)+'.json')).write_text('{}')
            self.assertEqual(self.app.plan_authorization('scan',self.plan)['state'],'ALREADY_USED')
        self.assertFalse(self.app.active);self.assertFalse(list((self.app.data/'jobs').iterdir()))

if __name__=='__main__':unittest.main(verbosity=2)
