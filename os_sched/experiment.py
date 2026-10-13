import argparse
import csv
import json
import math
import os
import platform
import statistics
import sys
import time
from pathlib import Path

from .scheduler import CHUNKS, collect_training_row, run
from .tree import DecisionTree
from .workload import generate

KINDS = ("uniform", "moderate", "high", "phase_shift")
METHODS = ("sequential", "fixed_1", "fixed_4", "fixed_16", "fixed_64", "rule", "ml", "guarded_ml")


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def train(out, workers, base, train_seeds, test_seeds):
    rows, labels, data = [], [], []
    start = time.perf_counter()
    for split, seeds in (("train", train_seeds), ("holdout", test_seeds)):
        for kind in KINDS:
            for seed in seeds:
                features, best, times = collect_training_row(generate(kind, 96, base, seed), workers)
                record = {"split": split, "workload": kind, "seed": seed,
                          **{f"feature_{i}": v for i, v in enumerate(features)}, "best_chunk": best,
                          **{f"candidate_{c}_s": times[c] for c in CHUNKS}}
                data.append(record)
                if split == "train":
                    rows.append(features)
                    labels.append(best)
    model = DecisionTree(max_depth=3, min_leaf=3).fit(rows, labels)
    train_elapsed = time.perf_counter() - start
    holdout = [r for r in data if r["split"] == "holdout"]
    accuracy = sum(model.predict_one([r[f"feature_{i}"] for i in range(5)]) == r["best_chunk"] for r in holdout) / len(holdout)
    write_csv(out / "training_data.csv", data)
    (out / "model.json").write_text(json.dumps(model.to_dict(), indent=2), encoding="utf-8")
    return model, {"training_and_label_collection_s": train_elapsed, "train_samples": len(rows),
                   "holdout_samples": len(holdout), "holdout_exact_chunk_accuracy": accuracy,
                   "train_seeds": train_seeds, "holdout_seeds": test_seeds}


def experiment(out, workers, base, count, repeats, model, test_seeds):
    raw, logs = [], []
    for kind in KINDS:
        for repeat in range(repeats):
            seed = test_seeds[repeat % len(test_seeds)]
            tasks = generate(kind, count, base, seed)
            reference = None
            for method in METHODS:
                result = run(tasks, workers, method, model)
                if reference is None:
                    reference = result["checksum"]
                    sequential_time = result["elapsed_s"]
                if result["checksum"] != reference:
                    raise AssertionError(f"checksum mismatch {kind} {repeat} {method}")
                raw.append({"workload": kind, "repeat": repeat + 1, "seed": seed,
                            "method": method, "workers": 1 if method == "sequential" else workers,
                            "tasks": count, "elapsed_s": result["elapsed_s"],
                            "throughput_tasks_s": count / result["elapsed_s"],
                            "speedup_vs_sequential": sequential_time / result["elapsed_s"],
                            "checksum": result["checksum"], "decisions": len(result["decisions"])})
                for d in result["decisions"]:
                    logs.append({"workload": kind, "repeat": repeat + 1, "seed": seed,
                                 "method": method, **d})
    write_csv(out / "raw_results.csv", raw)
    write_csv(out / "decisions.csv", logs)
    summary = []
    for kind in KINDS:
        for method in METHODS:
            items = [r for r in raw if r["workload"] == kind and r["method"] == method]
            values = [r["elapsed_s"] for r in items]
            summary.append({"workload": kind, "method": method, "runs": len(items),
                            "median_s": statistics.median(values), "min_s": min(values), "max_s": max(values),
                            "median_speedup": statistics.median(r["speedup_vs_sequential"] for r in items)})
    write_csv(out / "summary.csv", summary)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path("results"))
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--base", type=int, default=350000)
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    if args.workers < 1 or args.count < 96 or args.repeats < 1:
        ap.error("workers >= 1, count >= 96, repeats >= 1 required")
    args.output.mkdir(parents=True, exist_ok=True)
    train_seeds = list(range(11, 19))
    test_seeds = list(range(101, 101 + max(args.repeats, 3)))
    model, learning = train(args.output, args.workers, args.base, train_seeds, test_seeds)
    summary = experiment(args.output, args.workers, args.base, args.count, args.repeats, model, test_seeds)
    manifest = {"system": platform.platform(), "python": sys.version.split()[0], "cpu": platform.processor(),
                "logical_cpus": os.cpu_count(), "workers": args.workers, "base_iterations": args.base,
                "task_count": args.count, "repeats": args.repeats, "fixed_chunks": CHUNKS,
                "training": learning, "kernel": "compiled C shared library; gcc -O2",
                "timing_boundary": "end-to-end wall clock including pool startup and inference; offline training reported separately"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}; {len(summary)} summary rows; holdout accuracy={learning['holdout_exact_chunk_accuracy']:.3f}")
    for row in summary:
        if row["method"] in {"fixed_4", "rule", "ml", "guarded_ml"}:
            print(f"{row['workload']:11s} {row['method']:10s} median={row['median_s']:.4f}s speedup={row['median_speedup']:.2f}x")


if __name__ == "__main__":
    main()
