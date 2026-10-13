# Low-barrier scheduler improvement

The original tree scheduler waited for many small rounds to finish before choosing another chunk. The improved `ml_once` method keeps the **same saved trained decision tree** but makes only one online decision: execute 16 pilot tasks at chunk 4, measure their completed service times and throughput, predict a chunk, then dispatch the remaining 176 tasks in one bulk stage. Worker processes remain alive across both stages. No Linux kernel scheduler is changed.

## Fresh paired Linux test

The new benchmark tested seven methods on five workload classes × five held-out seeds: **175 timed runs**. Methods and workload/seed groups were shuffled. All paired checksums matched. Eight automated tests passed. `results_improvement/validation.json` recomputes medians, checks the decision counts and records code/data hashes. The timing includes process startup, dispatch, tree inference and teardown.

| Workload | Fixed 4 median | Old tree median | One-decision tree median | Paired one-decision/old-tree ratio |
|---|---:|---:|---:|---:|
| Uniform | 0.396 s | 0.410 s | 0.408 s | 0.966 |
| Moderate variance | 0.409 s | 0.441 s | 0.412 s | 0.994 |
| High variance | 0.402 s | 0.469 s | 0.404 s | 0.838 |
| Phase shift | 0.384 s | 0.435 s | 0.401 s | 0.921 |
| Prime scan | 0.204 s | 0.232 s | 0.220 s | 0.949 |

The one-decision version beat the old tree in paired median ratio in all five classes, most clearly on high variance. The moderate-variance difference is tiny and could be timing noise. It **does not consistently beat fixed chunking or the built-in Python process-pool options**; do not claim an optimal or generally faster scheduler. A single live demonstration can look better or worse than the five-run medians.

## Show it

Open `results_improvement/dashboard.html`, then `summary.csv`, `raw.csv`, `decisions.csv`, `validation.json`, `tests.txt` and `live_demo.json`. The source is `os_sched/scheduler_v3.py`. On Ubuntu/WSL2, from this directory:

```bash
bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.live_demo_improvement --model results_final_linux/model.json --output results_improvement/live_demo_again.json --workload high --workers 2
python3 -m os_sched.verify_improvement results_improvement
```

The live run prints the actual chunk change after the pilot and checks that fixed, old-tree and improved-tree outputs agree. To reproduce the timed comparison, run:

```bash
python3 -m os_sched.experiment_improvement --model results_final_linux/model.json --output results_improvement_repeat --workers 2 --base 1500000 --prime-base 3000 --count 192 --repeats 5
```

Next performance work would isolate barrier cost, test larger jobs and worker counts, and use real workload traces. Those are proposals, not completed findings.
