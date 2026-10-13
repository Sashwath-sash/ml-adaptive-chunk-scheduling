"""Fresh paired comparison on a recorded rare-tail-straggler CPU workload."""
import argparse
import json
import platform
import random
import statistics
from pathlib import Path

from .compare_existing import builtin
from .experiment_complete import write_csv
from .scheduler_v2 import run
from .scheduler_v4 import run_balanced
from .straggler_workload import generate_tail_spike

METHODS = ("fixed_4", "fixed_16", "pool_map_16", "balanced_8",
           "balanced_16", "balanced_32", "balanced_fifo_16")


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
    ap.add_argument("--seed-start", type=int, default=8001)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--base", type=int, default=1_500_000)
    ap.add_argument("--spike-factor", type=int, default=40)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw, inputs = [], []
    repeats = list(range(args.repeats))
    random.Random(args.seed_start * 29).shuffle(repeats)
    for repeat in repeats:
        seed = args.seed_start + repeat
        tasks, spike_index = generate_tail_spike(args.count, args.base, seed, args.spike_factor)
        inputs.extend({"seed": seed, "task_index": i, "work": task.work, "task_seed": task.seed,
                       "is_spike": i == spike_index} for i, task in enumerate(tasks))
        run(tasks[:16], args.workers, "fixed_4")
        order = list(METHODS)
        random.Random(seed * 199).shuffle(order)
        checksum = None
        for position, method in enumerate(order):
            result = execute(method, tasks, args.workers)
            if checksum is None:
                checksum = result["checksum"]
            assert result["checksum"] == checksum, (seed, method)
            raw.append({"repeat": repeat + 1, "seed": seed, "spike_index": spike_index,
                        "order": position, "method": method,
                        "elapsed_s": result["elapsed_s"], "checksum": result["checksum"],
                        "batch_count": result.get("batch_count", "")})
        print(f"PAIRED tail_spike seed={seed} spike_index={spike_index}", flush=True)
    write_csv(args.output / "dataset.csv", inputs)
    write_csv(args.output / "raw.csv", raw)
    fixed = {r["repeat"]: r["elapsed_s"] for r in raw if r["method"] == "fixed_4"}
    summary = []
    for method in METHODS:
        selected = [r for r in raw if r["method"] == method]
        values = [r["elapsed_s"] for r in selected]
        summary.append({"method": method, "runs": len(values),
                        "median_s": statistics.median(values),
                        "mean_s": statistics.mean(values),
                        "min_s": min(values), "max_s": max(values),
                        "median_ratio_to_paired_fixed4": statistics.median(r["elapsed_s"] / fixed[r["repeat"]] for r in selected)})
    write_csv(args.output / "summary.csv", summary)
    manifest = {"status": "PASS", "system": platform.platform(),
                "seed_start": args.seed_start, "repeats": args.repeats,
                "workers": args.workers, "count": args.count, "base": args.base,
                "spike_factor": args.spike_factor, "spike_position": "random among final 8 task slots",
                "methods": METHODS, "raw_rows": len(raw), "dataset_rows": len(inputs),
                "checksums_equal_within_pairs": True,
                "timing_boundary": "end-to-end including pool startup, dispatch and teardown",
                "purpose": "specific tail-straggler workload; not proof of universal speedup"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DONE {len(raw)} paired runs", flush=True)


if __name__ == "__main__":
    main()
