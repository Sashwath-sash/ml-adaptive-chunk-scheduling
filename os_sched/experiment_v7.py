"""Train an offline learned dispatch selector, then measure it on untouched runs.

No pilot is executed at inference: the model uses metadata known before work.
Training labels come from repeated complete-invocation timings, not a cost
formula or hand-authored workload label. Splits use disjoint seeds and scales.
"""
import argparse
import csv
import json
import math
import platform
import random
import statistics
import time
from collections import Counter
from pathlib import Path

from .compare_existing import builtin
from .experiment_v6 import KINDS_V6, csv_read, csv_write, task_list
from .scheduler_v2 import run as run_fixed
from .scheduler_v4 import estimated_cost
from .scheduler_v7 import run_policy
from .tree import DecisionTree

CANDIDATES = ("fixed_16", "contig_32", "lpt_2", "lpt_4", "lpt_8")
BASELINE = "contig_32"
FINAL_METHODS = ("sequential", "fixed_4", *CANDIDATES,
                 "pool_map_16", "process_executor_16", "learned")
TRAIN_SCALES = ((800_000, 1600), (3_200_000, 6400))
VALIDATION_SCALE = (1_600_000, 3200)
TEST_SCALE = (2_200_000, 4400)
SEED_BASE = {"train": 16001, "validation": 17001, "test": 18001}
FEATURES = (
    "log_mean_cost", "log_total_cost", "cost_cv", "max_to_mean",
    "p90_to_mean", "p50_to_mean", "tail_cost_share", "first_quarter_share",
    "last_quarter_share", "max_index_fraction", "prime_fraction",
    "log_mean_work", "log_max_work", "count", "workers",
)


