#!/usr/bin/env bash
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
exec "${PYTHON:-python3}" -B "$root/board/start_preview.py"
