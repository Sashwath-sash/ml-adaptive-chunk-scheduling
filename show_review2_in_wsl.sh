#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.live_demo \
  --model results_final_linux/model.json \
  --output results_paired_both_review/live_tree_demo.json \
  --workload prime_scan --prime-base 3000 --seed 12001 --workers 2
python3 -m os_sched.live_demo_straggler \
  --seed 12002 \
  --output results_paired_both_review/live_cost_demo.json

sed -n '1p;/^prime_scan,/p;/^late_heavy,/p' results_paired_both_review/summary.csv
echo 'Demo complete. This WSL terminal will stay open for review.'
exec bash
