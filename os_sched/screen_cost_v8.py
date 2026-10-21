"""Development comparison: measured-runtime cost model versus analytic LPT.

Uses predictor-validation seeds, not a final independent scheduling test.
"""
import csv
import random
import statistics
from pathlib import Path

from .cost_model_v8 import VALIDATION_SCALE, load
from .experiment_v6 import KINDS_V6, task_list
from .experiment_v7 import load_model
from .scheduler_v7 import run_policy
from .scheduler_v8 import run_ml

METHODS = ("cost32", "analytic_lpt2", "learned_cost_lpt2", "learned_hybrid")


def main():
    output = Path("results_cost_model_v8")
    cost_model, _ = load(output)
    policy_model, _ = load_model(Path("results_learned_v7_final"), 2, 192)
    rows = []
    groups = [(kind, seed) for kind in KINDS_V6 for seed in range(22001, 22004)]
    random.Random(11677).shuffle(groups)
    for group_no, (kind, seed) in enumerate(groups, 1):
        tasks = task_list(kind, 192, *VALIDATION_SCALE, seed)
        checksum = None
        for repeat in range(2):
            order = list(METHODS)
            random.Random(seed * 31 + repeat * 17 + len(kind)).shuffle(order)
            for position, method in enumerate(order):
                if method == "cost32":
                    result = run_policy(tasks, 2, "contig_32")
                elif method == "analytic_lpt2":
                    result = run_policy(tasks, 2, "lpt_2")
                elif method == "learned_cost_lpt2":
                    result = run_ml(tasks, 2, cost_model, fixed_bins=2)
                else:
                    result = run_ml(tasks, 2, cost_model, policy_model=policy_model)
                checksum = result["checksum"] if checksum is None else checksum
                if result["checksum"] != checksum:
                    raise AssertionError(f"checksum mismatch {kind} {seed}")
                rows.append({"kind": kind, "seed": seed, "repeat": repeat,
                             "order": position, "method": method,
                             "selected_policy": result.get("selected_policy", ""),
                             "elapsed_s": result["elapsed_s"], "checksum": checksum})
        print(f"COST SCREEN {group_no}/{len(groups)} {kind} {seed}", flush=True)
    with (output / "scheduler_screen_raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for kind in KINDS_V6:
        subset = [row for row in rows if row["kind"] == kind]
        base = {(row["seed"], row["repeat"]): row["elapsed_s"] for row in subset if row["method"] == "analytic_lpt2"}
        for method in METHODS:
            ratios = [row["elapsed_s"] / base[(row["seed"], row["repeat"])]
                      for row in subset if row["method"] == method]
            print(f"{kind:11} {method:20} ratio={statistics.median(ratios):.3f} wins={sum(x < 1 for x in ratios)}/{len(ratios)}")
    print("Development-only screen; not an independent final test.")


if __name__ == "__main__":
    main()
