"""Demonstrate the saved tree making one online decision on Linux."""
import argparse
import json
from pathlib import Path

from .experiment_complete import make_tasks
from .scheduler_v2 import run
from .scheduler_v3 import run_once
from .tree import DecisionTree


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, default=Path("results_final_linux/model.json"))
    ap.add_argument("--output", type=Path, default=Path("results_improvement/live_demo.json"))
    ap.add_argument("--workload", default="high")
    ap.add_argument("--seed", type=int, default=9101)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--base", type=int, default=1_500_000)
    ap.add_argument("--prime-base", type=int, default=3000)
    args = ap.parse_args()
    model = DecisionTree.from_dict(json.loads(args.model.read_text(encoding="utf-8")))
    tasks = make_tasks(args.workload, args.count, args.base, args.prime_base, args.seed)

    def show(event):
        print(f"LIVE after {event['tasks_completed']} completed tasks: "
              f"chunk {event['old_chunk']} -> {event['new_chunk']}; "
              f"decision {event['decision_s'] * 1e6:.1f} us", flush=True)

    fixed = run(tasks, args.workers, "fixed_4")
    old = run(tasks, args.workers, "ml", model)
    improved = run_once(tasks, args.workers, model, show)
    assert len({fixed["checksum"], old["checksum"], improved["checksum"]}) == 1
    result = {"workload": args.workload, "seed": args.seed, "workers": args.workers,
              "count": args.count, "model": str(args.model),
              "fixed_4": fixed, "old_tree": old, "one_decision_tree": improved,
              "checksums_equal": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"fixed4={fixed['elapsed_s']:.3f}s old_tree={old['elapsed_s']:.3f}s "
          f"one_decision_tree={improved['elapsed_s']:.3f}s checksums_equal=True", flush=True)


if __name__ == "__main__":
    main()
