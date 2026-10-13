#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
out="results_paired_both_review/terminal_screenshots"
mkdir -p "$out"
export DISPLAY=:94
Xvfb "$DISPLAY" -screen 0 1600x900x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT
sleep 2

capture() {
  local name="$1" title="$2" command="$3" delay="$4"
  xterm -geometry 128x34+20+18 -fa 'DejaVu Sans Mono' -fs 13 \
    -bg black -fg white -cr white -T "$title" \
    -e bash --noprofile --rcfile "$PWD/terminal_review2.rc" -i &
  local term_pid=$!
  sleep 1
  local window_id
  window_id=$(xdotool search --onlyvisible --name "$title" | tail -1)
  test -n "$window_id"
  xdotool windowfocus "$window_id"
  xdotool type --window "$window_id" --clearmodifiers --delay 2 "$command"
  xdotool key --window "$window_id" Return
  sleep "$delay"
  scrot "$out/$name.png"
  kill "$term_pid" 2>/dev/null || true
  wait "$term_pid" 2>/dev/null || true
}

capture "dark_01_tests" "Review 2 tests" \
  "python3 -m unittest discover -s tests -q" 3
capture "dark_02_audit" "Review 2 paired benchmark" \
  "python3 -m os_sched.verify_paired" 3
capture "dark_03_tree" "Review 2 live tree" \
  "python3 -m os_sched.live_demo --compact --model results_final_linux/model.json --output /tmp/review2_tree.json --workload prime_scan --prime-base 3000 --seed 12001 --workers 2" 5
capture "dark_04_balanced" "Review 2 live cost balancing" \
  "python3 -m os_sched.live_demo_straggler --seed 12002 --output /tmp/review2_balanced.json" 5
capture "dark_05_both" "Review 2 two live schedulers" \
  "bash show_both_review2.sh" 6
printf 'Captured interactive dark-terminal screenshots in %s\n' "$out"
