"""Train, validate, and test a live-metrics scheduling tree on disjoint data.

Train: seeds 6001-6004 at two task-cost scales.
Validate: seeds 7001-7003 at an unseen middle scale; choose tree depth/leaf size.
Test: seeds 8001-8010 at another unseen scale; never used for model selection.
Each label comes from repeated, measured *complete invocation* candidate times.
"""
import argparse
import csv
import json
import math
import platform
import random
import statistics
from collections import Counter
from pathlib import Path

from .experiment_complete import KINDS, make_tasks
from .scheduler_v2 import run as run_fixed
from .scheduler_v4 import run_balanced
from .scheduler_v6 import FEATURES, POLICIES, run_live
from .straggler_workload import generate_tail_spike
from .tree import DecisionTree

KINDS_V6 = (*KINDS, "late_heavy")
TRAIN_SCALES = ((500_000, 1000), (3_000_000, 6000))
VALIDATION_SCALE = (1_500_000, 3000)
TEST_SCALE = (2_000_000, 4000)
SEED_BASE = {"train": 6001, "validation": 7001, "test": 8001}
FINAL_METHODS = ("fixed_no_pilot", "cost32_no_pilot", "pilot_fixed_4",
                 "pilot_cost_16", "pilot_cost_32", "pilot_cost_64",
                 "live_tree", "live_tree_runtime_only")
RUNTIME_FEATURES = FEATURES[:6]


def task_list(kind, count, synthetic_base, prime_base, seed):
    if kind == "late_heavy":
        return generate_tail_spike(count, synthetic_base, seed, 40)[0]
    return make_tasks(kind, count, synthetic_base, prime_base, seed)


def csv_write(path, rows):
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def csv_read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def measured_candidates(args, split, scales, seed_count):
    raw, labels = [], []
    groups = [(kind, seed, base, prime) for base, prime in scales
              for kind in KINDS_V6
              for seed in range(SEED_BASE[split], SEED_BASE[split] + seed_count)]
    random.Random(61209 if split == "train" else 71209).shuffle(groups)
    for group_no, (kind, seed, base, prime) in enumerate(groups, 1):
        tasks = task_list(kind, args.count, base, prime, seed)
        by_policy = {policy: [] for policy in POLICIES}
        all_results = []
        checksum = None
        for repeat in range(args.candidate_repeats):
            order = list(POLICIES)
            random.Random(seed * 137 + repeat * 29 + base + len(kind)).shuffle(order)
            for position, policy in enumerate(order):
                result = run_live(tasks, args.workers, forced_policy=policy)
                if checksum is None:
                    checksum = result["checksum"]
                if checksum != result["checksum"]:
                    raise AssertionError(f"checksum mismatch: {kind} {seed} {policy}")
                by_policy[policy].append(result["elapsed_s"])
                all_results.append((policy, repeat, position, result))
        medians = {policy: statistics.median(times) for policy, times in by_policy.items()}
        best = min(POLICIES, key=lambda policy: medians[policy])
        label = best if medians[best] < 0.97 * medians["fixed_4"] else "fixed_4"
        labels.append({"kind": kind, "seed": seed, "base": base, "prime_base": prime,
                       "label": label, **{f"{policy}_median_s": medians[policy] for policy in POLICIES}})
        for policy, repeat, position, result in all_results:
            raw.append({"split": split, "kind": kind, "seed": seed,
                        "base": base, "prime_base": prime, "repeat": repeat,
                        "order": position, "policy": policy, "label": label,
                        "elapsed_s": result["elapsed_s"], "checksum": result["checksum"],
                        "pilot_elapsed_s": result["pilot_elapsed_s"],
                        "decision_s": result["decision_s"],
                        **result["features"]})
        print(f"{split.upper()} {group_no:02}/{len(groups)} {kind:11} "
              f"base={base} seed={seed} label={label}", flush=True)
    return raw, labels


