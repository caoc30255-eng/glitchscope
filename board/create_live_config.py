"""Create a config file only. Does not grant a round or touch devices."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runs',required=True);p.add_argument('--assets',required=True);p.add_argument('--receipt',required=True);p.add_argument('--output',required=True);a=p.parse_args()
assets=Path(a.assets).resolve();value=dict(runs=str(Path(a.runs).resolve()),software_receipt=str(Path(a.receipt).resolve()),assets=dict(bit=str(assets/'ax7020/h1_7020_evidence_candidate_v0_1.bit'),hwh=str(assets/'ax7020/h1_7020_evidence_candidate_v0_1.hwh'),native=str(assets/'native/libuartlite_service_v5_rt.so')))
for f in list(value['assets'].values())+[value['software_receipt']]:
    if not Path(f).is_file():raise SystemExit('Missing required file: '+f)
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
with out.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print('Configuration created; no hardware setup, no consent, no START:',out)
