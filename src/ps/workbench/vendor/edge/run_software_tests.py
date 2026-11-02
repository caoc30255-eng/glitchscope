"""Run contracts with retained synthetic fixtures (no device services)."""
from pathlib import Path
import sys,os,uuid,unittest,tempfile,json,contextlib
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT),str(ROOT/'backend')]

def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    fixtures=output/'synthetic_fixtures';fixtures.mkdir()
    os.environ['EDGEAI_TEST_ROOT']=str(fixtures)
    class RetainedTemporaryDirectory:
        def __init__(self,*a,**kw):
            p=fixtures/('tmp_'+uuid.uuid4().hex);p.mkdir();self.name=str(p)
        def cleanup(self):pass
        def __enter__(self):return self.name
        def __exit__(self,*a):pass
    from unittest.mock import patch
    with patch.object(tempfile,'TemporaryDirectory',RetainedTemporaryDirectory):
        suite=unittest.TestSuite()
        for name in ('tests_backend','tests_v02','tests_mmio_binding','tests_edge','tests_oss'):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
        with (output/'tests.log').open('w',encoding='utf-8') as log:
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    summary=dict(status='PASS_SOFTWARE_CONTRACTS' if result.wasSuccessful() else 'FAIL_SOFTWARE_CONTRACTS',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        hardware_access=False,new_STARTs=0,fixture_scope='Retained synthetic state and register models; not observed hardware records')
    (output/'test_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2));return result.wasSuccessful()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();raise SystemExit(0 if run(a.output) else 1)
