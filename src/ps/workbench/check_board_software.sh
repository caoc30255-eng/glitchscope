#!/usr/bin/env bash
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python=/usr/local/share/pynq-venv/bin/python3
work_dir=$(mktemp -d "../unified_ui_check_XXXXXXXX")
echo "仅软件检查，不加载Overlay、不访问FPGA、不新增START。"
"$python" -B software_check.py --output "$work_dir/report" > "$work_dir/console.log" 2>&1 &
check_pid=$!
while kill -0 "$check_pid" 2>/dev/null; do
  echo "检查运行中，日志：$work_dir/console.log"
  sleep 15
done
status=0
wait "$check_pid" || status=$?
cat "$work_dir/console.log"
echo "完整报告：$work_dir/report/report.json"
exit "$status"
