#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
gcc -O2 -std=c11 -Wall -Wextra -Werror -fPIC -shared native/work_kernel.c -o build/libwork_kernel.so
echo "Built build/libwork_kernel.so"
