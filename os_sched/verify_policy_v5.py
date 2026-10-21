"""Independently audit saved v5 train/validation/test files without rerunning work."""
import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from .scheduler_v5 import POLICIES


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify(folder, split):
    trained = json.loads((folder / "selector.json").read_text(encoding="utf-8"))
    train = csv_rows(folder / "train_labels.csv")
    assert len(train) == len({(row["kind"], row["seed"]) for row in train})
    assert {int(row["seed"]) for row in train} == set(trained["train_seeds"])
    assert {row["label"] for row in train} <= set(POLICIES)
    raw = csv_rows(folder / f"{split}_raw.csv")
    summary = csv_rows(folder / f"{split}_summary.csv")
    manifest = json.loads((folder / f"{split}_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS" and manifest["split"] == split
    assert len(raw) == manifest["raw_rows"]
    assert len(summary) == len(manifest["kinds"]) * len(manifest["methods"])
    assert set(manifest["seeds"]).isdisjoint(trained["train_seeds"])
    if split == "test" and (folder / "validation_manifest.json").exists():
        validation = json.loads((folder / "validation_manifest.json").read_text(encoding="utf-8"))
        assert set(manifest["seeds"]).isdisjoint(validation["seeds"])
    groups = defaultdict(list)
    for row in raw:
        groups[(row["kind"], int(row["seed"]))].append(row)
        assert float(row["elapsed_s"]) > 0
        assert float(row["startup_s"]) >= 0
        if row["method"] == "auto":
            assert row["selected_policy"] in POLICIES
            assert float(row["feature_s"]) >= 0 and float(row["selection_s"]) >= 0
    assert len(groups) == manifest["groups"]
    for rows in groups.values():
        assert {row["method"] for row in rows} == set(manifest["methods"])
        assert len({row["checksum"] for row in rows}) == 1
        assert len({int(row["order"]) for row in rows}) == len(rows)
    for row in summary:
        matches = [item for item in raw if item["kind"] == row["kind"] and item["method"] == row["method"]]
        baselines = {int(item["seed"]): float(item["elapsed_s"]) for item in raw if item["kind"] == row["kind"] and item["method"] == "fixed_4"}
        ratios = [float(item["elapsed_s"]) / baselines[int(item["seed"])] for item in matches]
        assert len(matches) == int(row["n"])
        assert math.isclose(statistics.median(ratios), float(row["median_paired_ratio"]), abs_tol=1e-12)
        assert math.isclose(statistics.mean(ratios), float(row["mean_paired_ratio"]), abs_tol=1e-12)
        assert sum(value < 1 for value in ratios) == int(row["paired_wins"])
        assert math.isclose(statistics.median(float(item["elapsed_s"]) for item in matches), float(row["median_wall_s"]), abs_tol=1e-12)
    print(f"PASS {split}: {len(groups)} matched groups, {len(raw)} runs, equal checksums")
    print("PASS disjoint seeds, methods, full-wall ratios and summaries recomputed")
    for row in summary:
        if row["method"] == "auto":
            print(f"{row['kind']:11} ratio={float(row['median_paired_ratio']):.3f} "
                  f"wins={row['paired_wins']}/{row['n']} "
                  f"bootstrap95=[{float(row['median_ratio_bootstrap_95_low']):.3f}, "
                  f"{float(row['median_ratio_bootstrap_95_high']):.3f}]")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("validation", "test"))
    parser.add_argument("--output", type=Path, default=Path("results_policy_v5"))
    args = parser.parse_args()
    verify(args.output, args.split)


if __name__ == "__main__":
    main()
