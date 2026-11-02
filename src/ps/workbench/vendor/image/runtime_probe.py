"""Relocated runtime import/codec closure probe. No FPGA/PYNQ/native library IO."""
import hashlib
import json
from pathlib import Path
import sys


def probe():
    root=Path(__file__).resolve().parent
    sys.path.insert(0,str(root/'runtime/host'))
    sys.modules['pynq']=None  # accidental PYNQ import must fail in this probe
    from ps_candidate_session import CandidateSession,BANKS
    from ch1_uartlite_realtime_transport import RealtimeUARTLiteControlTransport
    from controlled_trial_executor import ControlledTrialExecutor
    from local_rule_trial_loop import LocalRuleTrialLoop
    from ch1_completion_ledger import _codec
    import ch1_evidence_store as store
    for cls in (CandidateSession,RealtimeUARTLiteControlTransport,ControlledTrialExecutor,LocalRuleTrialLoop):
        if Path(sys.modules[cls.__module__].__file__).resolve().parent!=root/'runtime/host':
            raise ValueError('RUNTIME_MODULE_PATH')
    source=bytes(range(256));codec=_codec()
    item=codec.encode_item(1,1,1,0,1,0,0,source)
    decoded=codec.decode_item(item)
    if not decoded['valid'] or decoded['payload']!=source:raise ValueError('RELOCATED_ITEM_CODEC')
    config=codec.encode_config(1,1,32,8,256,1,256,hashlib.sha256(source).digest(),[store.crc16(source)])
    if not codec.decode_config(config)['valid']:raise ValueError('RELOCATED_CONFIG_CODEC')
    return dict(status='PASS_RELOCATED_RUNTIME_IMPORT_AND_CODEC',banks=len(BANKS),
                ITEM_bytes=len(item),CONFIG_bytes=len(config),hardware_access=False,
                native_library_loaded=False,physical_STARTs=0)


if __name__=='__main__':
    value=probe();out=Path(sys.argv[1]).resolve();root=Path(__file__).resolve().parent
    if root==out or root in out.parents:raise ValueError('OUTPUT_OUTSIDE_KIT_REQUIRED')
    with out.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(value,indent=2))
