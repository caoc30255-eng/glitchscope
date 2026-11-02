"""Synthetic, files-only lifecycle: one complete, one unknown, one cancelled."""
import argparse,hashlib,json
from pathlib import Path
import session_ledger as ledger
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.output)
    ledger.create(root,dict(max_records=3,record_ids=['setup','reference','measurement'],origin='SYNTHETIC',target='files_only_demo'))
    ledger.begin(root,'setup',dict(operation='synthetic_setup'))
    raw=root/'raw/setup.bin';raw.write_bytes(b'SYNTHETIC_ONLY_NOT_DEVICE_OUTPUT')
    ledger.complete(root,'setup',{'raw/setup.bin':hashlib.sha256(raw.read_bytes()).hexdigest()})
    ledger.begin(root,'reference',dict(operation='synthetic_reference'))
    ledger.unknown(root,'reference','Synthetic timeout fixture; no command was sent')
    report=ledger.cleanup(root,True,True)
    with (root/'demo_report.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
