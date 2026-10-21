"""Fit an actual task-runtime predictor from individually timed C kernels.

The model is kernel-specific ridge regression on log duration. No optimizer or
third-party ML library is required; coefficients are estimated from measured
worker-process observations, never assigned from a task-cost formula.
"""
import argparse
import csv
import json
import math
import multiprocessing as mp
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from .experiment_v6 import KINDS_V6, task_list
from .scheduler_v2 import _one

TRAIN_SCALES = ((800_000, 1600), (3_200_000, 6400))
VALIDATION_SCALE = (1_600_000, 3200)
SEED_BASE = {"train": 21001, "validation": 22001}


def timed_one(task):
    started_ns = time.perf_counter_ns()
    checksum = _one(task)
    return (time.perf_counter_ns() - started_ns) / 1e9, checksum


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def collect(args, folder, split):
    if split == "train":
        scales, count = TRAIN_SCALES, args.train_seeds
    else:
        scales, count = (VALIDATION_SCALE,), args.validation_seeds
    groups = [(kind, seed, base, prime) for base, prime in scales
              for kind in KINDS_V6
              for seed in range(SEED_BASE[split], SEED_BASE[split] + count)]
    random.Random(47427 if split == "train" else 57527).shuffle(groups)
    rows = []
    for group_no, (kind, seed, base, prime) in enumerate(groups, 1):
        tasks = task_list(kind, args.count, base, prime, seed)
        with mp.Pool(args.workers) as pool:
            results = pool.map(timed_one, tasks, chunksize=8)
        for index, (task, (elapsed_s, checksum)) in enumerate(zip(tasks, results)):
            rows.append({"split": split, "kind": kind, "seed": seed,
                         "base": base, "prime_base": prime, "index": index,
                         "kernel": task.kernel, "work": task.work,
                         "task_seed": task.seed, "service_s": elapsed_s,
                         "checksum": checksum})
        print(f"COST {split} {group_no:02}/{len(groups)} {kind:11} seed={seed}", flush=True)
    write_csv(folder / f"{split}_tasks.csv", rows)
    print(f"SAVED {split}: {len(groups)} groups, {len(rows)} individually timed compiled-C tasks", flush=True)


def features(work, seed):
    return [1.0, math.log(max(1, work)) - 12.0, math.log(max(1, seed)) - 18.0]


def solve(matrix, target):
    n = len(target)
    augmented = [list(matrix[i]) + [target[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-15:
            raise ValueError("singular feature matrix")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        factor = augmented[col][col]
        augmented[col] = [value / factor for value in augmented[col]]
        for row in range(n):
            if row != col:
                scale = augmented[row][col]
                augmented[row] = [a - scale * b for a, b in zip(augmented[row], augmented[col])]
    return [row[-1] for row in augmented]


def fit_kernel(rows, ridge=1.0):
    dimensions = 3
    matrix = [[0.0] * dimensions for _ in range(dimensions)]
    target = [0.0] * dimensions
    for row in rows:
        vector = features(int(row["work"]), int(row["task_seed"]))
        y = math.log(float(row["service_s"]))
        for i in range(dimensions):
            target[i] += vector[i] * y
            for j in range(dimensions):
                matrix[i][j] += vector[i] * vector[j]
    for i in range(1, dimensions):
        matrix[i][i] += ridge
    return solve(matrix, target)


class CostPredictor:
    def __init__(self, coefficients):
        self.coefficients = coefficients

    def predict(self, task):
        coefficients = self.coefficients[task.kernel]
        return math.exp(sum(a * b for a, b in zip(coefficients, features(task.work, task.seed))))


def fit(args, folder):
    training = read_csv(folder / "train_tasks.csv")
    validation = read_csv(folder / "validation_tasks.csv")
    train_seeds = {int(row["seed"]) for row in training}
    val_seeds = {int(row["seed"]) for row in validation}
    if not train_seeds.isdisjoint(val_seeds):
        raise AssertionError("train/validation seed overlap")
    kernels = sorted({row["kernel"] for row in training})
    coefficients = {kernel: fit_kernel([row for row in training if row["kernel"] == kernel]) for kernel in kernels}
    model = CostPredictor(coefficients)
    # Report *relative within-group* cost accuracy, which matters for LPT.
    by_group = defaultdict(list)
    for row in validation:
        by_group[(row["kind"], row["seed"])].append(row)
    accuracy = []
    for (kind, seed), rows in by_group.items():
        actual = [float(row["service_s"]) for row in rows]
        from .scheduler_v4 import estimated_cost
        from .workload import Task
        analytic = [estimated_cost(Task(int(row["work"]), int(row["task_seed"]), row["kernel"])) for row in rows]
        learned = [model.predict(Task(int(row["work"]), int(row["task_seed"]), row["kernel"])) for row in rows]
        scale_a = statistics.median(actual) / statistics.median(analytic)
        scale_l = statistics.median(actual) / statistics.median(learned)
        analytic_error = statistics.median(abs(math.log(max(1e-12, a * scale_a) / y)) for a, y in zip(analytic, actual))
        learned_error = statistics.median(abs(math.log(max(1e-12, p * scale_l) / y)) for p, y in zip(learned, actual))
        accuracy.append({"kind": kind, "seed": seed, "tasks": len(rows),
                         "analytic_median_absolute_log_error": analytic_error,
                         "learned_median_absolute_log_error": learned_error})
    write_csv(folder / "validation_accuracy.csv", accuracy)
    artifact = {"type": "kernel_specific_log_duration_ridge", "ridge": 1.0,
                "features": ["intercept", "log(work)-12", "log(seed)-18"],
                "coefficients": coefficients,
                "train_seeds": sorted(train_seeds), "validation_seeds": sorted(val_seeds),
                "train_rows": len(training), "validation_rows": len(validation),
                "prediction_target": "individually measured C-task service seconds",
                "boundary": "offline fit; online cost predictions from pre-dispatch task metadata"}
    (folder / "model.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print("FIT", coefficients, flush=True)
    for kind in KINDS_V6:
        subset = [row for row in accuracy if row["kind"] == kind]
        a = statistics.median(row["analytic_median_absolute_log_error"] for row in subset)
        l = statistics.median(row["learned_median_absolute_log_error"] for row in subset)
        print(f"ACCURACY {kind:11} analytic={a:.4f} learned={l:.4f}", flush=True)


def load(folder):
    artifact = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    return CostPredictor(artifact["coefficients"]), artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect_train", "collect_validation", "fit"))
    parser.add_argument("--output", type=Path, default=Path("results_cost_model_v8"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--count", type=int, default=192)
    parser.add_argument("--train-seeds", type=int, default=4)
    parser.add_argument("--validation-seeds", type=int, default=3)
    args = parser.parse_args()
    if min(args.workers, args.count, args.train_seeds, args.validation_seeds) < 1:
        parser.error("counts must be positive")
    args.output.mkdir(exist_ok=True)
    if args.command == "fit":
        fit(args, args.output)
    else:
        collect(args, args.output, "train" if args.command == "collect_train" else "validation")


if __name__ == "__main__":
    main()
