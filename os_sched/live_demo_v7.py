"""Run a fresh compiled-C comparison using the frozen no-pilot model."""
import argparse
import json
import random
from pathlib import Path

from .experiment_v7 import FEATURES, TEST_SCALE, feature_vector, load_model, run_learned, task_list
from .scheduler_v7 import run_policy


def path_for(root, values):
    path = []
    node = root
    while "feature" in node:
        index, threshold = node["feature"], node["threshold"]
        branch = "left" if values[index] <= threshold else "right"
        path.append({"feature": FEATURES[index], "observed": values[index],
                     "threshold": threshold, "branch": branch})
        node = node[branch]
    return path, node["value"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("uniform", "moderate", "high", "phase_shift", "prime_scan", "late_heavy"), default="phase_shift")
    parser.add_argument("--seed", type=int, default=20001)
    parser.add_argument("--output", type=Path, default=Path("results_learned_v7_final"))
    args = parser.parse_args()
    model, artifact = load_model(args.output, 2, 192)
    tasks = task_list(args.kind, 192, *TEST_SCALE, args.seed)
    features = feature_vector(tasks, 2)
    path, selected = path_for(model.root, features)
    methods = ["fixed_4", "contig_32", "lpt_2", "lpt_4", "learned"]
    random.Random(args.seed).shuffle(methods)
    results = {}
    for method in methods:
        result = run_learned(tasks, 2, model) if method == "learned" else run_policy(tasks, 2, method)
        results[method] = {key: result[key] for key in
                           ("elapsed_s", "checksum", "batch_count", "batch_latency_p95_s")}
        if method == "learned":
            results[method]["selected_policy"] = result["selected_policy"]
            results[method]["inference_s"] = result["inference_s"]
    equal = len({item["checksum"] for item in results.values()}) == 1
    if not equal:
        raise AssertionError("output checksum mismatch")
    trace = {"kind": args.kind, "seed": args.seed, "tasks": 192, "workers": 2,
             "model": artifact["chosen"], "features": dict(zip(FEATURES, features)),
             "decision_path": path, "selected_policy": selected,
             "methods": results, "checksum_equal": equal,
             "warning": "one live run is functional evidence; use saved held-out groups for performance estimates"}
    target = args.output / "live_demo.json"
    target.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(f"LIVE {args.kind} {len(tasks)} compiled-C tasks, two Linux workers, seed={args.seed}")
    for step in path:
        sign = "<=" if step["branch"] == "left" else ">"
        print(f"MODEL: {step['feature']}={step['observed']:.5g} {sign} {step['threshold']:.5g}")
    print(f"LEARNED POLICY: {selected}")
    for method in ("fixed_4", "contig_32", "lpt_2", "lpt_4", "learned"):
        print(f"{method:12} {results[method]['elapsed_s']:.3f}s checksum={results[method]['checksum']}")
    print(f"All outputs equal: {equal}; trace saved to {target}")
    print("Single-run timing is noisy; use held-out test_summary.csv for performance claims.")


if __name__ == "__main__":
    main()
