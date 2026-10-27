"""Compare learned admission with cheap admission on the same native cache parents.

The primary outcome is deterministic backing-read calls. Timing is exploratory:
each policy is a separate process and host activity can change loop duration.
"""
import argparse
import json
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUTS = {
    "BrowseTrace A": "cache_native_input_three_source_scripted",
    "BrowseTrace B": "cache_native_input_three_source_llm",
    "NASA August": "cache_native_input_nasa_aug_v1",
    "Calgary": "cache_native_input_calgary_v1",
}
POLICIES = (
    "arc", "second_touch_arc", "hybrid_arc",
    "s3fifo", "second_touch_s3fifo", "hybrid_s3fifo",
)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--capacity", type=int, default=512,
                        help="Cache entries; frozen model and threshold are unchanged")
    parser.add_argument("--only", choices=tuple(INPUTS))
    parser.add_argument("--input-folder", help="Use one additional exported native trace folder")
    parser.add_argument("--stream-name", help="Label for --input-folder")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.repeats < 1:
        parser.error("repeats must be positive")
    if not 2 <= args.capacity <= 65536:
        parser.error("capacity must be 2..65536")
    if bool(args.input_folder) != bool(args.stream_name):
        parser.error("--input-folder and --stream-name are required together")
    if args.input_folder and args.only:
        parser.error("--only cannot be combined with --input-folder")

    linux_root = "/mnt/" + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
    prefix = ["wsl.exe", "--cd", linux_root, "-e"]
    results = {"created_utc": datetime.now(timezone.utc).isoformat(),
               "repeats": args.repeats, "capacity_entries": args.capacity,
               "streams": {}}
    inputs = ({args.stream_name: args.input_folder} if args.input_folder else INPUTS)
    for stream, folder in inputs.items():
        if args.only and stream != args.only:
            continue
        observations = {policy: [] for policy in POLICIES}
        for repetition in range(args.repeats):
            order = POLICIES if repetition % 2 == 0 else tuple(reversed(POLICIES))
            for policy in order:
                command = prefix + ["./cache_native", f"{folder}/test_trace.txt",
                                    f"{folder}/model.txt", "1", policy, "--sync",
                                    "--capacity", str(args.capacity)]
                proc = subprocess.run(command, input="\n", capture_output=True, text=True)
                if proc.returncode:
                    raise RuntimeError(f"{stream} {policy}: {proc.stderr}\n{proc.stdout}")
                record = json.loads(proc.stdout.split("\n", 1)[1])["repeats"][0][0]
                observations[policy].append(record)
            print(f"{stream}: {repetition + 1}/{args.repeats}", flush=True)

        checksums = {r["checksum"] for runs in observations.values() for r in runs}
        if len(checksums) != 1:
            raise AssertionError(f"different data returned on {stream}: {checksums}")
        summary = {}
        for policy, runs in observations.items():
            counts = {r["direct_reads"] for r in runs}
            if len(counts) != 1:
                raise AssertionError(f"unstable miss count on {stream} {policy}")
            summary[policy] = {"direct_reads": runs[0]["direct_reads"],
                               "median_loop_seconds": statistics.median(
                                   r["wall_seconds"] for r in runs),
                               "all_loop_seconds": [r["wall_seconds"] for r in runs],
                               "tree_nodes_evaluated": runs[0]["tree_nodes_evaluated"]}
        for parent in ("arc", "s3fifo"):
            ml, cheap = "hybrid_" + parent, "second_touch_" + parent
            summary[ml]["read_reduction_vs_parent_pct"] = round(
                100 * (summary[parent]["direct_reads"] - summary[ml]["direct_reads"])
                / summary[parent]["direct_reads"], 3)
            summary[ml]["read_reduction_vs_second_touch_pct"] = round(
                100 * (summary[cheap]["direct_reads"] - summary[ml]["direct_reads"])
                / summary[cheap]["direct_reads"], 3)
        results["streams"][stream] = {"checksum": checksums.pop(), "policies": summary}
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps({p: summary[p]["direct_reads"] for p in POLICIES}), flush=True)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    run()
