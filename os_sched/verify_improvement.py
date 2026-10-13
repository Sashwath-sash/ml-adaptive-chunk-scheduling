"""Audit saved improvement benchmark against raw paired measurements."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args()
    folder = args.folder
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    raw, summary, decisions = (rows(folder / name) for name in
                               ("raw.csv", "summary.csv", "decisions.csv"))
    assert len(raw) == len(manifest["workloads"]) * manifest["repeats"] * len(manifest["methods"])
    assert len(summary) == len(manifest["workloads"]) * len(manifest["methods"])
    groups = defaultdict(list)
    for row in raw:
        groups[(row["workload"], int(row["repeat"]))].append(row)
        assert float(row["elapsed_s"]) > 0
    assert len(groups) == len(manifest["workloads"]) * manifest["repeats"]
    for key, group in groups.items():
        assert {r["method"] for r in group} == set(manifest["methods"]), key
        assert len({r["checksum"] for r in group}) == 1, key
        assert sorted(int(r["order"]) for r in group) == list(range(len(group))), key
        assert all(int(r["seed"]) == 1000 + int(r["repeat"]) for r in group), key
    events = defaultdict(list)
    for row in decisions:
        events[(row["workload"], int(row["repeat"]), row["method"])].append(row)
    for row in raw:
        key = (row["workload"], int(row["repeat"]), row["method"])
        assert len(events[key]) == int(row["decisions"]), key
        if row["method"] == "ml_once":
            assert len(events[key]) == 1 and events[key][0]["reason"] == "tree_once", key
    for row in summary:
        values = [float(r["elapsed_s"]) for r in raw
                  if r["workload"] == row["workload"] and r["method"] == row["method"]]
        assert len(values) == int(row["runs"])
        assert math.isclose(statistics.median(values), float(row["median_s"]), rel_tol=1e-10)
    root = Path(__file__).resolve().parents[1]
    files = [root / "os_sched/scheduler_v2.py", root / "os_sched/scheduler_v3.py",
             root / "os_sched/experiment_improvement.py",
             root / "results_final_linux/model.json", folder / "raw.csv", folder / "summary.csv"]
    report = {"status": "PASS", "raw_rows": len(raw), "summary_rows": len(summary),
              "decision_rows": len(decisions), "paired_groups": len(groups),
              "checksums_equal": True, "one_decision_per_ml_once_run": True,
              "summary_medians_recomputed": True,
              "source_and_data_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (folder / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
