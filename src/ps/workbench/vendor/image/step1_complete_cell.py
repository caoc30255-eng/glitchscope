from pathlib import Path
import sys, json, hashlib, importlib.util

if "board_session" in globals() or "ps_candidate_session" in sys.modules:
    raise RuntimeError("请使用全新内核，不复用旧会话")
root = Path("/home/xilinx/jupyter_notebooks/test_10_14")
candidate = root / "PYNQ_Image_Web_v0_2_1_2026-10-19"
host = candidate / "runtime" / "host"
rt_host = root / "PS_UART_RT_v5_2026-10-15" / "host"
native_library = rt_host / "libuartlite_service_v5_rt.so"
manifest = json.loads((candidate / "sha256.json").read_text(encoding="utf-8"))
for relative, expected in manifest.items():
    raw = (candidate / relative).read_bytes()
    assert len(raw) == expected["bytes"], relative
    assert hashlib.sha256(raw).hexdigest() == expected["sha256"], relative
print("候选文件校验通过:", len(manifest))
# Validate saved code before any Overlay/MMIO/UART/session allocation.
sys.path.insert(0,str(candidate))
import package_tools
assert Path(package_tools.__file__).resolve().parent==candidate.resolve()
print("Notebook代码检查:",json.dumps(package_tools.verify()["notebook"],ensure_ascii=False))
assert native_library.is_file(), "找不到 RT v5 接收库"
name = "h1_7020_evidence_candidate_v0_1"
for ext, digest in {
    ".bit": "0c0b686e80e37e49e64ab07b719a0c1ea3387451f3ceebdba5dcf38b8c68b61c",
    ".hwh": "8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc",
}.items():
    assert hashlib.sha256((root / (name + ext)).read_bytes()).hexdigest() == digest
for path in (str(rt_host), str(host), str(candidate)):
    if path in sys.path: sys.path.remove(path)
    sys.path.insert(0, path)
from pynq import Overlay, MMIO, Clocks
from ps_candidate_session import CandidateSession, BANKS
from ch1_uartlite_realtime_transport import RealtimeUARTLiteControlTransport
from ch1_admission_parts import _has_exact_rx
from controlled_trial_executor import ControlledTrialExecutor, TrialRequest
from local_rule_trial_loop import LocalRuleTrialLoop
from multipoint_capability_preflight import inspect_multipoint_capability
from fault_profile import FaultProfile
from fault_pilot_workflow import inspect_raw_mark_interface
for module_name in ("ps_candidate_session", "local_rule_trial_loop", "raw_mark_snapshot", "ch1_control_session"):
    assert Path(sys.modules[module_name].__file__).resolve().parent == host.resolve()
assert "uart_byte_exchange_saved" in _has_exact_rx.__code__.co_consts
spec = importlib.util.spec_from_file_location("unknown_candidate_probe", candidate / "read_only_probe.py")
probe_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_module)
# Hold the same exclusive lock across Overlay reload and session creation.
import fcntl
runs = root / "board_runs"
assert runs.is_dir(), "保留原有 board_runs，不创建替代目录"
assert "board_lock" not in globals(), "不要重复运行初始化单元格"
board_lock = (runs / "exclusive.lock").open("a+")
try:
    fcntl.flock(board_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BaseException:
    board_lock.close()
    raise
overlay = Overlay(str(root / (name + ".bit")))
Clocks.fclk0_mhz = 150
print("FCLK0 配置读回 MHz:", Clocks.fclk0_mhz)
fresh = probe_module.probe(MMIO, root / (name + ".hwh"))
print(json.dumps(fresh, indent=2, ensure_ascii=False))
expected_status = dict(H1=1, CTRL=0, MAIN=0, AUX=0, MAP=0, CH0=8, PROFILE=4, SYS=0)
assert fresh["all_IDs_match"]
assert all(int(b["status"], 16) == expected_status[b["bank"]] for b in fresh["banks"])
assert fresh["local_epoch"] == fresh["retire_count"] == fresh["grant_count"] == 0
print("上传图片整图候选已加载；原Overlay配置后检查通过，尚未创建会话、未执行试验。")
