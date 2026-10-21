# Current project demonstration: learned no-pilot dispatch

This is a runnable Linux/WSL2 **application-level scheduler** for independent CPU jobs, not a patch to the Linux kernel scheduler. The worker processes call compiled C11 functions for deterministic CPU work and prime counting. Python reads the workload description, uses a saved supervised model to select a dispatch policy, sends task batches to the processes, and collects results. The time spent in Python, including feature calculation and prediction, is counted in the end-to-end timer.

## Run it in front of the reviewer

From the Ubuntu terminal in this project directory:

```bash
bash show_latest_review.sh
```

That runs the following steps (you can also run them one at a time):

```bash
bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.verify_learned_v7 --output results_learned_v7_final
python3 -m os_sched.live_demo_v7 --kind phase_shift
```

Then open `results_learned_v7_final/dashboard.html`, `model.json`, and `test_raw.csv`. These are files on disk, not pictures of fake terminal output. A fresh demo may give different timings under different host load; the saved paired benchmark is the performance evidence. The live demo uses a seed outside the training, validation, and held-out test sets. Avoid rerunning `experiment_v7 train`, `tune`, or `test` in the review: the complete experimental runs take minutes and the train/tune commands can replace their saved artifacts. The confirmation command refuses to overwrite its saved run.

## The actual pipeline

`Task list with work count, input seed, and kernel` → `15 pre-dispatch metadata features` → `saved CART classifier` → `LPT-2 or LPT-4 batching` → `two Linux worker processes executing compiled C` → `checksum and latency audit`.

LPT means *longest estimated processing time first*. It sorts tasks by estimated cost and greedily assigns each to the least-loaded batch, then sends those batches to workers. It is a known heuristic, not a novel ML algorithm. The learned part is a classifier that chooses the batch policy from measured-data training; inference needs no blocking runtime pilot. The model stored in `results_learned_v7_final/model.json` chose a one-split rule: use LPT-2 when `p90_to_mean ≤ 2.6845`, otherwise LPT-4. `p90_to_mean` is the 90th-percentile estimated task cost divided by the mean estimated task cost. No workload label or hidden future execution time is passed to the model at inference.

## Where the training data came from

Every candidate label was computed from **repeated, complete program runs**, not assigned manually. For each task list, fixed-16, cost-balanced-32, LPT-2, LPT-4, and LPT-8 ran twice in shuffled order. The lowest median runtime became the label only if it beat cost-32 by at least 2%; otherwise the label remained cost-32. Training: 48 distinct workload/seed/scale groups and 480 candidate invocations. Validation: 18 new groups and 180 candidate invocations; it selected tree depth and minimum leaf size from 25 settings. Final testing: 60 untouched groups and 600 full invocations, including the trained policy, fixed-4, plain LPT, cost-32, sequential, `Pool.map`, and `ProcessPoolExecutor.map`. Training, validation, and test seeds and task scales do not overlap. Every method's output checksum matched within its task group; the independent verifier recomputes labels, features, model decisions and paired ratios from the saved CSVs.

The six workload classes are uniform, moderate-variance, high-variance, phase-shifted, prime-scan, and late-heavy. Prime-scan calls a genuine C prime-counting kernel over number ranges; the other classes use a deterministic C CPU kernel. These are generated workloads, **not external production traces**. The late-heavy class deliberately places one expensive task near the input tail.

The **primary metric** is complete wall-clock time: from before feature calculation and batching until after the worker pool exits. Throughput is 192 tasks divided by that time. A paired ratio divides one method's time by the baseline's time for the *same seed and task list*, then takes the median across seeds. `batch_latency_p95_s` is the 95th percentile of batch completion times measured from the parent's dispatch start; it includes queueing and C execution and is **not** an individual-task tail-latency measurement. `cpu_utilization_fraction` is parent-plus-child CPU seconds divided by elapsed seconds × two workers, an approximate capacity-normalized CPU-use measure. `planning_s`, `inference_s`, startup time, and batch count are saved where the method exposes them. The standard Python API baselines have different internal instrumentation, so their secondary timing fields may be blank; their complete wall time and checksums are comparable.

## Held-out end-to-end result

The figures are median ratios of complete runtime to cost-balanced-32 on **ten matched unseen seeds per workload**. Below 1 means faster. Read the intervals and all other methods in `test_summary.csv` and `test_raw.csv`.

| Workload | Learned / cost-32 | Wins / 10 | Plain LPT-2 / cost-32 |
| --- | ---: | ---: | ---: |
| Uniform | 0.994 | 7 | 1.001 |
| Moderate | 0.984 | 7 | 0.978 |
| High variance | 0.979 | 8 | 0.981 |
| Phase shift | 0.941 | 8 | 0.975 |
| Prime scan | 1.020 | 4 | 0.948 |
| Late heavy | 0.985 | 8 | 0.977 |

