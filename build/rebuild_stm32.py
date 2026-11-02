"""Fresh external Keil build; reconstruct generated header spelling, never flash."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(keil,output,project_root=None):
    root=Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]
    source=root/'src/stm32';out=Path(output).resolve()
    if out==root or root in out.parents:raise ValueError('OUTPUT_MUST_BE_EXTERNAL')
    out.mkdir(parents=True,exist_ok=False)
    inputs={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file() and not any(n in ('Objects','Listings','__pycache__') for n in p.parts)}
    copied=out/'project';shutil.copytree(source,copied,ignore=shutil.ignore_patterns('Objects','Listings','__pycache__'))
    spelling=[]
    for p in (copied/'keil').rglob('rte_components.h'):
        q=p.with_name('RTE_Components.h');p.rename(q);spelling.append(dict(source=p.relative_to(copied).as_posix(),generated=q.relative_to(copied).as_posix(),bytes_unchanged=True))
    tool=Path(keil).resolve();project=copied/'keil/stm32_image_dut_v0_4.uvprojx';log=out/'build.log'
    env=dict(os.environ);env['TEMP']=env['TMP']=str(out)
    start=time.time();r=subprocess.run([str(tool),'-r',str(project),'-t','Image_DUT_v0_4','-o',str(log)],cwd=project.parent,env=env,capture_output=True,timeout=180,creationflags=0x08000000 if os.name=='nt' else 0)
    (out/'console.log').write_bytes(r.stdout+r.stderr)
    text=log.read_text(encoding='utf-8',errors='replace') if log.exists() else ''
    artifacts={p.name:sha(p) for p in (copied/'keil/Objects').glob('*') if p.suffix.lower() in ('.hex','.axf','.map')}
    for n,h in inputs.items():
        if sha(source/n)!=h:raise ValueError('SOURCE_CHANGED_DURING_BUILD:'+n)
    reference=root/'board/firmware/stm32/stm32_image_dut_v0_4.hex';expected=sha(reference)
    ok=r.returncode==0 and '0 Error(s), 0 Warning(s)' in text and artifacts.get('STM32_Image_DUT_v0_4.hex')==expected
    report=dict(status='PASS_FRESH_BUILD_HEX_IDENTICAL' if ok else 'FAILED_BUILD_RETAIN_FILES',returncode=r.returncode,inputs=inputs,tool=str(tool),generated_header_spelling=spelling,artifacts=artifacts,accepted_hex_sha256=expected,wall_seconds=time.time()-start,hardware_access=False,flash_download=False)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report['status']);return ok
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--keil',required=True);p.add_argument('--output',required=True);p.add_argument('--project-root');a=p.parse_args();sys.exit(0 if run(a.keil,a.output,a.project_root) else 2)
