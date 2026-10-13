"""Show cost-balanced batches and real Linux times on a fresh tail-spike seed."""
import argparse
import json
from pathlib import Path

from .compare_existing import builtin
from .scheduler_v2 import run
from .scheduler_v4 import estimated_cost, make_balanced_batches, run_balanced
from .straggler_workload import generate_tail_spike


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=9001)
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--base", type=int, default=1_500_000)
    ap.add_argument("--spike-factor", type=int, default=40)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--output", type=Path, default=Path("results_straggler_test/live_demo.json"))
    args = ap.parse_args()
    tasks, spike = generate_tail_spike(args.count, args.base, args.seed, args.spike_factor)
    batches = make_balanced_batches(tasks, args.workers, 32)
    spike_batch = next(i for i, batch in enumerate(batches) if tasks[spike] in batch)
    print(f"Tail spike at task {spike}; balanced scheduler moves its batch to dispatch position {spike_batch}", flush=True)
    fixed = run(tasks, args.workers, "fixed_4")
    standard = builtin(tasks, args.workers, "pool_map_16")
    balanced = run_balanced(tasks, args.workers, 32)
    assert len({fixed["checksum"], standard["checksum"], balanced["checksum"]}) == 1
    result = {"seed": args.seed, "count": args.count, "workers": args.workers,
              "spike_factor": args.spike_factor, "spike_task_index": spike,
              "spike_dispatch_batch_index": spike_batch,
              "batch_sizes": [len(batch) for batch in batches],
              "batch_estimated_costs": [sum(estimated_cost(task) for task in batch) for batch in batches],
              "fixed_4": fixed, "pool_map_16": standard, "balanced_32": balanced,
              "checksums_equal": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"fixed4={fixed['elapsed_s']:.3f}s pool_map16={standard['elapsed_s']:.3f}s "
          f"balanced32={balanced['elapsed_s']:.3f}s checksums_equal=True", flush=True)


if __name__ == "__main__":
    main()
