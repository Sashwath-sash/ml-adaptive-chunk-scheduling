"""Reproducible train/test experiment with paired seeds and online decisions."""
import argparse
import csv
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

from .scheduler_v2 import CHUNKS, METHODS, collect_training_row, run
from .tree import DecisionTree
from .workload import generate

KINDS = ("uniform", "moderate", "high", "phase_shift", "prime_scan")
FEATURES = ("mean_task_s", "batch_spread", "throughput", "current_chunk", "remaining_fraction")


def progress(out, message):
    print(message, flush=True)
    with (out / "run_console.txt").open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_tasks(kind, count, synthetic_base, prime_base, seed):
    return generate(kind, count, prime_base if kind == "prime_scan" else synthetic_base, seed)


def train_model(out, args):
    training_rows, training_labels, records = [], [], []
    started = time.perf_counter()
    for split, seeds in (("train", range(11, 11 + args.train_seeds)),
                         ("holdout", range(101, 101 + args.holdout_seeds))):
        for kind in KINDS:
            for seed in seeds:
                tasks = make_tasks(kind, args.count, args.base, args.prime_base, seed)
                for current in (1, 4, 16):
                    features, label, times = collect_training_row(
                        tasks, args.workers, current, args.candidate_repeats,
                        seed=seed * 101 + current)
                    record = {"split": split, "workload": kind, "seed": seed,
                              **dict(zip(FEATURES, features)), "best_chunk": label,
                              **{f"candidate_{c}_median_s": times[c] for c in CHUNKS}}
                    records.append(record)
                    if split == "train":
                        training_rows.append(features)
                        training_labels.append(label)
            progress(out, f"PROFILE {split:7s} {kind:11s} rows={len(records)}")
    model = DecisionTree(max_depth=3, min_leaf=5).fit(training_rows, training_labels)
    holdout = [r for r in records if r["split"] == "holdout"]
    exact = sum(model.predict_one([r[k] for k in FEATURES]) == r["best_chunk"] for r in holdout) / len(holdout)
    regrets = []
    for record in holdout:
        predicted = model.predict_one([record[k] for k in FEATURES])
        best = min(record[f"candidate_{c}_median_s"] for c in CHUNKS)
        regrets.append(record[f"candidate_{predicted}_median_s"] / best)
    write_csv(out / "training_data.csv", records)
    (out / "model.json").write_text(json.dumps(model.to_dict(), indent=2), encoding="utf-8")
    return model, {"training_and_label_collection_s": time.perf_counter() - started,
                   "training_rows": len(training_rows), "holdout_rows": len(holdout),
                   "holdout_exact_accuracy": exact,
                   "holdout_median_regret_ratio": statistics.median(regrets),
                   "train_seeds": list(range(11, 11 + args.train_seeds)),
                   "holdout_seeds": list(range(101, 101 + args.holdout_seeds)),
                   "candidate_repeats": args.candidate_repeats,
                   "label_rule": "smallest median candidate time; chunks within 3% tie use larger chunk"}


