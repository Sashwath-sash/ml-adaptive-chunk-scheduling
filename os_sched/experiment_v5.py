"""Reproducible, leakage-separated training and paired evaluation for v5.

Usage: python3 -m os_sched.experiment_v5 train|validation|test [options]
Training seeds are 2001+, validation 3001+, final test 4001+ for every kind.
The final test is not used to fit, tune, or select the policy selector.
"""
import argparse
import csv
import json
import math
import platform
import random
import statistics
from pathlib import Path

from .experiment_complete import KINDS, make_tasks
from .scheduler_v5 import FEATURES, POLICIES, run_auto, run_policy, task_features
from .straggler_workload import generate_tail_spike
from .tree import DecisionTree

ALL_KINDS = (*KINDS, "late_heavy")
SEED_START = {"train": 2001, "validation": 3001, "test": 4001}


def tasks_for(kind, seed, args):
    if kind == "late_heavy":
        return generate_tail_spike(args.count, args.base, seed, 40)[0]
    return make_tasks(kind, args.count, args.base, args.prime_base, seed)


def save_csv(path, rows):
    if not rows:
        raise ValueError(f"no data for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_models(output):
    data = json.loads((output / "selector.json").read_text(encoding="utf-8"))
    selector = DecisionTree.from_dict(data["tree"])
    chunk_model = DecisionTree.from_dict(json.loads((Path(__file__).resolve().parents[1] / "results_final_linux" / "model.json").read_text(encoding="utf-8")))
    if data["features"] != list(FEATURES) or data["policies"] != list(POLICIES):
        raise ValueError("saved selector schema does not match the implementation")
    return selector, chunk_model, data


def label_for(medians, margin):
    baseline = medians["fixed_4"]
    best = min(POLICIES, key=lambda method: medians[method])
    return best if medians[best] <= baseline * (1 - margin) else "fixed_4"


def train(args, output):
    if (output / "test_raw.csv").exists():
        raise RuntimeError("final test results exist; refusing to retrain in this output folder")
    chunk_model = DecisionTree.from_dict(json.loads((Path(__file__).resolve().parents[1] / "results_final_linux" / "model.json").read_text(encoding="utf-8")))
    raw, training = [], []
    groups = [(kind, SEED_START["train"] + j) for kind in ALL_KINDS for j in range(args.train_seeds)]
    random.Random(50917).shuffle(groups)
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = tasks_for(kind, seed, args)
        features = task_features(tasks, args.workers)
        runtimes = {method: [] for method in POLICIES}
        checksum = None
        for repeat in range(args.candidate_repeats):
            order = list(POLICIES)
            random.Random(seed * 101 + repeat * 17 + len(kind)).shuffle(order)
            for position, method in enumerate(order):
                result = run_policy(tasks, args.workers, method, chunk_model)
                if checksum is None:
                    checksum = result["checksum"]
                if checksum != result["checksum"]:
                    raise AssertionError(f"checksum mismatch: {kind} {seed} {method}")
                runtimes[method].append(result["elapsed_s"])
                raw.append({"split": "train", "kind": kind, "seed": seed, "repeat": repeat,
                            "order": position, "method": method, "elapsed_s": result["elapsed_s"],
                            "checksum": result["checksum"], "startup_s": result["startup_s"],
                            "batch_p95_s": result["batch_latency_p95_s"]})
        medians = {method: statistics.median(runtimes[method]) for method in POLICIES}
        label = label_for(medians, args.margin)
        training.append({"kind": kind, "seed": seed,
                         **dict(zip(FEATURES, features)), "label": label,
                         **{f"{method}_median_s": medians[method] for method in POLICIES}})
        print(f"TRAIN {group_no:02}/{len(groups)} {kind:11} seed={seed} label={label}", flush=True)
    model = DecisionTree(max_depth=3, min_leaf=4).fit(
        [[row[key] for key in FEATURES] for row in training], [row["label"] for row in training])
    save_csv(output / "train_raw.csv", raw)
    save_csv(output / "train_labels.csv", training)
    record = {"tree": model.to_dict(), "features": FEATURES, "policies": POLICIES,
              "train_seeds": list(range(SEED_START["train"], SEED_START["train"] + args.train_seeds)),
              "candidate_repeats": args.candidate_repeats, "improvement_margin": args.margin,
              "workers": args.workers, "count": args.count, "base": args.base,
              "prime_base": args.prime_base,
              "label_counts": {method: sum(row["label"] == method for row in training) for method in POLICIES},
              "note": "tree fitted only to training seeds; targets are measured full-run candidate medians"}
    (output / "selector.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("TRAIN COMPLETE", record["label_counts"], flush=True)


def percentile(values, p):
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(len(s) - 1, lo + 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def evaluate(args, output):
    selector, chunk_model, metadata = load_models(output)
    if (metadata["workers"], metadata["count"], metadata["base"], metadata["prime_base"]) != (
        args.workers, args.count, args.base, args.prime_base):
        raise ValueError("training and evaluation configuration must match")
    split = args.command
    seed_count = args.validation_seeds if split == "validation" else args.test_seeds
    groups = [(kind, SEED_START[split] + j) for kind in ALL_KINDS for j in range(seed_count)]
    random.Random(65119 if split == "validation" else 78231).shuffle(groups)
    raw = []
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = tasks_for(kind, seed, args)
        checksum = None
        order = [*POLICIES, "auto"]
        random.Random(seed * 211 + len(kind)).shuffle(order)
        for position, method in enumerate(order):
            result = run_auto(tasks, args.workers, selector, chunk_model) if method == "auto" else run_policy(tasks, args.workers, method, chunk_model)
            if checksum is None:
                checksum = result["checksum"]
            if result["checksum"] != checksum:
                raise AssertionError(f"checksum mismatch: {kind} {seed} {method}")
            raw.append({"split": split, "kind": kind, "seed": seed, "order": position,
                        "method": method, "selected_policy": result.get("selected_policy", ""),
                        "elapsed_s": result["elapsed_s"], "checksum": result["checksum"],
                        "startup_s": result["startup_s"],
                        "batch_p95_s": result["batch_latency_p95_s"],
                        "queue_wait_p95_s": result.get("queue_wait_p95_s", ""),
                        "service_p95_s": result.get("service_p95_s", ""),
                        "cpu_s": result.get("cpu_s", ""),
                        "feature_s": result.get("feature_s", ""),
                        "selection_s": result.get("selection_s", "")})
        print(f"{split.upper()} {group_no:02}/{len(groups)} {kind:11} seed={seed}", flush=True)
    save_csv(output / f"{split}_raw.csv", raw)
    summary = []
    rng = random.Random(99221 if split == "validation" else 99223)
    for kind in ALL_KINDS:
        baseline = {int(row["seed"]): float(row["elapsed_s"]) for row in raw if row["kind"] == kind and row["method"] == "fixed_4"}
        for method in (*POLICIES, "auto"):
            subset = [row for row in raw if row["kind"] == kind and row["method"] == method]
            ratios = [float(row["elapsed_s"]) / baseline[int(row["seed"])] for row in subset]
            boots = [statistics.median(rng.choices(ratios, k=len(ratios))) for _ in range(2000)]
            summary.append({"kind": kind, "method": method, "n": len(subset),
                            "median_wall_s": statistics.median(float(row["elapsed_s"]) for row in subset),
                            "median_paired_ratio": statistics.median(ratios),
                            "mean_paired_ratio": statistics.mean(ratios),
                            "paired_wins": sum(value < 1 for value in ratios),
                            "median_ratio_bootstrap_95_low": percentile(boots, 2.5),
                            "median_ratio_bootstrap_95_high": percentile(boots, 97.5),
                            "median_batch_p95_s": statistics.median(float(row["batch_p95_s"]) for row in subset),
                            "median_startup_s": statistics.median(float(row["startup_s"]) for row in subset)})
    save_csv(output / f"{split}_summary.csv", summary)
    manifest = {"status": "PASS", "split": split, "system": platform.platform(),
                "workers": args.workers, "count": args.count, "base": args.base,
                "prime_base": args.prime_base, "seeds": list(range(SEED_START[split], SEED_START[split] + seed_count)),
                "kinds": ALL_KINDS, "methods": (*POLICIES, "auto"),
                "raw_rows": len(raw), "groups": len(groups),
                "checksum_equality": True, "method_order": "seeded shuffle within group",
                "timing": "full invocation including feature extraction, selector, planning, pool startup and teardown; offline training excluded",
                "primary_metric": "median within-seed wall-time ratio to fixed_4",
                "scope": "one WSL2 host; exploratory; 95% bootstrap intervals from small seed samples"}
    (output / f"{split}_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"PASS {split}: {len(groups)} groups / {len(raw)} timed runs", flush=True)
    for row in summary:
        if row["method"] == "auto":
            print(f"AUTO {row['kind']:11} n={row['n']} ratio={row['median_paired_ratio']:.3f} wins={row['paired_wins']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("train", "validation", "test"))
    parser.add_argument("--output", type=Path, default=Path("results_policy_v5"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--count", type=int, default=192)
    parser.add_argument("--base", type=int, default=1_500_000)
    parser.add_argument("--prime-base", type=int, default=3000)
    parser.add_argument("--train-seeds", type=int, default=6)
    parser.add_argument("--validation-seeds", type=int, default=3)
    parser.add_argument("--test-seeds", type=int, default=5)
    parser.add_argument("--candidate-repeats", type=int, default=2)
    parser.add_argument("--margin", type=float, default=0.05)
    args = parser.parse_args()
    if args.workers < 1 or args.count < 16 or args.train_seeds < 1 or args.candidate_repeats < 1 or not 0 <= args.margin < 1:
        parser.error("invalid positive workers/count/seeds/repeats or margin")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == "train":
        train(args, args.output)
    else:
        evaluate(args, args.output)


if __name__ == "__main__":
    main()
