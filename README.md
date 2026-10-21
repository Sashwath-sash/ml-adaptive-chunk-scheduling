# Machine-Learning-Assisted Adaptive Chunk Scheduling

**Current working system (v6):** [LIVE_V6_DEMO.md](LIVE_V6_DEMO.md) is the entry point for a live Linux demonstration. The [v6 dashboard](results_live_v6/dashboard.html), [saved mixed CART model](results_live_v6/model.json), [measured-only CART ablation](results_live_v6/model_runtime_only.json), [480 held-out timed runs](results_live_v6/test_raw.csv), and [audit](os_sched/verify_live_v6.py) are reproducible evidence. Build and run the tests before presenting. The older Review 2 report and slides below predate v6 and **must not be described as the current implementation or latest results**.

The research finding is mixed, not a universal ML speedup: on the 10 held-out `late_heavy` seeds, the live tree has median paired whole-run time 0.874× fixed chunk 4; the simpler cost-balanced scheduler *without a pilot* is better at 0.846×. On uniform and phase-shifted inputs, the live tree is slightly slower. Although six pilot timing metrics are genuine inputs, the selected mixed tree splits only on remaining-task metadata; an ablation restricted to measured pilot metrics predicts fixed chunk 4 on both leaves. See the demo note for the full comparison and limitations.

**Review 2 entry point:** The [expanded 12-page report](output/OS_Review2_Expanded_Report.pdf) explains the project, method, module workflows, dataset, measured comparison, evidence, and current limitations. Its [editable Word version](output/OS_Review2_Expanded_Report.docx) is also included. The prior [short report](output/OS_Review2_User_Edited_With_Module_Workflows.pdf) remains unchanged. Read [REVIEW2_DEMO.md](REVIEW2_DEMO.md) for demonstration commands. The report's comparison uses `results_paired_both_review`; its audit checks 35 matched input groups and 105 timed method runs. The combined scheduler is proposed for a later stage, not implemented here.

This project controls **application-level dispatch** of independent CPU tasks to Linux worker processes. It does **not** patch or replace the Linux kernel scheduler. The trained decision tree selects the next chunk while the process pool is executing, after each measured round. A cost-increase guard can override its prediction. The CPU task code is compiled C11; the orchestration, compact CART tree and evaluation are Python standard library.

**Current improvement:** `os_sched/scheduler_v3.py` keeps the same saved tree but makes one online decision after a 16-task pilot, then dispatches the remainder in bulk. It reduces the repeated synchronization overhead of the original. See [IMPROVEMENT_NOTES.md](IMPROVEMENT_NOTES.md) and `results_improvement/dashboard.html` for the fresh paired comparison. The original results in `results_final_linux` remain untouched.

**Measured baseline win on a defined workload:** `os_sched/scheduler_v4.py` implements cost-balanced batches with longest-estimated-cost batches first. With corrected end-to-end timing, it beat fixed chunk 4 on all ten fresh rare-tail-straggler test seeds (median paired runtime ratio **0.881**). This is a targeted result, not a universal speedup. Read [COST_BALANCED_RESULTS.md](COST_BALANCED_RESULTS.md) and open `results_straggler_corrected/dashboard.html`; the broader five-workload check is in `results_balanced_corrected`. Earlier cost-balanced timing folders are retained but superseded; see [TIMING_CORRECTION_PLAN.md](TIMING_CORRECTION_PLAN.md).

## Requirements

Ubuntu/WSL2, GCC, Bash and Python 3.12 or newer. No pip packages are needed to build, train, test or run the project. Use at least 2 logical CPUs for the submitted 2-worker settings. The included `build.sh` produces `build/libwork_kernel.so`.

## Verify and run from the project folder

