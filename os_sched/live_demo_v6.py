"""Demonstrate the measured-pilot tree and its actual path on fresh C work."""
import argparse
import json
from pathlib import Path

from .experiment_v6 import RUNTIME_FEATURES, TEST_SCALE, load_model, task_list, RuntimeProjection
from .scheduler_v2 import run as run_fixed
from .scheduler_v4 import run_balanced
from .scheduler_v6 import FEATURES, run_live
from .tree import DecisionTree


def decision_path(root, feature_values, feature_names):
    node = root
    path = []
    while "feature" in node:
        name = feature_names[node["feature"]]
        value = feature_values[name]
        threshold = node["threshold"]
        branch = "left" if value <= threshold else "right"
        path.append({"feature": name, "measured_or_known_value": value,
                     "threshold": threshold, "branch": branch})
        node = node[branch]
    return path, node["value"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("uniform", "moderate", "high", "phase_shift", "prime_scan", "late_heavy"), default="late_heavy")
    parser.add_argument("--seed", type=int, default=9001)
    parser.add_argument("--output-dir", type=Path, default=Path("results_live_v6"))
    args = parser.parse_args()
    model, artifact = load_model(args.output_dir)
    runtime_artifact = json.loads((args.output_dir / "model_runtime_only.json").read_text(encoding="utf-8"))
    runtime_model = RuntimeProjection(DecisionTree.from_dict(runtime_artifact["tree"]))
    workers, count = artifact["workers"], artifact["count"]
    tasks = task_list(args.kind, count, *TEST_SCALE, args.seed)
    results = {
        "fixed_no_pilot": run_fixed(tasks, workers, "fixed_4"),
        "cost32_no_pilot": run_balanced(tasks, workers, 32),
        "live_tree": run_live(tasks, workers, model=model),
        "live_tree_runtime_only": run_live(tasks, workers, model=runtime_model),
    }
    if len({row["checksum"] for row in results.values()}) != 1:
        raise AssertionError("checksum mismatch")
    mixed_path, mixed_leaf = decision_path(artifact["tree"]["root"], results["live_tree"]["features"], FEATURES)
    runtime_path, runtime_leaf = decision_path(runtime_artifact["tree"]["root"],
                                              results["live_tree_runtime_only"]["features"], RUNTIME_FEATURES)
    assert mixed_leaf == results["live_tree"]["policy"]
    assert runtime_leaf == results["live_tree_runtime_only"]["policy"]
    output = args.output_dir / "live_demo_v6.json"
    output.write_text(json.dumps({"kind": args.kind, "seed": args.seed,
                                  "base": TEST_SCALE[0], "prime_base": TEST_SCALE[1],
                                  "count": count, "workers": workers, "checksums_equal": True,
                                  "mixed_tree_path": mixed_path,
                                  "runtime_only_tree_path": runtime_path,
                                  "results": results}, indent=2), encoding="utf-8")
    print(f"LIVE {args.kind} tasks={count} workers={workers} seed={args.seed}")
    print("compiled C work completed; all four outputs have the same checksum")
    for node in mixed_path:
        print(f"MIXED TREE: {node['feature']}={node['measured_or_known_value']:.6g} "
              f"{'<=' if node['branch'] == 'left' else '>'} {node['threshold']:.6g}")
    print(f"MIXED TREE SELECTED {mixed_leaf}")
    for node in runtime_path:
        print(f"MEASURED-ONLY TREE: {node['feature']}={node['measured_or_known_value']:.6g} "
              f"{'<=' if node['branch'] == 'left' else '>'} {node['threshold']:.6g}")
    print(f"MEASURED-ONLY TREE SELECTED {runtime_leaf}")
    for method, result in results.items():
        print(f"{method:23} elapsed={result['elapsed_s']:.3f}s "
              f"batch_p95={result['batch_latency_p95_s']:.3f}s")
    print(f"checksums_equal=True saved={output}")
    print("This one live run demonstrates functionality; use held-out test_summary.csv for performance claims.")


if __name__ == "__main__":
    main()
