"""Run documented offline commands from relocated copies, never from a live board."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
 root=Path(__file__).resolve().parent;out=Path(a.output).resolve();out.mkdir();copied=out/'relocated';copied.mkdir();results=out/'results';results.mkdir();scratch=out/'scratch';scratch.mkdir()
 env=dict(os.environ,TEMP=str(scratch),TMP=str(scratch),TMPDIR=str(scratch),PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
 skills=root/'skill' if (root/'skill').is_dir() else root
 for skill in skills.iterdir():
  if skill.is_dir() and (skill/'SKILL.md').exists():shutil.copytree(skill,copied/skill.name,ignore=shutil.ignore_patterns('__pycache__'))
 runs=[]
 def call(skill,args,expected=0):
  r=subprocess.run([sys.executable,'-B']+[str(x) for x in args],cwd=str(copied/skill),env=env,capture_output=True)
  n=len(runs)+1;log=r.stdout+r.stderr;(out/('command_%02d.log'%n)).write_bytes(log)
  runs.append(dict(skill=skill,args=[str(x) for x in args],expected_returncode=expected,actual_returncode=r.returncode,passed=r.returncode==expected,log_sha256=hashlib.sha256(log).hexdigest()))
  if r.returncode!=expected:raise RuntimeError((skill,args,log.decode('utf-8','replace')))
 call('pynq-bringup',['scripts/preflight.py','--profile','examples/counter/profile.json','--output',results/'counter.json'])
 call('pynq-bringup',['scripts/preflight.py','--profile','examples/fir/profile.json','--output',results/'fir.json'])
 call('pynq-bringup',['scripts/check_notebook.py','--reference','examples/reference.ipynb','--candidate','examples/reformatted.ipynb'])
 for n in ['counter','fir']:
  call('axi-lite-contract-check',['scripts/contract.py','--contract','examples/'+n+'.json','--words','examples/'+n+'_words.json','--output',results/(n+'_registers.json')])
 call('axi-lite-contract-check',['scripts/generate_driver.py','--contract','examples/fir.json','--output',results/'generated'])
 call('axi-lite-contract-check',[results/'generated/test_generated.py'])
 call('rtl-reference-cosim',['scripts/make_demo_reference.py','--output',results/'reference'])
 # This only exercises the comparator CLI, explicitly not an RTL simulation.
 shutil.copy2(results/'reference/reference.csv',results/'synthetic_trace.csv')
 call('rtl-reference-cosim',['scripts/compare_trace.py','--reference',results/'reference/reference.csv','--actual',results/'synthetic_trace.csv','--spec',results/'reference/spec.json','--output',results/'trace_compare.json'])
 lines=(results/'synthetic_trace.csv').read_text(encoding='utf-8').splitlines();(results/'short_synthetic_trace.csv').write_text('\n'.join(lines[:-1])+'\n')
 call('rtl-reference-cosim',['scripts/compare_trace.py','--reference',results/'reference/reference.csv','--actual',results/'short_synthetic_trace.csv','--spec',results/'reference/spec.json','--output',results/'short_trace_rejected.json'],expected=2)
 call('hardware-session-evidence',['scripts/run_demo.py','--output',results/'session'])
 call('hardware-session-evidence',['scripts/session_ledger.py','audit','--root',results/'session'])
 call('edge-model-portability',['scripts/export_predictions.py','--runner','examples/demo_runner.py','--queries','examples/queries.json','--output',results/'actual.json'])
 call('edge-model-portability',['scripts/golden_check.py','--golden','examples/golden.json','--actual',results/'actual.json','--spec','examples/tolerance.json','--output',results/'golden.json'])
 call('edge-model-portability',['scripts/inference_bench.py','--runner','examples/demo_runner.py','--queries','examples/queries.json','--calls','50','--output',results/'bench.json'])
 call('bounded-active-benchmark',['scripts/benchmark.py','--experiment','examples/experiment.json','--output',results/'policies'])
 report=dict(status='PASS_RELOCATED_OFFLINE_EXAMPLES',commands=runs,command_count=len(runs),hardware_access=False,physical_cross_board_validation=False,new_generic_rtl_simulated=False,scope='Documented commands on copied skills; synthetic CSV comparison is not RTL simulation')
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report['status'],len(runs),'commands')
if __name__=='__main__':main()
