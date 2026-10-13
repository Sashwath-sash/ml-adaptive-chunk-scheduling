#!/usr/bin/env bash
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
dst=$(mktemp -d /tmp/os-sched-final.XXXXXX)
cp -r "$src/native" "$src/os_sched" "$src/tests" "$src/build.sh" "$dst/"
cd "$dst"
bash build.sh
python3 -m os_sched.experiment_complete --output results_final_linux --workers 2 --base 1500000 --prime-base 3000 --count 192 --repeats 5 --train-seeds 6 --holdout-seeds 4 --candidate-repeats 2
python3 -m os_sched.compare_existing --results results_final_linux --workers 2 --base 1500000 --prime-base 3000 --count 192 --repeats 5
python3 -m os_sched.verify_results results_final_linux
python3 -m os_sched.capture_tests --output results_final_linux/tests.txt
python3 -m os_sched.live_demo --model results_final_linux/model.json --output results_final_linux/live_demo.json --workload phase_shift --workers 2
mkdir -p "$src/results_final_linux"
cp -r results_final_linux/. "$src/results_final_linux/"
echo "FINAL_LINUX_PATH=$dst"
