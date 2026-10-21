#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo 'Building the real C kernel...'
bash build.sh
echo 'Running all functional tests...'
python3 -m unittest discover -s tests -v
echo 'Auditing saved training, validation and held-out timings...'
python3 -m os_sched.verify_learned_v7 --output results_learned_v7_final
echo 'Executing a fresh comparison...'
python3 -m os_sched.live_demo_v7 --kind phase_shift
echo
echo "Open $(pwd)/results_learned_v7_final/dashboard.html in a browser."
echo 'One live run demonstrates execution, not a reliable speedup estimate.'
