"""Load a saved tree and show real-time chunk choices as workers execute."""
import argparse
import json
from pathlib import Path

from .scheduler_v2 import run
from .tree import DecisionTree
from .workload import generate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, default=Path("results_complete/model.json"))
    ap.add_argument("--output", type=Path, default=Path("results_complete/live_demo.json"))
    ap.add_argument("--workload", choices=("uniform", "moderate", "high", "phase_shift", "prime_scan"), default="phase_shift")
    ap.add_argument("--seed", type=int, default=9001)
    ap.add_argument("--count", type=int, default=192)
    ap.add_argument("--base", type=int, default=1_500_000)
    ap.add_argument("--prime-base", type=int, default=300)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--compact", action="store_true", help="print a short, readable live trace")
    args = ap.parse_args()
    model = DecisionTree.from_dict(json.loads(args.model.read_text(encoding="utf-8")))
    base = args.prime_base if args.workload == "prime_scan" else args.base
    tasks = generate(args.workload, args.count, base, args.seed)
    print(f"LIVE {args.workload} tasks={len(tasks)} workers={args.workers} model={args.model}", flush=True)

    def show(event):
        if args.compact:
            print(f"round={event['round']:02d} chunk={event['old_chunk']}->{event['new_chunk']} "
                  f"completed={event['tasks_completed']} decision_us={event['decision_s'] * 1e6:.1f}",
                  flush=True)
            return
        print(f"round={event['round']:02d} completed={event['tasks_completed']:3d} "
              f"chunk {event['old_chunk']:2d}->{event['new_chunk']:2d} "
              f"throughput={event['throughput']:.1f} task_cost_change={event['task_cost_change']:+.2f} "
              f"reason={event['reason']} decision_us={event['decision_s'] * 1e6:.1f}", flush=True)

    fixed = run(tasks, args.workers, "fixed_4")
    tree = run(tasks, args.workers, "ml", model, show)
    guarded = run(tasks, args.workers, "guarded_ml", model, show)
    if len({fixed["checksum"], tree["checksum"], guarded["checksum"]}) != 1:
        raise AssertionError("live demonstration checksum mismatch")
    result = {"workload": args.workload, "seed": args.seed, "tasks": len(tasks),
              "model": str(args.model), "fixed_4": fixed, "tree": tree, "guarded_tree": guarded,
              "checksums_equal": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"END fixed4={fixed['elapsed_s']:.3f}s tree={tree['elapsed_s']:.3f}s "
          f"guarded={guarded['elapsed_s']:.3f}s checksums_equal=True output={args.output}", flush=True)


if __name__ == "__main__":
    main()
