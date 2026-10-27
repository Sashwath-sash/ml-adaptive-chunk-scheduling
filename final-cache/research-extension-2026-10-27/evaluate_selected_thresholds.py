"""Exploratory native evaluation of validation-selected admission thresholds.

The threshold rule was designed after inspecting capacity-sweep outcomes, so
these held-out streams are no longer a fresh blind test of the research idea.
"""
import argparse
import json
import subprocess
from pathlib import Path

from evaluate_admission_controls import INPUTS


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    selected = json.loads(args.selection.read_text())
    linux_root = "/mnt/" + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
    prefix = ["wsl.exe", "--cd", linux_root, "-e"]
    results = {"selection": str(args.selection), "exploratory_post_hoc": True,
               "capacities": {}}
    for capacity_text, per_parent in selected["capacities"].items():
        capacity = int(capacity_text)
        prior_name = ("results_admission_controls_2026-10-27.json" if capacity == 512 else
                      f"results_admission_controls_{capacity}_2026-10-27.json")
        prior = json.loads((ROOT / prior_name).read_text())
        results["capacities"][capacity_text] = {}
        for stream, folder in INPUTS.items():
            results["capacities"][capacity_text][stream] = {}
            for parent in ("arc", "s3fifo"):
                threshold = per_parent[parent]["chosen"]["threshold"]
                policy = "hybrid_" + parent
                command = prefix + ["./cache_native", f"{folder}/test_trace.txt",
                                    f"{folder}/model.txt", "1", policy, "--sync",
                                    "--capacity", str(capacity), "--threshold", str(threshold)]
                proc = subprocess.run(command, input="\n", capture_output=True, text=True)
                if proc.returncode:
                    raise RuntimeError(f"{capacity} {stream} {policy}: {proc.stderr}\n{proc.stdout}")
                record = json.loads(proc.stdout.split("\n", 1)[1])["repeats"][0][0]
                prior_stream = prior["streams"][stream]
                if record["checksum"] != prior_stream["checksum"]:
                    raise AssertionError(f"checksum differs: {capacity} {stream} {policy}")
                baseline = prior_stream["policies"][parent]["direct_reads"]
                old_ml = prior_stream["policies"][policy]["direct_reads"]
                results["capacities"][capacity_text][stream][parent] = {
                    "threshold_selected_on_validation": threshold,
                    "parent_direct_reads": baseline,
                    "original_fixed_threshold_direct_reads": old_ml,
                    "calibrated_direct_reads": record["direct_reads"],
                    "calibrated_reduction_vs_parent_pct": round(
                        100 * (baseline - record["direct_reads"]) / baseline, 3),
                    "checksum": record["checksum"],
                }
            print(capacity, stream, results["capacities"][capacity_text][stream], flush=True)
            args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
