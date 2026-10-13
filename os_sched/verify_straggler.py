"""Audit paired tail-straggler evaluation and its saved task inputs."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def load(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args()
    folder = args.folder
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    raw, summary, dataset = (load(folder / name) for name in ("raw.csv", "summary.csv", "dataset.csv"))
    assert len(raw) == manifest["repeats"] * len(manifest["methods"])
    assert len(summary) == len(manifest["methods"])
    assert len(dataset) == manifest["repeats"] * manifest["count"]
    pairs, task_groups = defaultdict(list), defaultdict(list)
    for row in raw:
        pairs[int(row["seed"])].append(row)
        assert float(row["elapsed_s"]) > 0
    for row in dataset:
        task_groups[int(row["seed"])].append(row)
    assert set(pairs) == set(range(manifest["seed_start"], manifest["seed_start"] + manifest["repeats"]))
    for seed, rows in pairs.items():
        assert {r["method"] for r in rows} == set(manifest["methods"]), seed
        assert len({r["checksum"] for r in rows}) == 1, seed
        assert sorted(int(r["order"]) for r in rows) == list(range(len(rows))), seed
        assert len(task_groups[seed]) == manifest["count"]
        spikes = [r for r in task_groups[seed] if r["is_spike"] == "True"]
        assert len(spikes) == 1 and int(spikes[0]["task_index"]) >= manifest["count"] - 8
    for row in summary:
        values = [float(r["elapsed_s"]) for r in raw if r["method"] == row["method"]]
        assert len(values) == int(row["runs"])
        assert math.isclose(statistics.median(values), float(row["median_s"]), rel_tol=1e-10)
    selected = next(r for r in summary if r["method"] == "balanced_32")
    root = Path(__file__).resolve().parents[1]
    files = [root / "STRAGGLER_TEST_PLAN.md", root / "TIMING_CORRECTION_PLAN.md",
             root / "os_sched/straggler_workload.py",
             root / "os_sched/scheduler_v4.py", root / "os_sched/experiment_straggler.py",
             folder / "dataset.csv", folder / "raw.csv", folder / "summary.csv"]
    report = {"status": "PASS", "raw_rows": len(raw), "dataset_rows": len(dataset),
              "paired_groups": len(pairs), "checksums_equal": True,
              "one_late_spike_per_group": True, "summary_medians_recomputed": True,
              "selected_method": "balanced_32",
              "selected_median_paired_ratio_to_fixed4": float(selected["median_ratio_to_paired_fixed4"]),
              "selected_beats_fixed4": float(selected["median_ratio_to_paired_fixed4"]) < 1,
              "source_and_data_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (folder / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
