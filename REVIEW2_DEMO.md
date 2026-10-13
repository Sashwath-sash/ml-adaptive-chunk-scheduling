# Review 2 live demonstration and speaking guide

Use the corrected folders only: `results_straggler_corrected` for the targeted result and `results_balanced_corrected` for the five ordinary workloads. Earlier `results_straggler_test`, `results_balanced_test` and `results_balanced_dev` are retained for audit but their timings are superseded.

## Open in this order

1. Open `results_straggler_corrected/dashboard.html` locally in a browser. Explain that the primary graph compares full wall time on the same 192 tasks, not tree inference time alone.
2. Open `results_straggler_corrected/summary.csv`. Point to fixed chunk 4 median 0.509 s and cost-balanced 32 median 0.446 s. The median of paired ratios is 0.881 (about 12% less time) across ten seeds, with 10/10 paired wins.
3. Open `results_straggler_corrected/validation.json` and `tests.txt`. Show `status: PASS`, 70 timed rows, 1,920 input rows, equal checksums and 12 passing tests.
4. Open `results_straggler_corrected/dataset.csv` to show the exact generated task inputs and late spike positions. These are synthetic CPU tasks, not real application traces.
5. Open `results_balanced_corrected/summary.csv` to show that the same method does not always win on ordinary workloads. On high variance and prime scan its paired ratio is slightly above 1.
6. Open `results_final_linux/model.json` and `results_final_linux/manifest.json` to show the trained depth-3 decision tree and disjoint train/holdout/final seeds. The original repeated-decision ML scheduler was slower than fixed chunk 4 in the five original classes. That result motivated the alternative method.

## Commands in Ubuntu or WSL2

Run these from the project directory. The first four commands are short and verify the saved evidence; they do not rerun the full benchmark.

```bash
bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.verify_straggler results_straggler_corrected
python3 -m os_sched.verify_balanced results_balanced_corrected
python3 -m os_sched.live_demo_straggler --seed 11001 --output demo_new.json
```

In the demo output, point to the expensive task's batch moving to dispatch position 0 and to matching checksums. Do not quote its one-run wall time as the ten-run result; host load can change that timing.

To reproduce the corrected ten-pair stress experiment, which takes longer:

```bash
python3 -m os_sched.experiment_straggler --output results_straggler_repeat --seed-start 10001 --repeats 10 --workers 2 --count 192 --base 1500000 --spike-factor 40
python3 -m os_sched.verify_straggler results_straggler_repeat
```

## What to say in roughly two minutes

“My project studies application-level chunk scheduling for independent CPU tasks. I run a Python process pool on Linux; the heavy computation is compiled C. A fixed chunk size groups the same number of tasks even when their costs differ. I first trained a depth-3 decision tree to choose chunks from measured features. Its held-out label accuracy was 73.3%, but the repeated round barriers made end-to-end execution slower than fixed chunk 4 on the general workloads. So I implemented a second scheduling path: estimate task costs from known metadata, make approximately cost-balanced batches and submit expensive batches first. The final timing includes that planning work and process startup and teardown. On a defined rare late-straggler workload, it beat fixed chunk 4 in all ten paired runs: 0.446 seconds median versus 0.509, with a median paired ratio of 0.881. It is not universally faster: the five ordinary workload classes show small mixed results. The Linux kernel itself is unchanged.”

## Likely questions

**Where is the machine learning?** `os_sched/tree.py` trains the tree; `results_final_linux/model.json` stores it; `scheduler_v2.py` applies it online. The better targeted result comes from `scheduler_v4.py`, a non-ML alternative. Do not call that result an ML speedup.

**What is new?** The project-specific contribution is the working, measured comparison of those two schedulers on the same process-pool/C workload, with corrected end-to-end timing and paired baselines. Adaptive scheduling and longest-first batching are established ideas; first-ever novelty is not proven.

**Is this an OS scheduler?** It is a user-space scheduler of task batches to Linux processes. The OS schedules those worker processes on CPUs. No kernel patch was made.

**Why does cost balancing help?** When a very expensive task is at the tail, fixed FIFO chunks may start it late. The planner moves its batch forward so its C work overlaps the other batches.

**What remains?** Test inaccurate cost metadata, more worker counts and a second machine, and evaluate real traces. These are necessary before generalizing the measured speedup.
