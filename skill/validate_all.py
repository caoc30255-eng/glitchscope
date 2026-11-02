"""Offline skill tests. Outputs stay outside skill/; no PYNQ imports or FPGA calls."""
import argparse,ast,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
 root=Path(__file__).resolve().parent;out=Path(a.output).resolve();out.mkdir()
 scratch=out/'scratch';scratch.mkdir()
 # Use an explicitly chosen writable temporary root rather than a service-owned OS temp.
 env=dict(os.environ,TMPDIR=str(scratch),TEMP=str(scratch),TMP=str(scratch),PYTHONIOENCODING='utf-8',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
 syntax=[];results=[]
 skills=root/'skill' if (root/'skill').is_dir() else root
 for skill in sorted(skills.iterdir()):
  if not skill.is_dir() or not (skill/'SKILL.md').is_file():continue
  for path in skill.rglob('*.py'):
   ast.parse(path.read_text(encoding='utf-8'),filename=str(path),feature_version=(3,8));syntax.append(path.relative_to(root).as_posix())
  started=time.perf_counter();r=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(skill/'tests'),'-v'],capture_output=True,env=env)
  log=r.stdout+r.stderr;(out/(skill.name+'.log')).write_bytes(log)
  n=re.search(rb'Ran (\d+) tests?',log)
  row=dict(skill=skill.name,returncode=r.returncode,tests=int(n.group(1)) if n else None,seconds=time.perf_counter()-started,log_sha256=hashlib.sha256(log).hexdigest());results.append(row)
  print(skill.name,row,flush=True)
  if r.returncode:print(log.decode('utf-8','replace')[-1200:],flush=True)
 report=dict(status='PASS_OFFLINE_SKILL_TESTS' if all(x['returncode']==0 for x in results) else 'FAILED',results=results,total_tests=sum(x['tests'] or 0 for x in results),python38_syntax_files=len(syntax),hardware_access=False,new_physical_STARTs=0,models_trained=False,physical_cross_board_portability_verified=False,scope='Temporary-file, fake-bus and synthetic policy tests; historical project artifacts are separate')
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 return 0 if report['status'].startswith('PASS_') else 2
if __name__=='__main__':sys.exit(main())