```bash
bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.experiment_complete --output results_final_linux --workers 2 --base 1500000 --prime-base 3000 --count 192 --repeats 5 --train-seeds 6 --holdout-seeds 4 --candidate-repeats 2
python3 -m os_sched.compare_existing --results results_final_linux --workers 2 --base 1500000 --prime-base 3000 --count 192 --repeats 5
python3 -m os_sched.verify_results results_final_linux
python3 -m os_sched.capture_tests --output results_final_linux/tests.txt
python3 -m os_sched.live_demo --model results_final_linux/model.json --output results_final_linux/live_demo.json --workload phase_shift --workers 2
python3 -m os_sched.experiment_improvement --model results_final_linux/model.json --output results_improvement --workers 2 --base 1500000 --prime-base 3000 --count 192 --repeats 5
python3 -m os_sched.verify_improvement results_improvement
python3 -m os_sched.live_demo_improvement --model results_final_linux/model.json --output results_improvement/live_demo.json --workload high --workers 2
python3 -m os_sched.verify_straggler results_straggler_corrected
python3 -m os_sched.live_demo_straggler --seed 11001 --output results_straggler_corrected/live_demo.json
```

The profiling and experiment run take several minutes. For a quick **functional** demonstration, open the saved model, manifest, logs and CSVs, run the 12 automated tests, then run `python3 -m os_sched.verify_paired` and `bash show_both_review2.sh`. A new timed run will differ slightly because operating-system scheduling and host load vary.

## Openable results

Open `results_final_linux/dashboard.html` in a browser. It is a self-contained local results page with real summary metrics, latency, decision traces, existing-option comparisons and code excerpts. `raw_results.csv`, `summary.csv`, `decisions.csv`, `existing_options_raw.csv`, `training_data.csv` and `dataset.csv` open in Excel or a text editor. `model.json` is the saved tree. `manifest.json` records all settings, machine details and timing definitions. `validation.json` records independent consistency checks. `live_demo.json` records a fresh model-loaded run.

For the newer low-barrier method, open `results_improvement/dashboard.html`. Its `raw.csv`, `summary.csv`, `decisions.csv`, `validation.json`, `tests.txt` and `live_demo.json` contain the evidence. The same model was reused; this is a scheduler implementation improvement, not a newly trained model.

For the separate non-ML cost-balanced method, open `results_straggler_corrected/dashboard.html`. It includes the ten-run tail-straggler win and a transparent five-workload generalization table. `results_straggler_corrected/dataset.csv` records every generated task and spike position.

## Workloads and algorithms

Synthetic classes are uniform, moderate, high-variance and phase-shifted deterministic C loops. The additional `prime_scan` class performs real C prime counting over disjoint integer ranges (not an external dataset). Each task is deterministic. The dataset CSV records the actual task values and seeds. All methods must produce the same checksum for each workload/seed.

Baselines are sequential and fixed chunks 1, 4, 16, 64. Adaptive methods are a threshold rule, a depth-3 Gini CART tree and the same tree with a measured task-cost increase guard. The guard halves the next chunk when mean measured task service time rises more than 25% compared with the previous round. The tree is fitted on randomized candidate measurements of chunks 1, 4, 16 and 64. Profiling features use the same pilot boundary as the online scheduler. Near-ties within 3% prefer the larger chunk. Training, holdout and final test seeds are disjoint.

A separate paired benchmark compares against existing Python APIs: `multiprocessing.Pool.map`, `Pool.imap_unordered` and `concurrent.futures.ProcessPoolExecutor.map` at chunk sizes 4 and 16. The standard APIs use their own dispatch internals, so this is an end-to-end practical comparison, not a same-internals microbenchmark.

## Metrics and boundary

Primary: **end-to-end wall-clock time**, including worker process startup/teardown, dispatch, online measurement and tree inference. Secondary: throughput, speedup versus the paired sequential run, process startup, parent/child CPU seconds and capacity-normalized CPU utilization (Linux), batch response latency p50/p95/p99 from parent dispatch to worker completion, queue wait p95, C service p95 and decision latency p95. Five test seeds are used for each workload and method; method order is seeded and randomized. Median, mean, standard deviation, min/max and paired ratio to fixed chunk 4 are saved. These runs are exploratory on one machine, not evidence of cross-machine speedup.

## Novelty boundary and limitations

Adaptive chunk scheduling and learning-based scheduling already exist. The project-specific contribution under test is the interpretable measured-data tree plus a task-cost-change guard in a Python process pool executing compiled C CPU work, with a direct guarded-vs-unguarded ablation and full overhead accounting. It is **not** a claim of worldwide first use or guaranteed performance improvement. The profiling labels are noisy, synthetic tasks do not represent every application, and two logical CPUs limit generalization. The results page should be used to state only what the measured implementation supports.
