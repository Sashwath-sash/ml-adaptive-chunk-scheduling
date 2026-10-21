"""Development-only screen of dispatch planners on distinct seeds.

This is not the final test and must never be presented as held-out evidence.
"""
import argparse
import random
import statistics
from pathlib import Path

from .experiment_v6 import KINDS_V6, csv_write, task_list
from .scheduler_v7 import POLICIES, run_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results_v7_screen"))
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--base", type=int, default=1_200_000)
    parser.add_argument("--prime-base", type=int, default=2400)
    parser.add_argument("--policies", nargs="+", default=list(POLICIES))
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("seeds must be positive")
    if "contig_32" not in args.policies or any(policy not in POLICIES for policy in args.policies):
        parser.error("policies must be supported and include contig_32")
    args.output.mkdir(exist_ok=True)
    groups = [(kind, 10001 + i) for kind in KINDS_V6 for i in range(args.seeds)]
    random.Random(17717).shuffle(groups)
    raw = []
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = task_list(kind, 192, args.base, args.prime_base, seed)
        order = list(args.policies)
        random.Random(seed * 19 + len(kind)).shuffle(order)
        checksum = None
        for position, policy in enumerate(order):
            result = run_policy(tasks, 2, policy)
            checksum = result["checksum"] if checksum is None else checksum
            if checksum != result["checksum"]:
                raise AssertionError(f"checksum mismatch: {kind} {seed} {policy}")
            raw.append({"kind": kind, "seed": seed, "base": args.base,
                        "prime_base": args.prime_base, "order": position,
                        "policy": policy, "elapsed_s": result["elapsed_s"],
                        "checksum": result["checksum"], "batch_count": result["batch_count"],
                        "planning_s": result["planning_s"]})
        print(f"SCREEN {group_no}/{len(groups)} {kind} {seed}", flush=True)
    csv_write(args.output / "raw.csv", raw)
    summary = []
    for kind in KINDS_V6:
        base = {int(row["seed"]): row["elapsed_s"] for row in raw
                if row["kind"] == kind and row["policy"] == "contig_32"}
        for policy in args.policies:
            subset = [row for row in raw if row["kind"] == kind and row["policy"] == policy]
            ratios = [row["elapsed_s"] / base[row["seed"]] for row in subset]
            summary.append({"kind": kind, "policy": policy, "n": len(subset),
                            "median_ratio_to_contig32": statistics.median(ratios),
                            "wins": sum(ratio < 1 for ratio in ratios)})
    csv_write(args.output / "summary.csv", summary)
    for kind in KINDS_V6:
        winners = sorted((row for row in summary if row["kind"] == kind),
                         key=lambda row: row["median_ratio_to_contig32"])[:4]
        print(kind, [(row["policy"], round(row["median_ratio_to_contig32"], 3)) for row in winners], flush=True)


if __name__ == "__main__":
    main()
