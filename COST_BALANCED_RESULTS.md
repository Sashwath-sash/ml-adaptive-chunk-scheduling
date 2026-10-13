# Cost-balanced dispatch: measured result and limits

This is a **different algorithm** from the decision tree. Before starting worker processes, it uses task metadata to estimate CPU cost, divides the queue into variable-size batches with approximately equal estimated cost, and dispatches the longest batches first. There is one process-pool dispatch and no repeated feedback barrier. CPU work still runs in compiled C under Linux; Python controls application-level dispatch. The Linux kernel scheduler is not modified.

## What actually beat the baseline

The primary stress test was recorded in `STRAGGLER_TEST_PLAN.md` before measurement. An audit then found that batch-planning time was excluded from the cost-balanced timer; `TIMING_CORRECTION_PLAN.md` records the correction and fresh rerun plan. The **final** test uses 192 tasks, one 40× CPU task randomly placed among the last eight task slots, two workers, new seeds **10001–10010**, and seven methods in shuffled order. `balanced_32` remained the declared primary comparator against fixed chunk 4. The corrected timer includes planning, process startup, dispatch and teardown.

Across **10 corrected paired runs**, `balanced_32` beat fixed chunk 4 **10/10 times**. Median wall time was **0.446 s** versus **0.509 s** for fixed 4. The median of the **paired runtime ratios** was **0.881**, or about **12% less end-to-end time**. It also beat `Pool.map(..., chunksize=16)` in all 10 pairs, with a median paired ratio of about **0.898**. Every method produced the same checksum. The measured dataset, exact spike locations, raw times, summaries, validation and browser screenshots are in `results_straggler_corrected`.

In the saved live demonstration (a separate seed, not one of the ten), the algorithm moved the expensive task's batch to dispatch position 0, and the three checksums matched. Its single-run timings in `live_demo.json` must not be substituted for the ten-run result.

## Where the claim stops

The corrected algorithm was also tested on five ordinary workloads with fresh seeds **6001–6005** (175 paired timed runs). On those classes, `balanced_32` had a geometric mean workload-level paired ratio of about **0.985** versus fixed 4, but it was slightly slower on high-variance and prime-scan classes. The preselected general-purpose candidate, `balanced_fifo_16`, had a ratio of **0.985**—small enough that host noise may matter. Do **not** claim a universal 12% speedup. The strong evidence is for the explicitly defined rare-tail-straggler workload. The earlier result folders are retained but superseded by the corrected-timing folders.

Adaptive chunk scheduling, cost-based batching and longest-processing-time-first ideas are not claimed as first-ever inventions. The project contribution is their measured implementation and comparison in this Linux multiprocessing/C workload setup, alongside the original decision-tree ablation. Production generalization would require real traces, more worker counts and machines, and an evaluation of cost-estimate errors.

## How to show it

Open `results_straggler_corrected/dashboard.html`. Then show `raw.csv`, `summary.csv`, `dataset.csv`, `validation.json`, `tests.txt`, and `live_demo.json`. The implementation is `os_sched/scheduler_v4.py` and the workload definition is `os_sched/straggler_workload.py`.

In Ubuntu/WSL2, from the project directory:

```bash
bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.live_demo_straggler --seed 11001 --output results_straggler_corrected/live_demo_again.json
python3 -m os_sched.verify_straggler results_straggler_corrected
```

To rerun the ten paired stress tests (timings will vary with host load):

```bash
python3 -m os_sched.experiment_straggler --output results_straggler_repeat --seed-start 10001 --repeats 10 --workers 2 --count 192 --base 1500000 --spike-factor 40
```
