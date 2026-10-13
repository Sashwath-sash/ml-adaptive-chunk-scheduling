#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo 'Tree scheduler (first decisions and final check):'
python3 -m os_sched.live_demo --compact --model results_final_linux/model.json \
  --output /tmp/review2_tree.json --workload prime_scan --prime-base 3000 \
  --seed 12001 --workers 2 | grep -E '^(LIVE|round=01|END)'
echo 'Cost-balanced scheduler (late-heavy run):'
python3 -m os_sched.live_demo_straggler --seed 12002 \
  --output /tmp/review2_balanced.json
