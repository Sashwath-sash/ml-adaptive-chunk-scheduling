"""Frozen-model confirmation at a larger unseen scale and fresh seeds."""
import csv
import json
import math
import platform
import random
import statistics
from pathlib import Path

from .experiment_v6 import KINDS_V6, task_list
from .experiment_v7 import load_model, run_learned
from .scheduler_v7 import run_policy

METHODS = ("contig_32", "lpt_2", "lpt_4", "learned")
SCALE = (4_000_000, 8000)
SEED_BASE = 25001
SEEDS_PER_KIND = 20


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(raw, kind, method, baseline):
    groups = {(int(row["seed"]), row["method"]): float(row["elapsed_s"])
              for row in raw if row["kind"] == kind}
    ratios = [groups[(seed, method)] / groups[(seed, baseline)]
              for seed in range(SEED_BASE, SEED_BASE + SEEDS_PER_KIND)]
    rng = random.Random(77199 + len(kind) * 13 + len(method) * 19 + len(baseline))
    boots = sorted(statistics.median(rng.choices(ratios, k=len(ratios))) for _ in range(4000))
    return {"kind": kind, "method": method, "baseline": baseline,
            "n": len(ratios), "median_paired_ratio": statistics.median(ratios),
            "geometric_mean_ratio": math.exp(statistics.mean(math.log(value) for value in ratios)),
            "paired_wins": sum(value < 1 for value in ratios),
            "bootstrap_median_95_low": boots[99], "bootstrap_median_95_high": boots[3899]}


def main():
    folder = Path("results_learned_v7_final")
    if (folder / "confirm_raw.csv").exists():
        raise RuntimeError("confirmation already exists; refusing to overwrite")
    model, artifact = load_model(folder, 2, 192)
    groups = [(kind, seed) for kind in KINDS_V6
              for seed in range(SEED_BASE, SEED_BASE + SEEDS_PER_KIND)]
    random.Random(73991).shuffle(groups)
    raw = []
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = task_list(kind, 192, *SCALE, seed)
        methods = list(METHODS)
        random.Random(seed * 43 + len(kind)).shuffle(methods)
        checksum = None
        for position, method in enumerate(methods):
            result = run_learned(tasks, 2, model) if method == "learned" else run_policy(tasks, 2, method)
            checksum = result["checksum"] if checksum is None else checksum
            if result["checksum"] != checksum:
                raise AssertionError(f"checksum mismatch {kind} {seed} {method}")
            raw.append({"kind": kind, "seed": seed, "base": SCALE[0], "prime_base": SCALE[1],
                        "order": position, "method": method,
                        "selected_policy": result.get("selected_policy", ""),
                        "elapsed_s": result["elapsed_s"], "checksum": checksum,
                        "batch_p95_s": result["batch_latency_p95_s"],
                        "cpu_utilization_fraction": result["cpu_utilization_fraction"]})
        print(f"CONFIRM {group_no:03}/{len(groups)} {kind:11} seed={seed}", flush=True)
    write_csv(folder / "confirm_raw.csv", raw)
    summary = [summarize(raw, kind, method, baseline)
               for kind in KINDS_V6 for baseline in ("contig_32", "lpt_2") for method in METHODS]
    write_csv(folder / "confirm_summary.csv", summary)
    manifest = {"status": "PASS", "frozen_model": artifact["chosen"], "scale": SCALE,
                "seed_base": SEED_BASE, "seeds_per_kind": SEEDS_PER_KIND,
                "groups": len(groups), "timed_runs": len(raw), "methods": METHODS,
                "checksums_equal": True, "method_order": "seeded shuffle per matched group",
                "platform": platform.platform(), "scope": "one WSL2 host, generated workloads, scale beyond training"}
    (folder / "confirm_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for row in summary:
        if row["method"] == "learned":
            print(f"LEARNED {row['kind']:11} vs {row['baseline']:9} ratio={row['median_paired_ratio']:.3f} "
                  f"wins={row['paired_wins']}/{row['n']}", flush=True)
    print(f"CONFIRM PASS {len(groups)} groups, {len(raw)} complete runs, equal checksums", flush=True)


if __name__ == "__main__":
    main()
