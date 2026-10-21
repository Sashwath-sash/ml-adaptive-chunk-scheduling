"""Independently recompute training labels and held-out paired results."""
import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from .experiment_v7 import BASELINE, CANDIDATES, FEATURES, FINAL_METHODS, csv_read, feature_vector, task_list
from .tree import DecisionTree


def group_rows(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["kind"], row["seed"], row["base"])].append(row)
    return grouped


def check_measured_split(folder, split, repeats):
    raw = csv_read(folder / f"{split}_raw.csv")
    labels = csv_read(folder / f"{split}_groups.csv")
    grouped = group_rows(raw)
    assert len(grouped) == len(labels)
    for label in labels:
        group = grouped[(label["kind"], label["seed"], label["base"])]
        assert len(group) == len(CANDIDATES) * repeats
        assert {row["policy"] for row in group} == set(CANDIDATES)
        assert len({row["checksum"] for row in group}) == 1
        medians = {policy: statistics.median(float(row["elapsed_s"]) for row in group if row["policy"] == policy)
                   for policy in CANDIDATES}
        best = min(CANDIDATES, key=lambda policy: medians[policy])
        expected = best if medians[best] <= .98 * medians[BASELINE] else BASELINE
        assert label["label"] == expected
        for policy in CANDIDATES:
            assert math.isclose(float(label[f"time_{policy}"]), medians[policy], abs_tol=1e-12)
        tasks = task_list(label["kind"], 192, int(label["base"]), int(label["prime_base"]), int(label["seed"]))
        calculated = feature_vector(tasks, 2)
        for name, value in zip(FEATURES, calculated):
            assert math.isclose(float(label[name]), value, rel_tol=1e-12, abs_tol=1e-12)
    print(f"PASS {split}: {len(labels)} groups, {len(raw)} complete candidate runs; labels, features, checksums recomputed")
    return labels


