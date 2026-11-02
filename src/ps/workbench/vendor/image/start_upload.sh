#!/usr/bin/env bash
set -euo pipefail
kit=$(cd -- "$(dirname -- "$0")" && pwd)
workspace=${1:?请传入原网页工作区，例如 /home/xilinx/jupyter_notebooks/test_10_14/web_preflight_v4IoWNYE/ui}
python=/usr/local/share/pynq-venv/bin/python3
stamp=$(date +%s)
"$python" -B "$kit/package_tools.py" "$workspace/image_upload_preflight_$stamp.json"
"$python" -B "$kit/runtime_probe.py" "$workspace/image_upload_runtime_$stamp.json"
"$python" -B -m unittest discover -s "$kit/tests" -v 2>&1 | tee "$workspace/image_upload_tests_$stamp.txt"
echo '上传预览服务启动；本命令不连接 FPGA，不发送 CONFIG/ITEM 或 START。'
"$python" -B "$kit/web_service.py" --workspace "$workspace" \
  --assets-root /home/xilinx/jupyter_notebooks/test_10_14/web_image_assets --port 8765
