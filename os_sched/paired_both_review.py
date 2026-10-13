"""Fresh paired fixed/tree/balanced measurements for Review 2 explanation.

Declared methods and seeds are intentionally fixed before execution. This is
an application-level Linux process-pool comparison, not a kernel benchmark.
"""
import csv
import json
import platform
import random
import statistics
from pathlib import Path

from .experiment_complete import KINDS, make_tasks
from .scheduler_v2 import run
from .scheduler_v4 import run_balanced
from .straggler_workload import generate_tail_spike
from .tree import DecisionTree


METHODS = ("fixed_4", "ml", "balanced_32")


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "results_paired_both_review"
    output.mkdir(exist_ok=True)
    model = DecisionTree.from_dict(json.loads((root / "results_final_linux" / "model.json").read_text(encoding="utf-8")))
    groups = [(kind, 7001 + i) for kind in KINDS for i in range(5)]
    groups += [("late_heavy", 11001 + i) for i in range(10)]
    random.Random(744731).shuffle(groups)
    raw = []
    for kind, seed in groups:
        if kind == "late_heavy":
            tasks, heavy_index = generate_tail_spike(192, 1_500_000, seed, 40)
        else:
            tasks = make_tasks(kind, 192, 1_500_000, 3000, seed)
            heavy_index = ""
        order = list(METHODS)
        random.Random(seed * 41).shuffle(order)
        checksum = None
        for position, method in enumerate(order):
            if method == "balanced_32":
                result = run_balanced(tasks, 2, 32)
            else:
                result = run(tasks, 2, method, model if method == "ml" else None)
            if checksum is None:
                checksum = result["checksum"]
            assert checksum == result["checksum"], (kind, seed, method)
            raw.append({"workload": kind, "seed": seed, "heavy_index": heavy_index,
                        "order": position, "method": method,
                        "elapsed_s": result["elapsed_s"], "checksum": checksum,
                        "batch_p95_s": result["batch_latency_p95_s"],
                        "queue_wait_p95_s": result.get("queue_wait_p95_s", ""),
                        "service_p95_s": result.get("service_p95_s", ""),
                        "decision_p95_s": result.get("decision_p95_s", ""),
                        "startup_s": result["startup_s"]})
        print(f"PAIRED {kind} seed={seed}", flush=True)
    write_csv(output / "raw.csv", raw)
    summary = []
    for kind in (*KINDS, "late_heavy"):
        baseline = {r["seed"]: r["elapsed_s"] for r in raw if r["workload"] == kind and r["method"] == "fixed_4"}
        for method in METHODS:
            rows = [r for r in raw if r["workload"] == kind and r["method"] == method]
            summary.append({"workload": kind, "method": method, "runs": len(rows),
                            "median_wall_s": statistics.median(r["elapsed_s"] for r in rows),
                            "median_paired_ratio": statistics.median(r["elapsed_s"] / baseline[r["seed"]] for r in rows),
                            "median_batch_p95_s": statistics.median(r["batch_p95_s"] for r in rows),
                            "median_startup_s": statistics.median(r["startup_s"] for r in rows)})
    write_csv(output / "summary.csv", summary)
    (output / "manifest.json").write_text(json.dumps({
        "status": "PASS", "system": platform.platform(), "workers": 2,
        "task_count": 192, "general_seeds": [7001, 7002, 7003, 7004, 7005],
        "late_heavy_seeds": list(range(11001, 11011)), "heavy_factor": 40,
        "methods": METHODS, "raw_rows": len(raw), "all_checksums_equal_within_groups": True,
        "timing": "end-to-end, including planning, pool startup, dispatch and teardown; model training excluded",
        "method_order": "seeded shuffle within every group",
        "primary_metric": "median within-seed wall-time ratio to fixed_4",
        "scope": "one WSL2 machine; exploratory, not universal speedup"
    }, indent=2), encoding="utf-8")
    print(f"PASS: {len(groups)} paired groups, {len(raw)} timed method runs", flush=True)


if __name__ == "__main__":
    main()
