"""Run the actual trained selector and hybrid live on one fresh Linux task list."""
import argparse
import json
from pathlib import Path

from .experiment_v5 import load_models, tasks_for
from .scheduler_v5 import run_auto, run_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("uniform", "moderate", "high", "phase_shift", "prime_scan", "late_heavy"), default="late_heavy")
    parser.add_argument("--seed", type=int, default=5001)
    parser.add_argument("--count", type=int, default=192)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--base", type=int, default=1_500_000)
    parser.add_argument("--prime-base", type=int, default=3000)
    parser.add_argument("--model-dir", type=Path, default=Path("results_policy_v5"))
    parser.add_argument("--output", type=Path, default=Path("results_policy_v5/live_demo.json"))
    args = parser.parse_args()
    selector, chunk_model, metadata = load_models(args.model_dir)
    if (args.workers, args.count, args.base, args.prime_base) != (
        metadata["workers"], metadata["count"], metadata["base"], metadata["prime_base"]):
        parser.error("demo configuration must match selector training configuration")
    tasks = tasks_for(args.kind, args.seed, args)
    results = {"fixed_4": run_policy(tasks, args.workers, "fixed_4", chunk_model),
               "balanced_32": run_policy(tasks, args.workers, "balanced_32", chunk_model),
               "hybrid_once": run_policy(tasks, args.workers, "hybrid_once", chunk_model),
               "auto": run_auto(tasks, args.workers, selector, chunk_model)}
    equal = len({row["checksum"] for row in results.values()}) == 1
    if not equal:
        raise AssertionError("methods returned different checksums")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"kind": args.kind, "seed": args.seed,
                                        "workers": args.workers, "count": len(tasks),
                                        "checksums_equal": equal, "results": results}, indent=2), encoding="utf-8")
    print(f"LIVE kind={args.kind} tasks={len(tasks)} workers={args.workers} seed={args.seed}")
    print(f"trained selector chose: {results['auto']['selected_policy']}")
    print(f"one-pilot hybrid chose chunk={results['hybrid_once']['chosen_chunk']} "
          f"and {results['hybrid_once']['target_batches']} target cost batches")
    print("Full-run elapsed seconds (includes planning, inference and pool lifecycle):")
    for method, row in results.items():
        print(f"  {method:13} {row['elapsed_s']:.3f}")
    print(f"checksums_equal={equal}; result={args.output}")
    print("One live run is a functional demo, not the multi-seed performance estimate.")


if __name__ == "__main__":
    main()
