#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
out="results_paired_both_review/terminal_screenshots"
mkdir -p "$out"
export DISPLAY=:93
Xvfb "$DISPLAY" -screen 0 1600x900x24 -nolisten tcp > /dev/null 2>&1 &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT
sleep 2

capture() {
  local name="$1" title="$2" command="$3"
  local marker="/tmp/review2_terminal_${name}_ready"
  rm -f "$marker"
  xterm -geometry 130x36+25+20 -fa 'DejaVu Sans Mono' -fs 12 \
    -bg white -fg black -cr black -T "$title" \
    -e bash -lc "cd '$PWD'; export TERM=xterm-mono; $command; touch '$marker'; sleep 15" &
  local term_pid=$!
  for _ in $(seq 1 120); do
    if test -f "$marker"; then break; fi
    sleep 1
  done
  test -f "$marker"
  sleep 1
  scrot "$out/$name.png"
  kill "$term_pid" 2>/dev/null || true
  wait "$term_pid" 2>/dev/null || true
  rm -f "$marker"
}

capture "01_tests" "Review 2 - Linux unit tests" \
  "printf 'Review 2 / Ubuntu WSL2 / unit tests\\n'; python3 -m unittest discover -s tests -q"
capture "02_benchmark_audit" "Review 2 - paired benchmark audit" \
  "printf 'Review 2 / saved paired benchmark / validation\\n'; python3 -m os_sched.verify_paired"
capture "03_live_tree" "Review 2 - live decision tree" \
  "python3 -m os_sched.live_demo --compact --model results_final_linux/model.json --output results_paired_both_review/terminal_tree_demo.json --workload prime_scan --prime-base 3000 --seed 12001 --workers 2"
capture "04_live_balanced" "Review 2 - live cost-balanced scheduler" \
  "python3 -m os_sched.live_demo_straggler --seed 12002 --output results_paired_both_review/terminal_balanced_demo.json"
printf 'Captured actual xterm screen images in %s\n' "$out"
