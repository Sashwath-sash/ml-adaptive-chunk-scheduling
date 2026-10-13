"""Audit an experiment directory without rerunning or changing measurements."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def load_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    raw = load_csv(folder / "raw_results.csv")
    summaries = load_csv(folder / "summary.csv")
    training = load_csv(folder / "training_data.csv")
    decisions = load_csv(folder / "decisions.csv")
    dataset = load_csv(folder / "dataset.csv")
    expected_raw = len(manifest["workloads"]) * manifest["repeats"] * len(manifest["methods"])
    expected_summary = len(manifest["workloads"]) * len(manifest["methods"])
    expected_dataset = len(manifest["workloads"]) * manifest["repeats"] * manifest["task_count"]
    assert len(raw) == expected_raw, (len(raw), expected_raw)
    assert len(summaries) == expected_summary, (len(summaries), expected_summary)
    assert len(dataset) == expected_dataset, (len(dataset), expected_dataset)
    assert len(training) == (manifest["training"]["training_rows"] + manifest["training"]["holdout_rows"])
    assert set(manifest["training"]["train_seeds"]).isdisjoint(manifest["training"]["holdout_seeds"])
    assert set(manifest["training"]["train_seeds"]).isdisjoint({int(r["seed"]) for r in raw})
    assert set(manifest["training"]["holdout_seeds"]).isdisjoint({int(r["seed"]) for r in raw})
    groups = defaultdict(list)
    for row in raw:
        groups[(row["workload"], int(row["repeat"]))].append(row)
        assert float(row["elapsed_s"]) > 0
        assert float(row["batch_latency_p95_s"]) >= 0
        assert float(row["decision_p95_s"]) >= 0
    for key, rows in groups.items():
        assert len(rows) == len(manifest["methods"]), key
        assert {r["method"] for r in rows} == set(manifest["methods"]), key
        assert len({r["checksum"] for r in rows}) == 1, key
        assert sorted(int(r["method_order"]) for r in rows) == list(range(len(rows))), key
    decision_groups = defaultdict(list)
    for event in decisions:
        decision_groups[(event["workload"], int(event["repeat"]), event["method"])].append(event)
        assert 1 <= int(event["new_chunk"]) <= 64
    for row in raw:
        key = (row["workload"], int(row["repeat"]), row["method"])
        events = decision_groups[key]
        assert len(events) == int(row["decisions"]), key
        if events:
            assert sum(int(e["tasks_completed"]) for e in events) == int(row["tasks"]), key
    for row in summaries:
        values = [float(r["elapsed_s"]) for r in raw if r["workload"] == row["workload"] and r["method"] == row["method"]]
        assert len(values) == int(row["runs"])
        assert math.isclose(statistics.median(values), float(row["median_elapsed_s"]), rel_tol=1e-10)
    comparison_rows = 0
    if (folder / "existing_options_raw.csv").exists():
        options = load_csv(folder / "existing_options_raw.csv")
        option_summaries = load_csv(folder / "existing_options_summary.csv")
        option_groups = defaultdict(list)
        for row in options:
            option_groups[(row["workload"], int(row["repeat"]))].append(row)
        expected_methods = {r["method"] for r in option_summaries}
        assert len(option_groups) == len(groups)
        for key, rows in option_groups.items():
            assert len(rows) == len(expected_methods), key
            assert {r["method"] for r in rows} == expected_methods, key
            assert len({r["checksum"] for r in rows}) == 1, key
        for row in option_summaries:
            values = [float(r["elapsed_s"]) for r in options if r["workload"] == row["workload"] and r["method"] == row["method"]]
            assert len(values) == int(row["runs"])
            assert math.isclose(statistics.median(values), float(row["median_elapsed_s"]), rel_tol=1e-10)
        comparison_rows = len(options)
    root = Path(__file__).resolve().parents[1]
    evidence_paths = [root / "native/work_kernel.c", root / "os_sched/workload.py",
                      root / "os_sched/tree.py", root / "os_sched/scheduler_v2.py",
                      root / "os_sched/experiment_complete.py", folder / "model.json",
                      folder / "raw_results.csv", folder / "summary.csv"]
    if comparison_rows:
        evidence_paths.extend([root / "os_sched/compare_existing.py",
                               folder / "existing_options_raw.csv",
                               folder / "existing_options_summary.csv"])
    sha256 = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in evidence_paths}
    report = {"status": "PASS", "raw_rows": len(raw), "summary_rows": len(summaries),
              "training_rows": len(training), "decision_rows": len(decisions),
              "dataset_rows": len(dataset), "paired_groups": len(groups),
              "all_checksum_groups_equal": True,
              "train_holdout_test_seeds_disjoint": True,
              "summary_medians_recomputed": True,
              "decision_counts_and_task_coverage_valid": True,
              "existing_options_rows": comparison_rows,
              "existing_options_checksums_and_medians_valid": comparison_rows > 0,
              "source_and_result_sha256": sha256}
    (folder / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args()
    print(json.dumps(verify(args.folder), indent=2))


if __name__ == "__main__":
    main()
