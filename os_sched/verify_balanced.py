"""Audit development and fresh-test balanced batching experiments."""
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


def verify(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    raw, summary = load(folder / "raw.csv"), load(folder / "summary.csv")
    expected_groups = len(manifest["workloads"]) * manifest["repeats"]
    assert len(raw) == expected_groups * len(manifest["methods"])
    assert len(summary) == len(manifest["workloads"]) * len(manifest["methods"])
    groups = defaultdict(list)
    for row in raw:
        groups[(row["workload"], int(row["repeat"]))].append(row)
        assert float(row["elapsed_s"]) > 0
    assert len(groups) == expected_groups
    for key, rows in groups.items():
        assert {r["method"] for r in rows} == set(manifest["methods"]), key
        assert len({r["checksum"] for r in rows}) == 1, key
        assert sorted(int(r["order"]) for r in rows) == list(range(len(rows))), key
        assert all(int(r["seed"]) == manifest["seed_start"] + key[1] - 1 for r in rows), key
    for row in summary:
        values = [float(r["elapsed_s"]) for r in raw
                  if r["workload"] == row["workload"] and r["method"] == row["method"]]
        assert len(values) == int(row["runs"])
        assert math.isclose(statistics.median(values), float(row["median_s"]), rel_tol=1e-10)
    selected = [float(row["median_ratio_to_paired_fixed4"]) for row in summary
                if row["method"] == "balanced_fifo_16"]
    assert len(selected) == len(manifest["workloads"])
    geo = math.prod(selected) ** (1 / len(selected))
    root = Path(__file__).resolve().parents[1]
    files = [root / "os_sched/scheduler_v4.py", root / "os_sched/experiment_balanced.py",
             root / "BALANCED_SELECTION.md", root / "TIMING_CORRECTION_PLAN.md",
             folder / "raw.csv", folder / "summary.csv"]
    report = {"status": "PASS", "raw_rows": len(raw), "summary_rows": len(summary),
              "paired_groups": len(groups), "checksums_equal": True,
              "summary_medians_recomputed": True,
              "selected_method": "balanced_fifo_16",
              "selected_geomean_paired_ratio_to_fixed4": geo,
              "selected_beats_fixed4_geomean": geo < 1,
              "source_and_data_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (folder / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args()
    print(json.dumps(verify(args.folder), indent=2))


if __name__ == "__main__":
    main()
