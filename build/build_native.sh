#!/usr/bin/env bash
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out=${1:?Supply an external output directory}
mkdir -p "$out"
test ! -e "$out/libuartlite_service_v5_rt.so"
gcc -O2 -std=c11 -Wall -Wextra -Werror -fPIC -shared -pthread -Wl,-Bsymbolic "$root/src/ps/native/uartlite_service_v5.c" -o "$out/libuartlite_service_v5_rt.so"
sha256sum "$out/libuartlite_service_v5_rt.so"
echo "Build only. No UART thread, MMIO, reset or START."