def train(args, output):
    if (output / "test_raw.csv").exists():
        raise RuntimeError("final test exists; training is frozen in this output folder")
    raw, labels = measured_candidates(args, "train", TRAIN_SCALES, args.train_seeds)
    csv_write(output / "train_raw.csv", raw)
    csv_write(output / "train_labels.csv", labels)
    config = {"status": "PASS", "workers": args.workers, "count": args.count,
              "train_scales": TRAIN_SCALES,
              "train_seeds": list(range(SEED_BASE["train"], SEED_BASE["train"] + args.train_seeds)),
              "candidate_repeats": args.candidate_repeats,
              "features": FEATURES, "policies": POLICIES, "label_margin": 0.03,
              "training_rows": len(raw), "training_groups": len(labels),
              "label_counts": dict(Counter(row["label"] for row in labels)),
              "label_definition": "lowest median full-invocation policy, if 3% below pilot-fixed; else pilot-fixed"}
    (output / "training_manifest.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("TRAIN COMPLETE", config["label_counts"], flush=True)


def fit_from_raw(raw, max_depth, min_leaf, feature_names=FEATURES):
    features = [[float(row[name]) for name in feature_names] for row in raw]
    labels = [row["label"] for row in raw]
    return DecisionTree(max_depth=max_depth, min_leaf=min_leaf).fit(features, labels)


def tune(args, output):
    if (output / "test_raw.csv").exists():
        raise RuntimeError("final test exists; refusing to retune model")
    train_manifest = json.loads((output / "training_manifest.json").read_text(encoding="utf-8"))
    if train_manifest["workers"] != args.workers or train_manifest["count"] != args.count:
        raise ValueError("training configuration mismatch")
    if (output / "validation_raw.csv").exists() and (output / "validation_labels.csv").exists() and not args.rerun_validation:
        raw = csv_read(output / "validation_raw.csv")
        labels = csv_read(output / "validation_labels.csv")
        print(f"REUSING {len(raw)} saved measured validation runs", flush=True)
    else:
        raw, labels = measured_candidates(args, "validation", (VALIDATION_SCALE,), args.validation_seeds)
        csv_write(output / "validation_raw.csv", raw)
        csv_write(output / "validation_labels.csv", labels)
    train_raw = csv_read(output / "train_raw.csv")
    groups = {}
    for row in raw:
        groups.setdefault((row["kind"], int(row["seed"])), []).append(row)
    for variant, feature_names, model_path, scores_path in (
        ("mixed", FEATURES, "model.json", "validation_model_scores.csv"),
        ("runtime_only", RUNTIME_FEATURES, "model_runtime_only.json", "validation_model_scores_runtime_only.csv"),
    ):
        scores = []
        models = {}
        for depth in (1, 2, 3, 4, 5, 6):
            for leaf in (4, 8, 12, 20):
                model = fit_from_raw(train_raw, depth, leaf, feature_names)
                regrets, exact = [], 0
                for label in labels:
                    sample = groups[(label["kind"], int(label["seed"]))]
                    # Median of repeated measured pilots reduces one-run noise.
                    feature_vector = [statistics.median(float(row[name]) for row in sample) for name in feature_names]
                    predicted = model.predict_one(feature_vector)
                    times = {policy: float(label[f"{policy}_median_s"]) for policy in POLICIES}
                    regrets.append(math.log(times[predicted] / min(times.values())))
                    exact += predicted == label["label"]
                score = statistics.mean(regrets)
                scores.append({"depth_cap": depth, "min_leaf": leaf,
                               "mean_log_regret": score, "exact_groups": exact,
                               "validation_groups": len(labels)})
                models[(depth, leaf)] = model
        csv_write(output / scores_path, scores)
        best_score = min(row["mean_log_regret"] for row in scores)
        near = [row for row in scores if row["mean_log_regret"] <= best_score + 0.005]
        chosen = min(near, key=lambda row: (row["depth_cap"], -row["min_leaf"]))
        model = models[(chosen["depth_cap"], chosen["min_leaf"])]
        artifact = {"tree": model.to_dict(), "features": feature_names, "policies": POLICIES,
                    "variant": variant, "chosen_hyperparameters": chosen,
                    "selection_rule": "lowest validation mean log regret; within 0.005 choose shallowest/largest leaf",
                    "train_seeds": train_manifest["train_seeds"],
                    "validation_seeds": list(range(SEED_BASE["validation"], SEED_BASE["validation"] + args.validation_seeds)),
                    "train_scales": TRAIN_SCALES, "validation_scale": VALIDATION_SCALE,
                    "workers": args.workers, "count": args.count,
                    "measurement_boundary": "32-task completed compiled-C pilot for two workers; full invocation labels"}
        (output / model_path).write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"{variant.upper()} MODEL SELECTED", chosen, flush=True)


def load_model(output):
    artifact = json.loads((output / "model.json").read_text(encoding="utf-8"))
    if artifact["features"] != list(FEATURES) or artifact["policies"] != list(POLICIES):
        raise ValueError("saved model feature/policy schema mismatch")
    return DecisionTree.from_dict(artifact["tree"]), artifact


class RuntimeProjection:
    """Project the live feature vector onto measured-only inputs for ablation."""

    def __init__(self, tree):
        self.tree = tree

    def predict_one(self, row):
        return self.tree.predict_one(row[:len(RUNTIME_FEATURES)])


def summarize(raw, kind, method):
    subset = [row for row in raw if row["kind"] == kind and row["method"] == method]
    baseline = {int(row["seed"]): float(row["elapsed_s"]) for row in raw
                if row["kind"] == kind and row["method"] == "fixed_no_pilot"}
    ratios = [float(row["elapsed_s"]) / baseline[int(row["seed"])] for row in subset]
    rng = random.Random(11981 + len(kind) * 131 + len(method))
    boots = sorted(statistics.median(rng.choices(ratios, k=len(ratios))) for _ in range(2000))
    return {"kind": kind, "method": method, "n": len(subset),
            "median_wall_s": statistics.median(float(row["elapsed_s"]) for row in subset),
            "median_paired_ratio": statistics.median(ratios),
            "mean_paired_ratio": statistics.mean(ratios),
            "paired_wins": sum(ratio < 1 for ratio in ratios),
            "bootstrap_median_95_low": boots[49], "bootstrap_median_95_high": boots[1949],
            "median_batch_p95_s": statistics.median(float(row["batch_p95_s"]) for row in subset),
            "median_startup_s": statistics.median(float(row["startup_s"]) for row in subset)}


