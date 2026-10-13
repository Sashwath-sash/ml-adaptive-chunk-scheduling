"""Paired train/test evaluation for estimated-cost balanced dispatch."""
import argparse
import json
import platform
import random
import statistics
from pathlib import Path

from .compare_existing import builtin
from .experiment_complete import KINDS, make_tasks, write_csv
from .scheduler_v2 import run
from .scheduler_v4 import run_balanced

METHODS = ("fixed_4", "fixed_16", "pool_map_16", "balanced_8", "balanced_16",
           "balanced_32", "balanced_fifo_16")


def execute(method, tasks, workers):
    if method.startswith("fixed_"):
        return run(tasks, workers, method)
    if method == "pool_map_16":
        return builtin(tasks, workers, method)
    if method == "balanced_fifo_16":
        return run_balanced(tasks, workers, 16, longest_first=False)
    return run_balanced(tasks, workers, int(method.rsplit("_", 1)[1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--seed-start", type=int, required=True)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--base", type=int, default=1_500_000)
    ap.add_argument("--prime-base", type=int, default=3000)
    ap.add_argument("--count", type=int, default=192)
    args = ap.parse_args()
    if min(args.seed_start, args.repeats, args.workers, args.base, args.prime_base) < 1 or args.count < 32:
        ap.error("positive settings and count >= 32 required")
    args.output.mkdir(parents=True, exist_ok=True)
    raw = []
    groups = [(kind, repeat) for kind in KINDS for repeat in range(args.repeats)]
    random.Random(args.seed_start * 17).shuffle(groups)
    for kind, repeat in groups:
        seed = args.seed_start + repeat
        tasks = make_tasks(kind, args.count, args.base, args.prime_base, seed)
        run(tasks[:16], args.workers, "fixed_4")
        order = list(METHODS)
        random.Random(seed * 157 + len(kind)).shuffle(order)
        checksum = None
        for position, method in enumerate(order):
            result = execute(method, tasks, args.workers)
            if checksum is None:
                checksum = result["checksum"]
            assert result["checksum"] == checksum, (kind, seed, method)
            raw.append({"workload": kind, "repeat": repeat + 1, "seed": seed,
                        "order": position, "method": method,
                        "elapsed_s": result["elapsed_s"], "checksum": result["checksum"],
                        "batch_count": result.get("batch_count", ""),
                        "batch_size_min": result.get("batch_size_min", ""),
                        "batch_size_max": result.get("batch_size_max", "")})
        print(f"PAIRED {kind:11s} seed={seed} methods={len(METHODS)}", flush=True)
    write_csv(args.output / "raw.csv", raw)
    summary = []
    for kind in KINDS:
        fixed = {r["repeat"]: r["elapsed_s"] for r in raw
                 if r["workload"] == kind and r["method"] == "fixed_4"}
        for method in METHODS:
            selected = [r for r in raw if r["workload"] == kind and r["method"] == method]
            times = [r["elapsed_s"] for r in selected]
            summary.append({"workload": kind, "method": method, "runs": len(times),
                            "median_s": statistics.median(times),
                            "min_s": min(times), "max_s": max(times),
                            "median_ratio_to_paired_fixed4": statistics.median(r["elapsed_s"] / fixed[r["repeat"]] for r in selected)})
    write_csv(args.output / "summary.csv", summary)
    manifest = {"status": "PASS", "system": platform.platform(),
                "seed_start": args.seed_start, "repeats": args.repeats,
                "workers": args.workers, "base": args.base,
                "prime_base": args.prime_base, "count": args.count,
                "workloads": KINDS, "methods": METHODS,
                "raw_rows": len(raw), "summary_rows": len(summary),
                "checksums_equal_within_groups": True,
                "timing_boundary": "end-to-end including worker startup, dispatch and teardown",
                "randomization": "group and method order seeded and shuffled"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DONE {len(raw)} paired runs", flush=True)


if __name__ == "__main__":
    main()