The learned selector beat cost-32 by median runtime on five of six classes. It did **not** consistently beat plain LPT-2, and it lost to cost-32 on prime scan. On some classes the selected policy *is* LPT-2, so any small timing difference between learned and plain LPT-2 there is mainly measurement noise plus inference overhead, **not a new scheduling advantage**. This distinction is important in a serious review. The best-supported claim is a measured, end-to-end improvement over the prior cost-32 method on several constructed workloads—not a universal ML victory.

The model was then **frozen** for a second run at a larger task scale not seen during training. This confirmation used 20 further seeds per workload: 120 matched groups and 480 full runs. The independent audit checks it separately. Ratios are again complete-run paired medians; the bootstrap intervals resample the 20 matched seed ratios.

| Workload | Learned / cost-32 | 95% bootstrap interval | Learned / plain LPT-2 |
| --- | ---: | ---: | ---: |
| Uniform | 1.005 | 0.980–1.021 | 1.010 |
| Moderate | 0.972 | 0.952–0.983 | 0.991 |
| High variance | 0.973 | 0.964–0.988 | 0.997 |
| Phase shift | 0.982 | 0.968–0.994 | 0.992 |
| Prime scan | 0.993 | 0.942–1.019 | 1.039 |
| Late heavy | 0.990 | 0.983–1.002 | 0.998 |

Thus the larger-scale evidence supports an advantage over **cost-32** for moderate, high-variance, and phase-shifted inputs on this host. It still does **not** support a general advantage over **plain LPT-2**; the intervals for learned/LPT-2 include 1, and prime-scan is notably noisy. This is why the dashboard shows both baselines rather than a single favorable number.

The project also trained a separate kernel-specific ridge regression model on **9,216 individually timed compiled-C tasks**, with 3,456 different validation tasks. Its purpose was to replace the hand-written per-task cost estimate. It did not improve validation cost accuracy enough, and a scheduling screen was worse on prime-scan work. Therefore that model is retained as a documented ablation in `results_cost_model_v8`, **not deployed as a superior scheduler**. It demonstrates that adding a second ML model is not automatically useful.
Its raw task timings, saved coefficients and errors can be checked with `python3 -m os_sched.verify_cost_model_v8`.

## Reviewer questions and accurate answers

- **“Where is the ML?”** `os_sched/tree.py` fits CART splits from measured complete-run labels; `os_sched/experiment_v7.py` performs data collection, tuning, and frozen-model inference. `results_learned_v7_final/model.json` has the learned threshold and leaf policies. The separate measured-task ridge model is in `os_sched/cost_model_v8.py`.
- **“Does it really run under Linux?”** Yes. Run `bash build.sh`; the binary is `build/libwork_kernel.so`. Linux processes execute those C functions, while Python decides application-level batching. It does not alter kernel CPU scheduling.
- **“How is it faster?”** Avoiding the old blocking pilot reduces decision overhead. LPT distributes expensive known tasks across batches. The saved matched timings include all that overhead, but show workload-dependent, not universal, gains.
- **“Did you compare existing options?”** Yes: fixed chunks, sequential, cost-balanced-32, plain LPT-2/4/8, `multiprocessing.Pool.map` and `ProcessPoolExecutor.map` are timed on the same input lists. The Python built-ins use different dispatch internals, so this is a practical end-to-end comparison, not an equal-internals microbenchmark. OpenMP/LB4OMP is relevant prior art but not a directly measured baseline here.
- **“What is novel?”** Not adaptive scheduling, LPT, or learning-based selection in general. [LB4OMP](https://github.com/unibas-dmi-hpc/LB4OMP) already includes adaptive and RL-based schedulers. This project's defensible contribution is an overhead-aware, no-pilot, measured-data policy selector in this process-pool setting, plus transparent comparisons including negative ML ablations. Do not claim world-first novelty or guaranteed speedup.
- **“What remains?”** More CPU counts and machines, external application traces, longer/noise-controlled repeats, and a learned mechanism that reliably beats the strongest simple LPT baseline—not merely cost-32. WSL2 currently exposes two logical CPUs to this Ubuntu environment.

Source entry points: `os_sched/scheduler_v7.py` (LPT and fixed planners), `os_sched/experiment_v7.py` (features, supervised training and full benchmarks), `os_sched/live_demo_v7.py` (fresh run), and `os_sched/verify_learned_v7.py` (audit). The older Review 2 PDF predates these experiments and should not be presented as the latest performance report.
