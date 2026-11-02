"""Verify/export an analysis directory. No hardware imports or source rewriting."""
from pathlib import Path
import argparse,json,zipfile,hashlib
from report_export import verify_output

def pack(output,archive):
    root=Path(output).resolve();target=Path(archive).resolve()
    if root==target or root in target.parents:raise ValueError('ARCHIVE_MUST_BE_OUTSIDE_REPORT')
    proof=verify_output(root)
    manifest=json.loads((root/'output_sha256.json').read_bytes())
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for n in sorted(manifest):z.write(root/n,root.name+'/'+n)
        z.write(root/'output_sha256.json',root.name+'/output_sha256.json')
    return dict(**proof,archive=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source_evidence_included=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--zip');a=p.parse_args()
    print(json.dumps(pack(a.output,a.zip) if a.zip else verify_output(a.output),ensure_ascii=False,indent=2))
