"""Read-only public historical audit and exact reviewer missing-READ32 probe."""
import argparse
import json
from pathlib import Path
import custom_plan
from custom_hardware_audit import load_trace, record_audit
from ch1_control_session import decode_frame
from fault_profile import FaultProfile


def run(sessions, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    records=[];rejections=[];removed_counts={}
    for root in sorted(Path(sessions).iterdir()):
        if not (root/'EXECUTOR').exists():continue
        trace=load_trace(root)
        removed={packet for packet in trace[1] if decode_frame(packet)[0]==0x7b}
        reduced=(trace[0],trace[1]-removed,trace[2]);removed_counts[root.name]=len(removed)
        for path in sorted((root/'EXECUTOR').glob('record_*/result/result.json')):
            rid=int(path.parent.parent.name.split('_')[1],16);result=json.loads(path.read_bytes())
            intent=json.loads((path.parent.parent/'intent/intent.json').read_bytes())
            profile=FaultProfile(**intent['fault']) if intent['fault'] else None
            proof=record_audit(root,rid,result,profile,trace)
            records.append(dict(session=root.name,**proof))
            try:record_audit(root,rid,result,profile,reduced)
            except ValueError as error:
                assert 'MMIO_REPLY_MISSING_FROM_CAPTURE' in str(error),str(error)
                rejections.append(dict(session=root.name,record_id=rid,reason=str(error)))
            else:raise AssertionError('Accepted absent raw READ32')
    assert len(records)==len(rejections)==70
    report=dict(status='PASS',scope='PUBLIC_HISTORICAL_RAW_NOT_NEW_ADAPTER_HARDWARE',records=records,
                missing_READ32_rejections=rejections,removed_unique_READ32_by_session=removed_counts,
                original_files_rewritten=False,new_physical_STARTs=0,hardware_acceptance=False,
                target_status='PENDING_TARGET',hardware_status='PENDING_HARDWARE')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS historical records=70, missing-READ32 rejections=70; no new hardware execution')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sessions',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();run(args.sessions,args.output)
