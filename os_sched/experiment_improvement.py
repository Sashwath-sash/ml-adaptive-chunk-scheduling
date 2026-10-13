"""Paired Linux comparison of one-decision tree against old tree and baselines."""
import argparse
import csv
import json
import platform
import random
import statistics
from pathlib import Path

from .compare_existing import builtin
from .experiment_complete import KINDS, make_tasks, write_csv
from .scheduler_v2 import run
from .scheduler_v3 import run_once
from .tree import DecisionTree

METHODS = ("fixed_4", "fixed_16", "ml", "guarded_ml", "ml_once",
           "pool_map_16", "process_executor_16")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, default=Path("results_final_linux/model.json"))
    ap.add_argument("--output", type=Path, default=Path("results_improvement"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--base", type=int, default=1_500_000)
    ap.add_argument("--prime-base", type=int, default=3000)
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()
    if args.workers < 1 or args.count < 16 or args.repeats < 1:
        ap.error("workers/repeats must be positive; count >= 16")
    model = DecisionTree.from_dict(json.loads(args.model.read_text(encoding="utf-8")))
    args.output.mkdir(parents=True, exist_ok=True)
    raw, decisions = [], []
    groups = [(kind, repeat) for kind in KINDS for repeat in range(args.repeats)]
    random.Random(28711).shuffle(groups)
    for kind, repeat in groups:
        seed = 1001 + repeat
        tasks = make_tasks(kind, args.count, args.base, args.prime_base, seed)
        # Warm-up is untimed; all methods then see the same inputs.
        run(tasks[:16], args.workers, "fixed_4")
        order = list(METHODS)
        random.Random(seed * 113 + len(kind)).shuffle(order)
        checksum = None
        for position, method in enumerate(order):
            if method == "ml_once":
                result = run_once(tasks, args.workers, model)
            elif method.startswith(("pool_map_", "process_executor_")):
                result = builtin(tasks, args.workers, method)
            else:
                result = run(tasks, args.workers, method, model)
            if checksum is None:
                checksum = result["checksum"]
            assert result["checksum"] == checksum, (kind, repeat, method)
            raw.append({"workload": kind, "repeat": repeat + 1, "seed": seed,
                        "order": position, "method": method,
                        "elapsed_s": result["elapsed_s"], "checksum": result["checksum"],
                        "decisions": len(result.get("decisions", [])),
                        "decision_p95_s": result.get("decision_p95_s", 0),
                        "batch_latency_p95_s": result.get("batch_latency_p95_s", 0)})
            decisions.extend({"workload": kind, "repeat": repeat + 1, "seed": seed,
                              "method": method, **event}
                             for event in result.get("decisions", []))
        print(f"PAIRED {kind:11s} repeat={repeat + 1} methods={len(METHODS)}", flush=True)
    write_csv(args.output / "raw.csv", raw)
    write_csv(args.output / "decisions.csv", decisions)
    summary = []
    for kind in KINDS:
        fixed = {int(r["repeat"]): float(r["elapsed_s"]) for r in raw
                 if r["workload"] == kind and r["method"] == "fixed_4"}
        old = {int(r["repeat"]): float(r["elapsed_s"]) for r in raw
               if r["workload"] == kind and r["method"] == "ml"}
        for method in METHODS:
            rows = [r for r in raw if r["workload"] == kind and r["method"] == method]
            values = [r["elapsed_s"] for r in rows]
            summary.append({"workload": kind, "method": method, "runs": len(rows),
                            "median_s": statistics.median(values),
                            "min_s": min(values), "max_s": max(values),
                            "median_ratio_to_paired_fixed4": statistics.median(r["elapsed_s"] / fixed[r["repeat"]] for r in rows),
                            "median_ratio_to_paired_old_tree": statistics.median(r["elapsed_s"] / old[r["repeat"]] for r in rows),
                            "median_decision_p95_s": statistics.median(r["decision_p95_s"] for r in rows)})
    write_csv(args.output / "summary.csv", summary)
    report = {"status": "PASS", "system": platform.platform(), "workers": args.workers,
              "count": args.count, "repeats": args.repeats, "workloads": KINDS,
              "methods": METHODS, "raw_rows": len(raw), "summary_rows": len(summary),
              "decision_rows": len(decisions), "all_group_checksums_equal": True,
              "model": str(args.model), "base": args.base, "prime_base": args.prime_base,
              "timing_boundary": "total wall time including pool startup, dispatch, inference and teardown",
              "randomization": "workload/repeat groups and method order seeded and shuffled",
              "scope": "same held-out task seeds; one Linux host; exploratory paired runs"}
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert len(raw) == len(KINDS) * args.repeats * len(METHODS)
    print(f"DONE {len(raw)} paired runs; checksums match", flush=True)


if __name__ == "__main__":
    main()
