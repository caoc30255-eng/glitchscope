"""Bind isolated driver imports; no FPGA/Overlay/native library access."""
import sys
from pathlib import Path

def bind():
    root=Path(__file__).resolve().parent;host=root/'runtime/host'
    for n in ('ps_candidate_session','controlled_trial_executor','raw_mark_snapshot','ch1_evidence_store'):
        m=sys.modules.get(n)
        if m is not None and Path(m.__file__).resolve().parent!=host:
            raise RuntimeError('NEW_KERNEL_REQUIRED_OLD_MODULE: '+n)
    if str(host) not in sys.path:sys.path.insert(0,str(host))
    return root
