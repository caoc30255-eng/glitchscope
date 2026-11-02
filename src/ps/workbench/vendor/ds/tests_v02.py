"""Meaningful data-integrity/partial-state tests; fixtures never become HIL labels."""
from pathlib import Path
from unittest.mock import patch
import unittest,tempfile,json,shutil,threading,os,copy,hashlib,uuid
from contextlib import contextmanager
import workbench as w
from report_export import verify_output,safe_json,viewer_item
from evidence_input import decode_config,open_session,read_item,verify_stable
from tests_offline import all64

@contextmanager
def scratch():
    # Keep synthetic fixtures in a named, writable directory, never inside the kit.
    # No recursive deletion or permission edits are performed.
    base=Path(os.environ.get('WORKBENCH_TEST_ROOT',str(Path(__file__).resolve().parent.parent/'_ds_workbench_test_runs'))).resolve()
    base.mkdir(parents=True,exist_ok=True);root=base/('case_'+uuid.uuid4().hex);root.mkdir()
    yield str(root)

def commit(folder,files):
    folder.mkdir(parents=True,exist_ok=True);manifest={}
    for n,data in files.items():
        (folder/n).write_bytes(data);manifest[n]=hashlib.sha256(data).hexdigest()
    (folder/'committed.json').write_text(json.dumps(dict(files=manifest)),encoding='utf-8')

class UnitChecks(unittest.TestCase):
    def test_threshold_region_separate_from_minimax(self):
        summary=w.summarize(all64());w.add_regions(summary,0,0)
        self.assertTrue(summary['threshold_candidate_region']);self.assertEqual(summary['hardware_verified_region'],[])
    def test_integrity_block_withdraws_every_recommendation(self):
        summary=w.summarize(all64());w.add_regions(summary,10000,100,True)
        self.assertFalse(summary['global_minimax_candidate_set']);self.assertFalse(summary['threshold_candidate_region'])
        self.assertTrue(all(not p['eligible_for_global_software_ranking'] for p in summary['profiles']))
    def test_threshold_bool_and_negative_refused(self):
        for value in (-1,True):
            with self.assertRaises(ValueError):w.add_regions(w.summarize(all64()),value,0)
    def test_html_payload_cannot_close_script(self):
        raw=safe_json({'name':'</script><img src=x onerror=alert(1)>&\u2028'})
        self.assertNotIn('<',raw);self.assertEqual(json.loads(raw)['name'],'</script><img src=x onerror=alert(1)>&\u2028')
    def test_missing_wave_is_not_idealized(self):
        p=viewer_item(dict(record_id=2,state='NO_MARK_WINDOW'),dict(retained_phases=[]),{},None)
        self.assertIsNone(p['raw']);self.assertIsNone(p['source']);self.assertFalse(p['profiles'])
    def test_measured_missing_is_not_zero_error_sample(self):
        p=w.aggregate_measured([dict(metrics=None)])['B']
        self.assertEqual(p['retired_items_with_bytes'],0);self.assertEqual(p['equal_length_items'],0)
    def test_atomic_output_does_not_overwrite(self):
        with scratch() as d:
            p=Path(d)/'one.json';w.write(p,{'one':1})
            with self.assertRaises(ValueError):w.write(p,{'two':2})
            self.assertEqual(json.loads(p.read_bytes()),{'one':1})
    def test_report_verifier_rejects_tampering(self):
        from report_export import seal_output
        with scratch() as d:
            p=Path(d);(p/'summary.json').write_text('{}');seal_output(p);verify_output(p)
            (p/'summary.json').write_text('{"forged":true}')
            with self.assertRaisesRegex(ValueError,'OUTPUT_CHANGED'):verify_output(p)
    def test_source_guard_never_creates_lock(self):
        with scratch() as d:
            root=Path(d)/'session';root.mkdir()
            with w.source_gate(root):pass
            self.assertFalse((root.parent/'exclusive.lock').exists())
    def test_output_overlap_rejected_before_reading(self):
        with scratch() as d:
            root=Path(d)/'source';root.mkdir()
            with patch.object(w,'verify_package',return_value=1):
                with self.assertRaisesRegex(ValueError,'OUTPUT_OVERLAPS_INPUT'):w.run(root,root/'new')
            self.assertFalse((root/'new').exists())
    def test_notebook_autosave_outputs_allowed(self):
        with scratch() as d:
            root=Path(d)/'kit';shutil.copytree(w.ROOT,root)
            p=root/'ds_analysis.ipynb';n=json.loads(p.read_bytes())
            cell=next(c for c in n['cells'] if c['cell_type']=='code');cell['execution_count']=77;cell['outputs']=[dict(output_type='stream',name='stdout',text='synthetic output\n')]
            p.write_text(json.dumps(n),encoding='utf-8');w.verify_package(root)
    def test_notebook_code_change_rejected(self):
        with scratch() as d:
            root=Path(d)/'kit';shutil.copytree(w.ROOT,root)
            p=root/'ds_analysis.ipynb';n=json.loads(p.read_bytes())
            cell=next(c for c in n['cells'] if c['cell_type']=='code');cell['source'].append('\nprint("changed")\n')
            p.write_text(json.dumps(n),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'NOTEBOOK_CODE_CHANGED'):w.verify_package(root)

class HistoricalChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=Path(os.environ.get('IMAGE64_EVIDENCE','__not_provided__'))
        if not cls.source.is_dir():raise unittest.SkipTest('Historical source not supplied')
    def subset(self,root):
        for rel in ('EXECUTOR/plan','EXECUTOR/random_schedule','EXECUTOR/record_00000001','EXECUTOR/record_00000002',
                    'CH0/epoch_10000027_record_00000001','CH0/epoch_10000027_record_00000002',
                    'admission/epoch_10000027_record_00000001','admission/epoch_10000027_record_00000002',
                    'MARK/epoch_10000027_record_00000002'):
            shutil.copytree(self.source/rel,root/rel)
    def test_config_received_and_source_binding(self):
        s=open_session(self.source);self.assertEqual(s['config']['item_total'],64);self.assertEqual(s['actual_profile'],dict(d=3,s=-1))
    def test_bad_config_crc_rejected(self):
        source=(self.source/'EXECUTOR/plan/source.bin').read_bytes();raw=bytearray((self.source/'EXECUTOR/plan/config.bin').read_bytes());raw[-1]^=1
        with self.assertRaisesRegex(ValueError,'CONFIG_CRC'):decode_config(raw,source)
    def test_partial64_report_has_no_global_candidate(self):
        with scratch() as d:
            root=Path(d)/'source';out=Path(d)/'analysis';self.subset(root)
            with patch.object(w,'verify_package',return_value=1):r=w.run(root,out,progress=lambda *a:None)
            self.assertEqual(r['provided_ITEMS'],1);self.assertFalse(r['complete64']);self.assertFalse(r['global_minimax_candidate_set']);verify_output(out)
    def test_corrupt_capture_blocks_all_remaining(self):
        with scratch() as d:
            root=Path(d)/'source';out=Path(d)/'analysis';self.subset(root)
            p=root/'MARK/epoch_10000027_record_00000002/saved/samples.bin';raw=bytearray(p.read_bytes());raw[2000]^=1;p.write_bytes(raw)
            with patch.object(w,'verify_package',return_value=1):r=w.run(root,out,progress=lambda *a:None)
            self.assertEqual(r['job_state'],'BLOCKED_INTEGRITY');self.assertFalse(r['global_minimax_candidate_set']);verify_output(out)
    def test_missing_capture_is_gap_not_integrity_success(self):
        with scratch() as d:
            root=Path(d)/'source';self.subset(root)
            p=root/'MARK/epoch_10000027_record_00000002/saved/committed.json';p.rename(p.with_suffix('.held'))
            self.assertEqual(read_item(open_session(root),2)['state'],'MISSING_WINDOW')
    def test_disabled_profile_no_capture_is_explicit(self):
        with scratch() as d:
            root=Path(d)/'source';self.subset(root);s=open_session(root)
            # Synthetic metadata fixture only; not reported as a measured disabled run.
            s['plan']['requests'][0]['fault']=None
            p=root/'EXECUTOR/record_00000002/intent';intent=json.loads((p/'intent.json').read_bytes());intent['fault']=None
            commit(p,{'intent.json':json.dumps(intent).encode(),'request.bin':(p/'request.bin').read_bytes()})
            rd=root/'EXECUTOR/record_00000002/result';result=json.loads((rd/'result.json').read_bytes())
            result['MPG1_pre_retirement']['configured_points']=result['MPG1_pre_retirement']['emitted_points']=0
            result['profile']=None
            commit(rd,{'result.json':json.dumps(result).encode()})
            marker=root/'MARK/epoch_10000027_record_00000002';marker.rename(marker.with_name(marker.name+'_not_used_fixture'))
            self.assertEqual(read_item(s,2)['state'],'NO_MARK_WINDOW')
    def test_actual_emitted_count_is_bound_to_plan(self):
        with scratch() as d:
            root=Path(d)/'source';self.subset(root);s=open_session(root)
            rd=root/'EXECUTOR/record_00000002/result';r=json.loads((rd/'result.json').read_bytes());r['MPG1_pre_retirement']['emitted_points']-=1
            commit(rd,{'result.json':json.dumps(r).encode()})
            with self.assertRaisesRegex(ValueError,'POINT_COUNT'):read_item(s,2)
    def test_unknown_intent_no_result_remains_unknown(self):
        with scratch() as d:
            root=Path(d)/'source';self.subset(root);s=open_session(root)
            p=root/'EXECUTOR/record_00000002/result/result.json';p.rename(p.with_suffix('.held'))
            self.assertEqual(read_item(s,2)['state'],'UNKNOWN_OR_UNRETIRED')
    def test_changed_source_after_load_detected(self):
        with scratch() as d:
            root=Path(d)/'source';self.subset(root);s=open_session(root)
            p=root/'EXECUTOR/plan/source.bin';raw=bytearray(p.read_bytes());raw[0]^=1;p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'INPUT_CHANGED'):verify_stable(s)
    def test_cancel_before_first_item_still_exports(self):
        with scratch() as d:
            out=Path(d)/'analysis';stop=threading.Event();stop.set()
            with patch.object(w,'verify_package',return_value=1):r=w.run(self.source,out,stop_event=stop)
            self.assertEqual(r['job_state'],'CANCELLED');self.assertFalse(r['global_minimax_candidate_set']);verify_output(out)
    def test_failed_input_still_has_diagnostic_report(self):
        with scratch() as d:
            root=Path(d)/'missing';out=Path(d)/'analysis'
            with patch.object(w,'verify_package',return_value=1):r=w.run(root,out)
            self.assertEqual(r['job_state'],'BLOCKED_INTEGRITY');self.assertEqual(r['provided_ITEMS'],0);verify_output(out)
    def test_full27_expected_results_and_no_source_rewrite(self):
        p=Path(os.environ.get('WORKBENCH_OUTPUT','__missing__'))
        if not (p/'summary.json').exists():self.skipTest('Full analysis output not supplied')
        s=json.loads((p/'summary.json').read_bytes());self.assertEqual(s['global_minimax_candidate_set'],[dict(d=4,s=-2)])
        self.assertEqual(s['actual_full_frame_observations']['B']['payload_bit_errors'],3169)
        self.assertEqual(s['actual_full_frame_observations']['B']['frame_correct'],39)
        self.assertFalse(s['threshold_candidate_region']);verify_output(p)
        for name,proof in json.loads((p/'input_manifest.json').read_bytes()).items():self.assertEqual(hashlib.sha256((self.source/name).read_bytes()).hexdigest(),proof['sha256'])

if __name__=='__main__':unittest.main(verbosity=2)
