"""Export v16 printable parts using a locally installed OpenSCAD. No hardware access."""
import argparse,json,subprocess,shutil
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--openscad',default=shutil.which('openscad') or shutil.which('openscad.com'));p.add_argument('--output',required=True);a=p.parse_args()
 if not a.openscad:raise SystemExit('Install OpenSCAD or supply --openscad /path/to/openscad')
 root=Path(__file__).resolve().parent;out=Path(a.output).resolve()
 if out==root or root in out.parents:raise SystemExit('Output must be outside the delivery source')
 out.mkdir(parents=True,exist_ok=False)
 for item in json.loads((root/'print_manifest.json').read_bytes())['parts']:
  target=out/item['file'];target.parent.mkdir(parents=True,exist_ok=True)
  subprocess.run([a.openscad,'--export-format','binstl','-D','PART="'+item['openscad_part']+'"','-o',str(target),str(root/'case_v16.scad')],check=True)
 print('Exported 14 printable part types; print quantities are in print_manifest.json. This is not a physical fit check.')
if __name__=='__main__':main()
