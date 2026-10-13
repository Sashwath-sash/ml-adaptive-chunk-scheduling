"""Audit the saved paired Review 2 benchmark without rerunning timings."""
import csv
import json
import statistics
from pathlib import Path


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    folder = Path(__file__).resolve().parents[1] / "results_paired_both_review"
    raw = rows(folder / "raw.csv")
    summary = rows(folder / "summary.csv")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert len(raw) == manifest["raw_rows"] == 105
    assert len(summary) == 18
    groups = {}
    for row in raw:
        groups.setdefault((row["workload"], int(row["seed"])), []).append(row)
    assert len(groups) == 35
    assert all({r["method"] for r in rs} == {"fixed_4", "ml", "balanced_32"}
               and len({r["checksum"] for r in rs}) == 1
               and len({int(r["order"]) for r in rs}) == 3
               for rs in groups.values())
    assert set(manifest["general_seeds"]).isdisjoint(manifest["late_heavy_seeds"])
    for row in summary:
        kind, method = row["workload"], row["method"]
        matching = [r for r in raw if r["workload"] == kind and r["method"] == method]
        baseline = {int(r["seed"]): float(r["elapsed_s"]) for r in raw
                    if r["workload"] == kind and r["method"] == "fixed_4"}
        assert int(row["runs"]) == len(matching)
        wall = statistics.median(float(r["elapsed_s"]) for r in matching)
        ratio = statistics.median(float(r["elapsed_s"]) / baseline[int(r["seed"])] for r in matching)
        assert abs(wall - float(row["median_wall_s"])) < 1e-9
        assert abs(ratio - float(row["median_paired_ratio"])) < 1e-9
    print("PASS  12-column raw data and 18 summary rows audited")
    print("PASS  35 paired input groups / 105 method runs")
    print("PASS  all three checksums equal within every group")
    print("PASS  summary wall times and paired ratios recomputed")
    print()
    print("Median paired wall-time ratio to fixed chunk 4 (lower is better)")
    print(f"{'workload':14} {'n':>2} {'tree':>8} {'balanced':>9}")
    for kind in ("uniform", "moderate", "high", "phase_shift", "prime_scan", "late_heavy"):
        matches = {r["method"]: r for r in summary if r["workload"] == kind}
        print(f"{kind:14} {matches['fixed_4']['runs']:>2} "
              f"{float(matches['ml']['median_paired_ratio']):8.3f} "
              f"{float(matches['balanced_32']['median_paired_ratio']):9.3f}")


if __name__ == "__main__":
    main()