def run_experiment(out, args, model):
    raw, decisions, dataset = [], [], []
    # These seeds were never used for model fitting or holdout selection.
    work_order = [(kind, repeat) for kind in KINDS for repeat in range(args.repeats)]
    random.Random(24680).shuffle(work_order)
    for kind, repeat in work_order:
            seed = 1001 + repeat
            tasks = make_tasks(kind, args.count, args.base, args.prime_base, seed)
            dataset.extend({"workload": kind, "repeat": repeat + 1, "seed": seed,
                            "task_index": i, "work": task.work, "start_or_seed": task.seed,
                            "kernel": task.kernel} for i, task in enumerate(tasks))
            # Warm-up is separate and untimed; it does not enter the raw CSV.
            run(tasks[:min(16, len(tasks))], args.workers, "fixed_4")
            baseline = run(tasks, args.workers, "sequential")
            order = list(METHODS[1:])
            random.Random(seed * 73 + len(kind)).shuffle(order)
            results = {"sequential": baseline}
            for method in order:
                results[method] = run(tasks, args.workers, method, model)
            checksums = {result["checksum"] for result in results.values()}
            if len(checksums) != 1:
                raise AssertionError(f"checksum mismatch: {kind} repeat {repeat + 1}")
            for sequence, method in enumerate(("sequential", *order)):
                result = results[method]
                raw.append({"workload": kind, "repeat": repeat + 1, "seed": seed,
                            "method_order": sequence, "method": method,
                            "workers": 1 if method == "sequential" else args.workers,
                            "tasks": args.count, "elapsed_s": result["elapsed_s"],
                            "throughput_tasks_s": args.count / result["elapsed_s"],
                            "speedup_vs_sequential": baseline["elapsed_s"] / result["elapsed_s"],
                            "startup_s": result["startup_s"], "cpu_s": result["cpu_s"],
                            "cpu_utilization_fraction": result["cpu_utilization_fraction"],
                            "batch_latency_p50_s": result["batch_latency_p50_s"],
                            "batch_latency_p95_s": result["batch_latency_p95_s"],
                            "batch_latency_p99_s": result["batch_latency_p99_s"],
                            "queue_wait_p95_s": result["queue_wait_p95_s"],
                            "service_p95_s": result["service_p95_s"],
                            "decision_p95_s": result["decision_p95_s"],
                            "checksum": result["checksum"], "decisions": len(result["decisions"]),
                            "guard_events": sum(d["reason"] == "cost_increase_guard" for d in result["decisions"])})
                decisions.extend({"workload": kind, "repeat": repeat + 1, "seed": seed,
                                  "method": method, **d} for d in result["decisions"])
            progress(out, f"RUN {kind:11s} repeat={repeat + 1} fixed4={results['fixed_4']['elapsed_s']:.3f}s "
                          f"tree={results['ml']['elapsed_s']:.3f}s guarded={results['guarded_ml']['elapsed_s']:.3f}s")
    write_csv(out / "dataset.csv", dataset)
    write_csv(out / "raw_results.csv", raw)
    write_csv(out / "decisions.csv", decisions)
    summaries = []
    for kind in KINDS:
        for method in METHODS:
            rows = [r for r in raw if r["workload"] == kind and r["method"] == method]
            times = [r["elapsed_s"] for r in rows]
            fixed4 = {r["repeat"]: r["elapsed_s"] for r in raw
                      if r["workload"] == kind and r["method"] == "fixed_4"}
            summaries.append({"workload": kind, "method": method, "runs": len(rows),
                              "median_elapsed_s": statistics.median(times),
                              "mean_elapsed_s": statistics.mean(times),
                              "stdev_elapsed_s": statistics.stdev(times) if len(times) > 1 else 0.0,
                              "min_elapsed_s": min(times), "max_elapsed_s": max(times),
                              "median_speedup_vs_sequential": statistics.median(r["speedup_vs_sequential"] for r in rows),
                              "median_ratio_to_paired_fixed4": statistics.median(r["elapsed_s"] / fixed4[r["repeat"]] for r in rows),
                              "median_batch_latency_p95_s": statistics.median(r["batch_latency_p95_s"] for r in rows),
                              "median_decision_p95_s": statistics.median(r["decision_p95_s"] for r in rows),
                              "total_guard_events": sum(r["guard_events"] for r in rows)})
    write_csv(out / "summary.csv", summaries)
    return {"raw_rows": len(raw), "summary_rows": len(summaries),
            "dataset_rows": len(dataset), "decision_rows": len(decisions),
            "all_checksums_equal": True}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=Path("results_complete"))
    ap.add_argument("--workers", type=int, default=min(2, os.cpu_count() or 1))
    ap.add_argument("--base", type=int, default=1_500_000, help="synthetic C iterations per task")
    ap.add_argument("--prime-base", type=int, default=300, help="integers checked for primality per task")
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--train-seeds", type=int, default=8)
    ap.add_argument("--holdout-seeds", type=int, default=4)
    ap.add_argument("--candidate-repeats", type=int, default=2)
    args = ap.parse_args()
    if min(args.workers, args.base, args.prime_base, args.train_seeds,
           args.holdout_seeds, args.candidate_repeats, args.repeats) < 1 or args.count < 96:
        ap.error("positive parameters and count >= 96 required")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "run_console.txt").write_text("", encoding="utf-8")
    started = time.perf_counter()
    model, learning = train_model(args.output, args)
    experiment = run_experiment(args.output, args, model)
    try:
        compiler = subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0]
    except (OSError, subprocess.CalledProcessError):
        compiler = "not available"
    manifest = {"project": "Machine-Learning-Assisted Adaptive Chunk Scheduling for Multiprocessing Workloads",
                "system": platform.platform(), "python": sys.version.split()[0], "compiler": compiler,
                "logical_cpus": os.cpu_count(), "workers": args.workers,
                "synthetic_base_iterations": args.base, "prime_numbers_per_task": args.prime_base,
                "task_count": args.count, "repeats": args.repeats,
                "workloads": KINDS, "methods": METHODS, "training": learning,
                "experiment": experiment, "total_pipeline_s": time.perf_counter() - started,
                "timing_boundary": "total wall clock includes pool startup, teardown, dispatch, live decisions; training excluded from test runs",
                "latency_definition": "batch latency from parent dispatch to worker completion; p95 per run; queue wait and C service separately",
                "cpu_definition": "RUSAGE_SELF + RUSAGE_CHILDREN CPU seconds divided by worker capacity; unavailable on Windows",
                "randomization": "workload/repeat group order seeded and shuffled; method order seeded per group; candidate profile order shuffled per pass",
                "scope": "application-level dispatch to Linux/Windows processes, not kernel scheduler modification"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    progress(args.output, f"COMPLETE {args.output} raw={experiment['raw_rows']} "
                          f"accuracy={learning['holdout_exact_accuracy']:.3f} "
                          f"regret={learning['holdout_median_regret_ratio']:.3f}")


if __name__ == "__main__":
    main()
