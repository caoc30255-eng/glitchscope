"""Start local PREVIEW UI only; no live config, device import or permission grant."""
import subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
data=Path(tempfile.mkdtemp(prefix='glitchscope_preview_'))
print('PREVIEW only: http://127.0.0.1:8780/ ; data:',data,flush=True)
raise SystemExit(subprocess.call([sys.executable,'-B',str(root/'src/ps/workbench/server.py'),'--port','8780','--data',str(data)]))
