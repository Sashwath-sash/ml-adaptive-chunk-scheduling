# Live measured-metrics scheduler: demonstration and evidence

This is an **application-level** CPU-task dispatcher on Linux/WSL2. Python starts worker processes, measures batches, loads a trained CART decision tree, and chooses how to package the remaining tasks. Every task's CPU kernel is compiled C11. It does **not** modify the Linux kernel process scheduler. The Python control path is part of measured end-to-end latency.

## Show it in the terminal

From Ubuntu/WSL2, enter this project directory, then run:

```bash
bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.verify_live_v6
python3 -m os_sched.live_demo_v6 --kind late_heavy
```

Open `results_live_v6/dashboard.html` in a browser. Open `results_live_v6/model.json` and `results_live_v6/test_raw.csv` if asked for the actual trained splits and raw timings. `live_demo_v6.json` records the new run. Run `python3 -m os_sched.dashboard_v6` to regenerate the page from saved measurements. A new run's exact timings will vary with host load; do not quote the single demo run as a speedup estimate.

For a full fresh experiment, the order is `python3 -m os_sched.experiment_v6 train`, then `tune`, then `test`. **Do not overwrite the saved evidence before presenting.** Those steps take many minutes and the test command will rewrite the test CSVs. The default model is trained for 192 tasks and two workers. Functional checks with other counts/worker counts are not claims of model generalization.

## What is actually implemented

1. Generate deterministic uniform, moderate, high-variance, phase-shifted, prime-counting, and late-heavy task lists. The late-heavy class puts rare expensive tasks near the end.
2. Execute the first 32 tasks in chunk-4 batches on two workers. The C work is real. Measure pilot batch service times, effective task throughput, queue-wait proxy, and batch response latency. Also compute cost-distribution descriptors from **known metadata of not-yet-run tasks**; these are estimates, not measured future runtimes.
3. Load the trained CART model and choose one of four remainder policies: fixed chunk 4 or cost-balanced batches targeting 16, 32, or 64 tasks. Cost balancing packs batches using the task cost estimate, then dispatches heavier batches first. The implementation files are `os_sched/scheduler_v6.py`, `os_sched/scheduler_v4.py`, and `os_sched/tree.py`.
4. Check the sum of all C result checksums against other methods on identical task lists. Measure complete invocation wall time, including pool startup/teardown, pilot, feature computation, decision, and dispatch. Batch p95 and queue-wait proxy are separate secondary measurements.

The term `pilot_mean_task_s` is total measured *batch* service time divided by pilot task count; `pilot_service_cv` and `pilot_service_p95_s` describe **batch** service times, not individually instrumented task times. `queue_wait_p95_s` is worker batch start minus parent submission; it can include serialization/dispatch time. `batch_latency_p95_s` is worker batch finish minus parent submission, including queue delay. The pilot is a blocking barrier; all pilot batches finish before selecting the remainder policy.

## Training and honest comparison

Training used 48 workload/seed/scale groups and 384 complete candidate invocations (four policies, two repetitions). The label was the policy with the lowest median **whole-invocation** time, with a 3% improvement margin before moving away from pilot-fixed-4. Validation used 18 separate groups (144 candidate invocations) at a different scale to select tree depth and minimum leaf size. Final testing used 60 further groups at another scale and 480 complete runs across eight methods. Seeds 6001–6004, 7001–7003, and 8001–8010 were used in the three splits, respectively. Candidate order was shuffled within each matched group. The final test was not used for model selection. The audit recomputes labels and paired ratios from raw CSVs and checks every within-group checksum.

The table shows **median paired whole-run time / fixed-4 whole-run time** on ten unseen seeds per workload. Below 1 is faster; 1.00 is parity. These are exploratory single-host results, not general performance guarantees.

| Workload | Mixed CART with pilot | Measured-pilot-only CART | Cost-balanced 32 without pilot |
| --- | ---: | ---: | ---: |
| Uniform | 1.017 | 1.017 | 0.997 |
| Moderate | 1.003 | 1.010 | 1.006 |
| High variance | 1.002 | 1.016 | 0.992 |
| Phase shift | 1.008 | 1.021 | 1.003 |
| Prime scan | 0.967 | 0.987 | 0.963 |
| Late heavy | 0.874 | 0.995 | 0.846 |

The mixed CART is a real trained tree, but its selected splits are only `remaining_cost_cv` and `prime_fraction`. It **receives** six real pilot features, yet training/validation did not find them useful enough to use. To test that directly, the measured-pilot-only CART was restricted to those six runtime features. Its saved tree splits on measured `pilot_service_p95_s`, but **both leaves choose fixed 4**, so the split has no useful scheduling effect. The pilot cannot see expensive tasks placed later in the queue. This is a negative ML finding, not a success to hide.

Cost-balanced 32, which uses task metadata and no pilot, is the strongest tested method on the late-heavy workload. It is not ML and the cost estimate assumes task metadata is available and informative. On a workload whose costs are hidden until execution, that method may not transfer. Conversely, the live tree pays for a pilot/barrier that these experiments did not justify against that simpler baseline. The reported late-heavy mixed-tree improvement is **against fixed 4**, not against cost-balanced 32.

## Prior art and novelty boundary

[LB4OMP](https://github.com/unibas-dmi-hpc/LB4OMP) already implements many dynamic/adaptive OpenMP loop schedulers and reinforcement-learning-based algorithm selection. Learning-based scheduling, dynamic chunking, and cost-aware balancing are **not new ideas**. [AdaptDL](https://github.com/petuum/adaptdl) adapts resource and batch-size decisions for distributed ML training, a different granularity. Our narrower project contribution is a reproducible comparison of a measured-pilot CART selector, a runtime-feature ablation, and a no-pilot cost-balanced policy for compiled-C tasks dispatched through a Linux process pool, with complete-run overhead and failure cases exposed. It is an experimental implementation, not a claim of first-ever novelty or superiority to LB4OMP.

## What to say when questioned

- **“Is this really running on the OS?”** Yes: Ubuntu/WSL2 processes run compiled C work; Python controls the application-level batches. No kernel modification was made.
- **“Is the tree hard-coded?”** No. `train_raw.csv` contains timed candidate runs; `train_labels.csv` contains labels from those complete runs; `model.json` stores learned thresholds and leaf choices. The tree training code is in `os_sched/tree.py`.
- **“Does it use actual runtime features?”** It measures and passes them to the mixed tree. But the *learned splits* did not select them. The runtime-only ablation showed why the current pilot is insufficient for unseen late-tail cost.
- **“Does ML beat the baseline?”** On late-heavy data it beats fixed 4 by about 12.6% median paired whole-run time, but loses to cost-balanced 32 without a pilot (about 15.4% faster than fixed 4). On several other workloads the ML pilot costs more than it saves.
- **“What is still missing?”** Validation beyond one WSL2 host, more worker counts and task sizes, representative external traces, a better mechanism for hidden future costs, and a model/policy whose advantage survives a stronger no-pilot baseline. This is not ready for a claim of universal speedup.

The older Review 2 PDF describes an earlier implementation and should not be presented as if it contains these v6 findings.
