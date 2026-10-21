"""Independent checks of measured training labels and held-out v6 comparisons."""
import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from .experiment_v6 import FINAL_METHODS, POLICIES, RUNTIME_FEATURES, csv_read
from .scheduler_v6 import FEATURES


def verify_training(folder):
    manifest = json.loads((folder / "training_manifest.json").read_text(encoding="utf-8"))
    raw = csv_read(folder / "train_raw.csv")
    labels = csv_read(folder / "train_labels.csv")
    assert manifest["status"] == "PASS"
    assert manifest["features"] == list(FEATURES)
    assert len(raw) == manifest["training_rows"]
    assert len(labels) == manifest["training_groups"]
    assert len({(r["kind"], r["seed"], r["base"]) for r in labels}) == len(labels)
    for row in raw:
        assert row["policy"] in POLICIES
        assert float(row["pilot_mean_task_s"]) > 0
        assert float(row["pilot_throughput_tps"]) > 0
        assert float(row["pilot_queue_wait_p95_s"]) >= 0
        assert float(row["elapsed_s"]) > float(row["pilot_elapsed_s"]) > 0
    groups = defaultdict(list)
    for row in raw:
        groups[(row["kind"], row["seed"], row["base"])].append(row)
    for label in labels:
        group = groups[(label["kind"], label["seed"], label["base"])]
        assert len({row["checksum"] for row in group}) == 1
        assert {row["policy"] for row in group} == set(POLICIES)
        medians = {policy: statistics.median(float(row["elapsed_s"]) for row in group if row["policy"] == policy)
                   for policy in POLICIES}
        for policy in POLICIES:
            assert math.isclose(float(label[f"{policy}_median_s"]), medians[policy], abs_tol=1e-12)
        best = min(POLICIES, key=lambda policy: medians[policy])
        expected = best if medians[best] < 0.97 * medians["fixed_4"] else "fixed_4"
        assert label["label"] == expected
    print(f"PASS training: {len(labels)} groups, {len(raw)} measured candidate runs, labels recomputed")
    return manifest


def verify_validation(folder, training):
    raw = csv_read(folder / "validation_raw.csv")
    labels = csv_read(folder / "validation_labels.csv")
    model = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    runtime_model = json.loads((folder / "model_runtime_only.json").read_text(encoding="utf-8"))
    scores = csv_read(folder / "validation_model_scores.csv")
    runtime_scores = csv_read(folder / "validation_model_scores_runtime_only.csv")
    assert model["features"] == list(FEATURES)
    assert runtime_model["features"] == list(RUNTIME_FEATURES)
    assert set(model["validation_seeds"]).isdisjoint(training["train_seeds"])
    assert runtime_model["train_seeds"] == model["train_seeds"]
    assert runtime_model["validation_seeds"] == model["validation_seeds"]
    assert len(scores) == 24
    assert len(runtime_scores) == 24
    assert len(raw) == len(labels) * len(POLICIES) * training["candidate_repeats"]
    assert {(r["seed"], r["base"]) for r in labels}.isdisjoint(
        {(str(s), str(scale[0])) for s in training["train_seeds"] for scale in training["train_scales"]})
    print(f"PASS validation: {len(labels)} groups, {len(scores)} complexity choices, disjoint scale and seeds")
    return model


def verify_test(folder, model):
    raw = csv_read(folder / "test_raw.csv")
    summary = csv_read(folder / "test_summary.csv")
    manifest = json.loads((folder / "test_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS" and len(raw) == manifest["raw_rows"]
    assert set(manifest["test_seeds"]).isdisjoint(model["train_seeds"])
    assert set(manifest["test_seeds"]).isdisjoint(model["validation_seeds"])
    assert tuple(manifest["methods"]) == FINAL_METHODS
    groups = defaultdict(list)
    for row in raw:
        groups[(row["kind"], int(row["seed"]))].append(row)
        if row["method"] in ("live_tree", "live_tree_runtime_only"):
            assert row["selected_policy"] in POLICIES
            assert float(row["pilot_elapsed_s"]) > 0
            assert float(row["pilot_mean_task_s"]) > 0
    assert len(groups) == manifest["groups"]
    for group in groups.values():
        assert {row["method"] for row in group} == set(FINAL_METHODS)
        assert len({row["checksum"] for row in group}) == 1
        assert len({int(row["order"]) for row in group}) == len(group)
    assert len(summary) == len({row["kind"] for row in raw}) * len(FINAL_METHODS)
    for row in summary:
        subset = [r for r in raw if r["kind"] == row["kind"] and r["method"] == row["method"]]
        baseline = {int(r["seed"]): float(r["elapsed_s"]) for r in raw
                    if r["kind"] == row["kind"] and r["method"] == "fixed_no_pilot"}
        ratios = [float(r["elapsed_s"]) / baseline[int(r["seed"])] for r in subset]
        assert int(row["n"]) == len(subset)
        assert math.isclose(statistics.median(ratios), float(row["median_paired_ratio"]), abs_tol=1e-12)
        assert math.isclose(statistics.mean(ratios), float(row["mean_paired_ratio"]), abs_tol=1e-12)
        assert int(row["paired_wins"]) == sum(value < 1 for value in ratios)
    print(f"PASS test: {len(groups)} matched groups, {len(raw)} timed runs, equal checksums")
    print("PASS complete-run paired metrics recomputed; all splits disjoint")
    for row in summary:
        if row["method"] == "live_tree":
            print(f"{row['kind']:11} ratio={float(row['median_paired_ratio']):.3f} "
                  f"wins={row['paired_wins']}/{row['n']} "
                  f"bootstrap95=[{float(row['bootstrap_median_95_low']):.3f}, "
                  f"{float(row['bootstrap_median_95_high']):.3f}]")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results_live_v6"))
    parser.add_argument("--through", choices=("train", "validation", "test"), default="test")
    args = parser.parse_args()
    training = verify_training(args.output)
    if args.through == "train":
        return
    model = verify_validation(args.output, training)
    if args.through == "test":
        verify_test(args.output, model)


if __name__ == "__main__":
    main()