def verify(folder, through):
    manifest = json.loads((folder / "train_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["features"] == list(FEATURES)
    assert manifest["candidates"] == list(CANDIDATES)
    assert manifest["workers"] == 2 and manifest["count"] == 192
    training = check_measured_split(folder, "train", manifest["candidate_repeats"])
    if through == "train":
        return
    validation = check_measured_split(folder, "validation", manifest["candidate_repeats"])
    scores = csv_read(folder / "validation_scores.csv")
    artifact = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    assert len(scores) == 25
    assert artifact["features"] == list(FEATURES)
    assert set(artifact["training_seeds"]).isdisjoint(artifact["validation_seeds"])
    assert artifact["training_groups"] == len(training)
    assert artifact["validation_groups"] == len(validation)
    model = DecisionTree.from_dict(artifact["model"])
    chosen = artifact["chosen"]
    corresponding = [row for row in scores if int(row["depth_cap"]) == chosen["depth_cap"]
                     and int(row["min_leaf"]) == chosen["min_leaf"]]
    assert len(corresponding) == 1
    regrets = []
    for row in validation:
        predicted = model.predict_one([float(row[name]) for name in FEATURES])
        times = [float(row[f"time_{policy}"]) for policy in CANDIDATES]
        regrets.append(math.log(float(row[f"time_{predicted}"]) / min(times)))
    assert math.isclose(statistics.mean(regrets), float(chosen["mean_log_regret"]), abs_tol=1e-12)
    print(f"PASS validation: 25 model sizes scored, saved model and selected score agree")
    if through == "validation":
        return
    raw = csv_read(folder / "test_raw.csv")
    summary = csv_read(folder / "test_summary.csv")
    test_manifest = json.loads((folder / "test_manifest.json").read_text(encoding="utf-8"))
    assert test_manifest["status"] == "PASS"
    assert test_manifest["timed_runs"] == len(raw)
    assert set(test_manifest["methods"]) == set(FINAL_METHODS)
    assert set(range(test_manifest["seed_base"], test_manifest["seed_base"] + test_manifest["test_seeds"])).isdisjoint(
        set(artifact["training_seeds"]) | set(artifact["validation_seeds"]))
    assert tuple(test_manifest["test_scale"]) not in [tuple(value) for value in artifact["train_scales"]]
    assert tuple(test_manifest["test_scale"]) != tuple(artifact["validation_scale"])
    grouped = defaultdict(list)
    for row in raw:
        grouped[(row["kind"], row["seed"])].append(row)
    assert len(grouped) == test_manifest["groups"]
    for (kind, seed), group in grouped.items():
        assert len(group) == len(FINAL_METHODS)
        assert {row["method"] for row in group} == set(FINAL_METHODS)
        assert len({row["checksum"] for row in group}) == 1
        assert len({row["order"] for row in group}) == len(group)
        learned = next(row for row in group if row["method"] == "learned")
        tasks = task_list(kind, 192, *test_manifest["test_scale"], int(seed))
        predicted = model.predict_one(feature_vector(tasks, 2))
        assert learned["selected_policy"] == predicted
        assert float(learned["inference_s"]) > 0
    assert len(summary) == len({row["kind"] for row in raw}) * len(FINAL_METHODS)
    for row in summary:
        subset = [item for item in raw if item["kind"] == row["kind"] and item["method"] == row["method"]]
        baselines = {item["seed"]: float(item["elapsed_s"]) for item in raw
                     if item["kind"] == row["kind"] and item["method"] == BASELINE}
        ratios = [float(item["elapsed_s"]) / baselines[item["seed"]] for item in subset]
        assert math.isclose(statistics.median(ratios), float(row["median_paired_ratio"]), abs_tol=1e-12)
        assert int(row["paired_wins"]) == sum(ratio < 1 for ratio in ratios)
    print(f"PASS held-out: {len(grouped)} matched groups, {len(raw)} complete timed runs, equal outputs, predictions and paired metrics independently recomputed")
    if (folder / "confirm_raw.csv").exists():
        verify_confirmation(folder, model, artifact, test_manifest)


def verify_confirmation(folder, model, artifact, test_manifest):
    raw = csv_read(folder / "confirm_raw.csv")
    summary = csv_read(folder / "confirm_summary.csv")
    manifest = json.loads((folder / "confirm_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS" and manifest["timed_runs"] == len(raw)
    confirm_seeds = set(range(manifest["seed_base"], manifest["seed_base"] + manifest["seeds_per_kind"]))
    assert confirm_seeds.isdisjoint(set(artifact["training_seeds"]) | set(artifact["validation_seeds"]))
    assert confirm_seeds.isdisjoint(set(range(test_manifest["seed_base"], test_manifest["seed_base"] + test_manifest["test_seeds"])))
    assert tuple(manifest["scale"]) != tuple(test_manifest["test_scale"])
    grouped = defaultdict(list)
    for row in raw:
        grouped[(row["kind"], row["seed"])].append(row)
    assert len(grouped) == manifest["groups"]
    for (kind, seed), group in grouped.items():
        assert {row["method"] for row in group} == set(manifest["methods"])
        assert len({row["checksum"] for row in group}) == 1
        assert len({row["order"] for row in group}) == len(group)
        learned = next(row for row in group if row["method"] == "learned")
        tasks = task_list(kind, 192, *manifest["scale"], int(seed))
        assert learned["selected_policy"] == model.predict_one(feature_vector(tasks, 2))
    for row in summary:
        subset = [item for item in raw if item["kind"] == row["kind"]]
        times = {(item["seed"], item["method"]): float(item["elapsed_s"]) for item in subset}
        ratios = [times[(str(seed), row["method"])] / times[(str(seed), row["baseline"])] for seed in confirm_seeds]
        assert int(row["n"]) == len(ratios)
        assert math.isclose(float(row["median_paired_ratio"]), statistics.median(ratios), abs_tol=1e-12)
        assert int(row["paired_wins"]) == sum(value < 1 for value in ratios)
    print(f"PASS confirmation: {len(grouped)} new groups, {len(raw)} timed runs; scale, seeds, outputs, predictions and ratios audited")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results_learned_v7"))
    parser.add_argument("--through", choices=("train", "validation", "test"), default="test")
    args = parser.parse_args()
    verify(args.output, args.through)


if __name__ == "__main__":
    main()
