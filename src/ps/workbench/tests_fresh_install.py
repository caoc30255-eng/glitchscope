"""Temporary filesystem/fake platform checks; no real grants, PYNQ or FPGA calls."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from common import ROOT,sha,digest
from installation_state import create_fresh,fresh_identity,validate_registries,installed_config,check_clock_environment,CONFIRMATION
from demo_authority import Authority
from runtime_lease import acquire_runtime_lock

class FreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.assets={}
        for name in ('bit','hwh','native'):
            p=self.base/(name+'.bin');p.write_bytes(('SYNTHETIC_'+name).encode());self.assets[name]=str(p)
        self.receipt=self.base/'software.json';self.receipt.write_text(json.dumps(dict(status='PASS_TARGET_DEMO_SOFTWARE',ui_manifest_sha256=sha(ROOT/'manifest.json'),hardware_access=False,new_STARTs=0)))
    def tearDown(self):self.temp.cleanup()
    def fresh(self):return create_fresh(self.base/'new_runs',self.assets,self.receipt,CONFIRMATION)
    def test_empty_origin_zero_budget_and_no_implicit_grant(self):
        c=self.fresh();v=fresh_identity(c)
        self.assertEqual(v['initial_budget'],0);self.assertEqual(validate_registries(c['runs'],v),[])
        self.assertEqual((Path(c['runs'])/'namespace_allocations.jsonl').read_bytes(),b'')
        a=Authority.for_live(c);self.assertIsNone(a.status()['active_round']);self.assertFalse((a.root/'ledger.jsonl').exists());self.assertEqual(a.legacy_floor(),0)
    def test_existing_root_is_never_reused_or_erased(self):
        p=self.base/'new_runs';p.mkdir();(p/'evidence.txt').write_text('KEEP')
        with self.assertRaisesRegex(ValueError,'NEW_RUNS'):self.fresh()
        self.assertEqual((p/'evidence.txt').read_text(),'KEEP')
    def test_wrong_confirmation_creates_nothing(self):
        with self.assertRaisesRegex(ValueError,'CONFIRMATION'):create_fresh(self.base/'new_runs',self.assets,self.receipt,'automatic')
        self.assertFalse((self.base/'new_runs').exists())
    def test_legacy_accounting_floor_is_preserved(self):
        p=self.base/'legacy';p.mkdir();a=Authority.for_live(dict(runs=str(p)));self.assertEqual(a.legacy_floor(),707)
    def test_fresh_marker_requires_binding_and_cannot_be_silently_lost(self):
        c=self.fresh();bad=dict(c);bad.pop('fresh_installation_sha256')
        with self.assertRaisesRegex(ValueError,'BINDING'):fresh_identity(bad)
        (Path(c['runs'])/'fresh_installation.json').unlink()
        with self.assertRaisesRegex(ValueError,'MARKER'):fresh_identity(c)
    def test_asset_tamper_refused(self):
        c=self.fresh();Path(c['assets']['bit']).write_bytes(b'TAMPER')
        with self.assertRaisesRegex(ValueError,'ASSETS_CHANGED'):fresh_identity(c)
    def test_legacy_namespace_rows_cannot_masquerade_as_fresh(self):
        c=self.fresh();(Path(c['runs'])/'namespace_allocations.jsonl').write_text('{"number":1}\n')
        with self.assertRaisesRegex(ValueError,'ORIGIN'):fresh_identity(c)
    def test_actual_allocated_fresh_row_remains_valid(self):
        c=self.fresh();v=fresh_identity(c);(Path(c['runs'])/'namespace_allocations.jsonl').write_text(json.dumps(dict(number=1,installation_id=v['id']))+'\n')
        self.assertEqual(validate_registries(c['runs'],v)[0]['number'],1)
    def test_broken_namespace_sequence_and_trial_sequence_rejected(self):
        c=self.fresh();v=fresh_identity(c);p=Path(c['runs'])/'namespace_allocations.jsonl'
        p.write_text(json.dumps(dict(number=2,installation_id=v['id']))+'\n')
        with self.assertRaisesRegex(ValueError,'HISTORY'):fresh_identity(c)
        p.write_text('');t=Path(c['runs'])/'trial_registry/trial_0002.json';t.write_text('{"trial_id":2}')
        with self.assertRaisesRegex(ValueError,'TRIAL_HISTORY'):fresh_identity(c)
    def test_trial_identity_and_legacy_artifact_refused(self):
        c=self.fresh();t=Path(c['runs'])/'trial_registry/trial_0001.json';t.write_text('{"trial_id":2}')
        with self.assertRaisesRegex(ValueError,'TRIAL_ID'):fresh_identity(c)
        t.unlink();(Path(c['runs'])/'unified_ui_approval_consumed').mkdir()
        with self.assertRaisesRegex(ValueError,'LEGACY_ACCOUNTING'):fresh_identity(c)
    def test_cannot_nest_a_new_installation_under_old_runs(self):
        old=self.base/'old';old.mkdir();(old/'namespace_allocations.jsonl').write_text('')
        with self.assertRaisesRegex(ValueError,'NEST'):create_fresh(old/'new',self.assets,self.receipt,CONFIRMATION)
    def test_installed_binding_survives_scan_authority_reconstruction(self):
        c=self.fresh();rebuilt=installed_config(c['runs'],c);self.assertEqual(fresh_identity(rebuilt)['id'],fresh_identity(c)['id']);self.assertEqual(Authority.for_live(rebuilt).legacy_floor(),0)
    def test_current_profile_readonly_check_and_reference_mismatch(self):
        dt=self.base/'dt';dt.mkdir();(dt/'ps-clk-frequency').write_bytes((33333333).to_bytes(4,'big'))
        good=SimpleNamespace(_instance=type('_ClocksZynq',(),{'_ref_clk_mhz':50.0})())
        self.assertFalse(check_clock_environment(good,'2.7.0',dt)['clock_setter_called'])
        bad=SimpleNamespace(_instance=type('_ClocksZynq',(),{'_ref_clk_mhz':33.333333})())
        with self.assertRaisesRegex(ValueError,'REFERENCE_ENVIRONMENT'):check_clock_environment(bad,'2.7.0',dt)
        with self.assertRaisesRegex(ValueError,'PYNQ27'):check_clock_environment(good,'2.4',dt)
    def test_wrong_or_missing_dt_reference_refused(self):
        dt=self.base/'dt';dt.mkdir();clocks=SimpleNamespace(_instance=type('_ClocksZynq',(),{'_ref_clk_mhz':50.0})())
        with self.assertRaisesRegex(ValueError,'UNIQUE'):check_clock_environment(clocks,'2.7',dt)
        (dt/'ps-clk-frequency').write_bytes((50000000).to_bytes(4,'big'))
        with self.assertRaisesRegex(ValueError,'PROFILE_CHANGED'):check_clock_environment(clocks,'2.7',dt)
    def test_global_lease_excludes_other_installation_roots(self):
        a=self.base/'a';b=self.base/'b';a.mkdir();b.mkdir();g=self.base/'global.lock'
        lease=acquire_runtime_lock(a,g)
        try:
            with self.assertRaises((RuntimeError,OSError)):acquire_runtime_lock(b,g)
            self.assertEqual(Path(lease.name),a/'exclusive.lock');self.assertFalse(lease.closed)
        finally:lease.close()
        second=acquire_runtime_lock(b,g);second.close();self.assertTrue(second.closed);self.assertTrue(g.exists())
    def test_global_lease_is_exclusive_across_processes(self):
        a=self.base/'a';b=self.base/'b';a.mkdir();b.mkdir();g=self.base/'global.lock';lease=acquire_runtime_lock(a,g)
        code='import sys;sys.path.insert(0,sys.argv[1]);from runtime_lease import acquire_runtime_lock\ntry:\n x=acquire_runtime_lock(sys.argv[2],sys.argv[3])\nexcept (RuntimeError,OSError):sys.exit(42)\nx.close();sys.exit(0)'
        try:
            r=subprocess.run([sys.executable,'-B','-c',code,str(ROOT),str(b),str(g)],capture_output=True);self.assertEqual(r.returncode,42,r.stderr)
        finally:lease.close()
    def test_uncertain_cleanup_quarantines_across_roots(self):
        a=self.base/'a';b=self.base/'b';a.mkdir();b.mkdir();g=self.base/'global.lock';lease=acquire_runtime_lock(a,g);lease.quarantine('SYNTHETIC uncertain native close');lease.close()
        with self.assertRaisesRegex(RuntimeError,'QUARANTINED'):acquire_runtime_lock(b,g)
        self.assertFalse(json.loads(Path(str(g)+'.quarantine.json').read_bytes())['automatic_recovery'])
    def test_prepare_accepts_bound_fresh_zero_history_without_grant(self):
        import prepare_demo_install
        c=self.fresh();config=Path(c['runs'])/'live_config.json';expected={k:sha(p) for k,p in self.assets.items()}
        with patch.object(prepare_demo_install,'verify',return_value=0),patch.object(prepare_demo_install,'ASSETS',expected):prepare_demo_install.run(config)
        a=Authority.for_live(c);self.assertIsNone(a.status()['active_round']);binding=json.loads((a.root/'installation.json').read_bytes());self.assertEqual(binding['installation_mode'],'fresh');self.assertEqual(binding['fresh_installation_sha256'],c['fresh_installation_sha256'])
    def test_legacy_short_history_is_still_rejected(self):
        import prepare_demo_install
        runs=self.base/'legacy';runs.mkdir();(runs/'trial_registry').mkdir();(runs/'namespace_allocations.jsonl').write_text(''.join(json.dumps(dict(number=n))+'\n' for n in range(1,79)))
        c=dict(runs=str(runs),assets=self.assets,software_receipt=str(self.receipt));config=self.base/'legacy.json';config.write_text(json.dumps(c));expected={k:sha(p) for k,p in self.assets.items()}
        with patch.object(prepare_demo_install,'verify',return_value=0),patch.object(prepare_demo_install,'ASSETS',expected),self.assertRaisesRegex(ValueError,'ORIGINAL_NAMESPACE'):prepare_demo_install.run(config)
    def test_wrong_clock_environment_fails_before_overlay_or_mmio(self):
        import live
        events=[]
        class Lock:
            closed=False
            def close(self):self.closed=True
        lock=Lock();pynq=SimpleNamespace(__version__='2.7.0',Clocks=SimpleNamespace(_instance=type('_ClocksZynq',(),{'_ref_clk_mhz':33.333333})()),Overlay=lambda *a:events.append('OVERLAY'),MMIO=lambda *a:events.append('MMIO'))
        authority=SimpleNamespace(settle=lambda *a,**kw:events.append('SETTLED'),task=lambda *a:{})
        gate=SimpleNamespace(runs=self.base,check=lambda:None,reserve=lambda:None,authority=authority,job_id='SYNTHETIC_JOB')
        out=self.base/'result';out.mkdir()
        with patch('runtime_lease.acquire_runtime_lock',return_value=lock),patch.object(live.platform,'system',return_value='Linux'),patch.object(live.platform,'machine',return_value='armv7l'),patch.dict(sys.modules,{'pynq':pynq}),self.assertRaisesRegex(ValueError,'REFERENCE_ENVIRONMENT'):live.initialize(gate,out,lambda **v:None)
        self.assertEqual(events,['SETTLED']);self.assertTrue(lock.closed)
if __name__=='__main__':unittest.main()