def test(args, output):
    model, artifact = load_model(output)
    runtime_artifact = json.loads((output / "model_runtime_only.json").read_text(encoding="utf-8"))
    if runtime_artifact["features"] != list(RUNTIME_FEATURES):
        raise ValueError("runtime-only model schema mismatch")
    runtime_model = RuntimeProjection(DecisionTree.from_dict(runtime_artifact["tree"]))
    if artifact["workers"] != args.workers or artifact["count"] != args.count:
        raise ValueError("test configuration mismatch with saved model")
    groups = [(kind, SEED_BASE["test"] + j) for kind in KINDS_V6 for j in range(args.test_seeds)]
    random.Random(81921).shuffle(groups)
    raw = []
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = task_list(kind, args.count, *TEST_SCALE, seed)
        order = list(FINAL_METHODS)
        random.Random(seed * 311 + len(kind)).shuffle(order)
        checksum = None
        for position, method in enumerate(order):
            if method == "fixed_no_pilot":
                result = run_fixed(tasks, args.workers, "fixed_4")
            elif method == "cost32_no_pilot":
                result = run_balanced(tasks, args.workers, 32)
            elif method == "live_tree":
                result = run_live(tasks, args.workers, model=model)
            elif method == "live_tree_runtime_only":
                result = run_live(tasks, args.workers, model=runtime_model)
            else:
                result = run_live(tasks, args.workers, forced_policy=method.removeprefix("pilot_"))
            if checksum is None:
                checksum = result["checksum"]
            if result["checksum"] != checksum:
                raise AssertionError(f"checksum mismatch: {kind} {seed} {method}")
            raw.append({"kind": kind, "seed": seed, "base": TEST_SCALE[0], "prime_base": TEST_SCALE[1],
                        "order": position, "method": method, "selected_policy": result.get("policy", ""),
                        "elapsed_s": result["elapsed_s"], "checksum": result["checksum"],
                        "startup_s": result["startup_s"], "batch_p95_s": result["batch_latency_p95_s"],
                        "queue_wait_p95_s": result.get("queue_wait_p95_s", ""),
                        "service_p95_s": result.get("service_p95_s", ""),
                        "decision_s": result.get("decision_s", ""),
                        "pilot_elapsed_s": result.get("pilot_elapsed_s", ""),
                        **{name: result.get("features", {}).get(name, "") for name in FEATURES}})
        print(f"TEST {group_no:02}/{len(groups)} {kind:11} seed={seed}", flush=True)
    csv_write(output / "test_raw.csv", raw)
    summary = [summarize(raw, kind, method) for kind in KINDS_V6 for method in FINAL_METHODS]
    csv_write(output / "test_summary.csv", summary)
    manifest = {"status": "PASS", "system": platform.platform(), "workers": args.workers,
                "count": args.count, "test_scale": TEST_SCALE,
                "test_seeds": list(range(SEED_BASE["test"], SEED_BASE["test"] + args.test_seeds)),
                "train_seeds": artifact["train_seeds"], "validation_seeds": artifact["validation_seeds"],
                "groups": len(groups), "raw_rows": len(raw), "methods": FINAL_METHODS,
                "checksum_equality": True, "method_order": "seeded shuffle within each group",
                "timer": "complete invocation including live pilot, tree inference, planning, pool lifecycle; model fitting excluded",
                "primary_metric": "median paired whole-run ratio to fixed_no_pilot",
                "scope": "one WSL2 host; constructed workloads; exploratory"}
    (output / "test_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"PASS test: {len(groups)} groups, {len(raw)} timed runs, all checksums equal", flush=True)
    for row in summary:
        if row["method"] in ("live_tree", "live_tree_runtime_only"):
            print(f"{row['method'].upper()} {row['kind']:11} ratio={row['median_paired_ratio']:.3f} wins={row['paired_wins']}/{row['n']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("train", "tune", "test"))
    parser.add_argument("--output", type=Path, default=Path("results_live_v6"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--count", type=int, default=192)
    parser.add_argument("--train-seeds", type=int, default=4)
    parser.add_argument("--validation-seeds", type=int, default=3)
    parser.add_argument("--test-seeds", type=int, default=10)
    parser.add_argument("--candidate-repeats", type=int, default=2)
    parser.add_argument("--rerun-validation", action="store_true")
    args = parser.parse_args()
    if min(args.workers, args.count, args.train_seeds, args.validation_seeds, args.test_seeds, args.candidate_repeats) < 1:
        parser.error("all counts must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == "train":
        train(args, args.output)
    elif args.command == "tune":
        tune(args, args.output)
    else:
        test(args, args.output)


if __name__ == "__main__":
    main()