def feature_vector(tasks, workers):
    if not tasks or workers < 1:
        raise ValueError("nonempty tasks and workers >= 1 required")
    costs = [estimated_cost(task) for task in tasks]
    ordered = sorted(costs)
    mean = statistics.mean(costs)
    total = sum(costs)
    n = len(tasks)
    quarter = max(1, n // 4)
    works = [task.work for task in tasks]
    return [
        math.log1p(mean), math.log1p(total), statistics.pstdev(costs) / max(mean, 1e-12),
        max(costs) / max(mean, 1e-12), ordered[round(.9 * (n - 1))] / max(mean, 1e-12),
        statistics.median(costs) / max(mean, 1e-12),
        sum(ordered[-max(1, n // 8):]) / max(total, 1e-12),
        sum(costs[:quarter]) / max(total, 1e-12),
        sum(costs[-quarter:]) / max(total, 1e-12),
        costs.index(max(costs)) / max(1, n - 1),
        sum(task.kernel == "prime" for task in tasks) / n,
        math.log1p(statistics.mean(works)), math.log1p(max(works)),
        float(n), float(workers),
    ]


def measured_candidates(args, split, scales, seed_count):
    groups = [(kind, seed, base, prime) for base, prime in scales
              for kind in KINDS_V6
              for seed in range(SEED_BASE[split], SEED_BASE[split] + seed_count)]
    random.Random(51171 if split == "train" else 61171).shuffle(groups)
    raw, labels = [], []
    for group_no, (kind, seed, base, prime) in enumerate(groups, 1):
        tasks = task_list(kind, args.count, base, prime, seed)
        features = dict(zip(FEATURES, feature_vector(tasks, args.workers)))
        times = {policy: [] for policy in CANDIDATES}
        group_rows = []
        checksum = None
        for repeat in range(args.candidate_repeats):
            order = list(CANDIDATES)
            random.Random(seed * 131 + repeat * 23 + base + len(kind)).shuffle(order)
            for position, policy in enumerate(order):
                result = run_policy(tasks, args.workers, policy)
                checksum = result["checksum"] if checksum is None else checksum
                if result["checksum"] != checksum:
                    raise AssertionError(f"checksum mismatch: {kind} {seed} {policy}")
                times[policy].append(result["elapsed_s"])
                group_rows.append({"split": split, "kind": kind, "seed": seed,
                                   "base": base, "prime_base": prime, "repeat": repeat,
                                   "order": position, "policy": policy,
                                   "elapsed_s": result["elapsed_s"], "checksum": checksum,
                                   "planning_s": result["planning_s"],
                                   "batch_count": result["batch_count"]})
        medians = {policy: statistics.median(values) for policy, values in times.items()}
        best = min(CANDIDATES, key=lambda policy: medians[policy])
        label = best if medians[best] <= .98 * medians[BASELINE] else BASELINE
        labels.append({"kind": kind, "seed": seed, "base": base, "prime_base": prime,
                       "label": label, **features,
                       **{f"time_{policy}": medians[policy] for policy in CANDIDATES}})
        raw.extend(group_rows)
        print(f"{split.upper()} {group_no:02}/{len(groups)} {kind:11} "
              f"base={base} seed={seed} label={label}", flush=True)
    return raw, labels


def train(args, folder):
    if (folder / "test_raw.csv").exists():
        raise RuntimeError("final test exists; refusing to overwrite training")
    raw, labels = measured_candidates(args, "train", TRAIN_SCALES, args.train_seeds)
    csv_write(folder / "train_raw.csv", raw)
    csv_write(folder / "train_groups.csv", labels)
    manifest = {"status": "PASS", "candidate_repeats": args.candidate_repeats,
                "workers": args.workers, "count": args.count,
                "scales": TRAIN_SCALES, "seed_base": SEED_BASE["train"],
                "groups": len(labels), "timed_runs": len(raw),
                "features": FEATURES, "candidates": CANDIDATES,
                "labels": dict(Counter(row["label"] for row in labels)),
                "label_rule": "lowest median complete invocation, if >=2% faster than contig_32; else contig_32"}
    (folder / "train_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("TRAIN PASS", manifest["labels"], flush=True)


def fit(rows, depth, leaf):
    features = [[float(row[name]) for name in FEATURES] for row in rows]
    return DecisionTree(max_depth=depth, min_leaf=leaf).fit(features, [row["label"] for row in rows])


def tune(args, folder):
    if (folder / "test_raw.csv").exists():
        raise RuntimeError("final test exists; refusing to retune")
    train_manifest = json.loads((folder / "train_manifest.json").read_text(encoding="utf-8"))
    if (train_manifest["workers"], train_manifest["count"]) != (args.workers, args.count):
        raise ValueError("training configuration mismatch")
    raw, groups = measured_candidates(args, "validation", (VALIDATION_SCALE,), args.validation_seeds)
    csv_write(folder / "validation_raw.csv", raw)
    csv_write(folder / "validation_groups.csv", groups)
    training = csv_read(folder / "train_groups.csv")
    scores, models = [], {}
    for depth in (1, 2, 3, 4, 5):
        for leaf in (2, 3, 4, 6, 8):
            model = fit(training, depth, leaf)
            regrets, ratios = [], []
            for row in groups:
                policy = model.predict_one([float(row[name]) for name in FEATURES])
                times = {candidate: float(row[f"time_{candidate}"]) for candidate in CANDIDATES}
                regrets.append(math.log(times[policy] / min(times.values())))
                ratios.append(times[policy] / times[BASELINE])
            score = statistics.mean(regrets)
            scores.append({"depth_cap": depth, "min_leaf": leaf,
                           "mean_log_regret": score,
                           "median_ratio_to_contig32": statistics.median(ratios),
                           "wins": sum(ratio < 1 for ratio in ratios)})
            models[(depth, leaf)] = model
    csv_write(folder / "validation_scores.csv", scores)
    minimum = min(row["mean_log_regret"] for row in scores)
    near = [row for row in scores if row["mean_log_regret"] <= minimum + .005]
    chosen = min(near, key=lambda row: (row["depth_cap"], -row["min_leaf"]))
    model = models[(chosen["depth_cap"], chosen["min_leaf"])]
    artifact = {"model": model.to_dict(), "features": FEATURES,
                "candidates": CANDIDATES, "fallback": BASELINE,
                "chosen": chosen, "selection_rule": "lowest validation mean log regret; within 0.005 choose shallowest/largest leaf",
                "training_groups": len(training), "validation_groups": len(groups),
                "training_seeds": list(range(SEED_BASE["train"], SEED_BASE["train"] + args.train_seeds)),
                "validation_seeds": list(range(SEED_BASE["validation"], SEED_BASE["validation"] + args.validation_seeds)),
                "train_scales": TRAIN_SCALES, "validation_scale": VALIDATION_SCALE,
                "workers": args.workers, "count": args.count,
                "inference_boundary": "task metadata only, before pool creation; zero runtime pilot"}
    (folder / "model.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print("TUNE PASS", chosen, flush=True)


def load_model(folder, workers, count):
    artifact = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    if artifact["features"] != list(FEATURES) or artifact["candidates"] != list(CANDIDATES):
        raise ValueError("model schema mismatch")
    if (artifact["workers"], artifact["count"]) != (workers, count):
        raise ValueError("model was trained for different workers/count")
    return DecisionTree.from_dict(artifact["model"]), artifact


def run_learned(tasks, workers, model):
    started_ns = time.perf_counter_ns()
    features = feature_vector(tasks, workers)
    selected = model.predict_one(features)
    if selected not in CANDIDATES:
        raise ValueError("model selected unsupported policy")
    inference_s = (time.perf_counter_ns() - started_ns) / 1e9
    result = run_policy(tasks, workers, selected)
    result["elapsed_s"] += inference_s
    result["selected_policy"] = selected
    result["inference_s"] = inference_s
    return result


def summary_row(raw, kind, method):
    baseline = {int(row["seed"]): float(row["elapsed_s"]) for row in raw
                if row["kind"] == kind and row["method"] == BASELINE}
    subset = [row for row in raw if row["kind"] == kind and row["method"] == method]
    ratios = [float(row["elapsed_s"]) / baseline[int(row["seed"])] for row in subset]
    rng = random.Random(81171 + len(kind) * 71 + len(method))
    boots = sorted(statistics.median(rng.choices(ratios, k=len(ratios))) for _ in range(3000))
    return {"kind": kind, "method": method, "n": len(subset),
            "median_wall_s": statistics.median(float(row["elapsed_s"]) for row in subset),
            "median_paired_ratio": statistics.median(ratios),
            "mean_paired_ratio": statistics.mean(ratios),
            "paired_wins": sum(ratio < 1 for ratio in ratios),
            "bootstrap_median_95_low": boots[74], "bootstrap_median_95_high": boots[2924],
            "median_batch_p95_s": statistics.median(float(row["batch_p95_s"]) for row in subset if row["batch_p95_s"])
            if any(row["batch_p95_s"] for row in subset) else ""}


def test(args, folder):
    if (folder / "test_raw.csv").exists():
        raise RuntimeError("final test already exists; refusing to overwrite")
    model, artifact = load_model(folder, args.workers, args.count)
    groups = [(kind, SEED_BASE["test"] + i) for kind in KINDS_V6 for i in range(args.test_seeds)]
    random.Random(91171).shuffle(groups)
    raw = []
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = task_list(kind, args.count, *TEST_SCALE, seed)
        order = list(FINAL_METHODS)
        random.Random(seed * 71 + len(kind)).shuffle(order)
        checksum = None
        for position, method in enumerate(order):
            if method == "learned":
                result = run_learned(tasks, args.workers, model)
            elif method == "sequential":
                result = run_fixed(tasks, args.workers, "sequential")
            elif method in ("pool_map_16", "process_executor_16"):
                result = builtin(tasks, args.workers, method)
            else:
                result = run_policy(tasks, args.workers, method)
            checksum = result["checksum"] if checksum is None else checksum
            if result["checksum"] != checksum:
                raise AssertionError(f"checksum mismatch: {kind} {seed} {method}")
            raw.append({"kind": kind, "seed": seed, "base": TEST_SCALE[0], "prime_base": TEST_SCALE[1],
                        "order": position, "method": method, "selected_policy": result.get("selected_policy", ""),
                        "elapsed_s": result["elapsed_s"], "checksum": checksum,
                        "planning_s": result.get("planning_s", ""), "inference_s": result.get("inference_s", ""),
                        "startup_s": result.get("startup_s", ""), "batch_p95_s": result.get("batch_latency_p95_s", ""),
                        "batch_count": result.get("batch_count", "")})
        print(f"TEST {group_no:02}/{len(groups)} {kind:11} seed={seed}", flush=True)
    csv_write(folder / "test_raw.csv", raw)
    summary = [summary_row(raw, kind, method) for kind in KINDS_V6 for method in FINAL_METHODS]
    csv_write(folder / "test_summary.csv", summary)
    manifest = {"status": "PASS", "platform": platform.platform(), "workers": args.workers,
                "count": args.count, "groups": len(groups), "timed_runs": len(raw),
                "methods": FINAL_METHODS, "seed_base": SEED_BASE["test"],
                "test_seeds": args.test_seeds, "test_scale": TEST_SCALE,
                "training_seeds": artifact["training_seeds"], "validation_seeds": artifact["validation_seeds"],
                "checksum_equality": True, "method_order": "seeded shuffle within each matched task group",
                "timer": "whole invocation including feature calculation, prediction, planning, pool startup, IPC, C work, and teardown",
                "primary_metric": "median paired ratio of complete time to contig_32",
                "scope": "constructed workloads on one WSL2 host; exploratory"}
    (folder / "test_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"TEST PASS {len(groups)} groups, {len(raw)} timed runs, equal checksums", flush=True)
    for row in summary:
        if row["method"] == "learned":
            print(f"LEARNED {row['kind']:11} ratio={row['median_paired_ratio']:.3f} wins={row['paired_wins']}/{row['n']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("train", "tune", "test"))
    parser.add_argument("--output", type=Path, default=Path("results_learned_v7"))
    parser.add_argument("--count", type=int, default=192)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--train-seeds", type=int, default=4)
    parser.add_argument("--validation-seeds", type=int, default=3)
    parser.add_argument("--test-seeds", type=int, default=10)
    parser.add_argument("--candidate-repeats", type=int, default=2)
    args = parser.parse_args()
    if min(args.count, args.workers, args.train_seeds, args.validation_seeds, args.test_seeds, args.candidate_repeats) < 1:
        parser.error("all counts must be positive")
    args.output.mkdir(exist_ok=True)
    {"train": train, "tune": tune, "test": test}[args.command](args, args.output)


if __name__ == "__main__":
    main()
