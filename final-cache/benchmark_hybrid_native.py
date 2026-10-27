"""Alternating-order native ARC versus ML-filtered ARC timing."""
import json
import argparse
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--baseline", choices=("arc", "s3fifo"), default="arc")
ap.add_argument("--candidate", choices=("hybrid_arc", "hybrid_s3fifo"), default="hybrid_arc")
ap.add_argument("--output", type=Path, default=ROOT / "results_hybrid_native_benchmark.json")
ap.add_argument("--only", choices=("scripted", "llm", "nasa_aug", "calgary"))
args = ap.parse_args()
if args.output.exists():
    ap.error("output already exists")
LINUX_ROOT = "/mnt/" + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
PREFIX = ["wsl.exe", "--cd", LINUX_ROOT, "-e"]
inputs = {"scripted": "cache_native_input_three_source_scripted",
          "llm": "cache_native_input_three_source_llm",
          "nasa_aug": "cache_native_input_nasa_aug_v1",
          "calgary": "cache_native_input_calgary_v1"}
result = {}
for name, folder in inputs.items():
    if args.only and name != args.only:
        continue
    runs = {args.baseline: [], args.candidate: []}
    for rep in range(5):
        for policy in ((args.baseline, args.candidate) if rep % 2 == 0 else (args.candidate, args.baseline)):
            cmd = PREFIX + ["./cache_native", f"{folder}/test_trace.txt",
                            f"{folder}/model.txt", "1", policy, "--sync"]
            run = subprocess.run(cmd, input="\n", capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError(f"{name} {policy}: {run.stderr}")
            record = json.loads(run.stdout.split("\n", 1)[1])["repeats"][0][0]
            runs[policy].append(record)
        print(f"{name}: repetition {rep+1}/5", flush=True)
    result[name] = {policy: {"direct_reads": records[0]["direct_reads"],
                             "median_loop_seconds": statistics.median(r["wall_seconds"] for r in records),
                             "range_loop_seconds": [min(r["wall_seconds"] for r in records),
                                                    max(r["wall_seconds"] for r in records)],
                             "tree_nodes_evaluated": records[0]["tree_nodes_evaluated"],
                             "raw_runs": records}
                    for policy, records in runs.items()}
    assert len({r["checksum"] for records in runs.values() for r in records}) == 1
    print(json.dumps({p: {k: v for k, v in d.items() if k != "raw_runs"}
                      for p, d in result[name].items()}, indent=2), flush=True)
args.output.write_text(json.dumps(result, indent=2))
