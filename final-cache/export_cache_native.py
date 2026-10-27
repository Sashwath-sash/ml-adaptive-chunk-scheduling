"""Export held-out URL requests and frozen cache model for native C replay."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", type=Path, default=Path("data/browsetrace_full_400_sessions.csv"))
    ap.add_argument("--trace-url", default="https://github.com/landigf/BrowseTrace")
    ap.add_argument("--model-results", type=Path, default=Path("results_cache_compact_2pct_512"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--all-rows", action="store_true", help="Use entire external trace with frozen model")
    ap.add_argument("--shard-count", type=int, default=1)
    ap.add_argument("--shard-index", type=int, default=0)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output already exists")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        ap.error("invalid shard count/index")
    with args.trace.open(encoding="utf-8", newline="") as stream:
        rows = [(r["cache_key"], max(0, int(r["object_size_bytes"])))
                for r in csv.DictReader(stream)]
    test = rows if args.all_rows else rows[int(len(rows) * .8):]
    test = test[args.shard_index::args.shard_count]
    keys = {key: i for i, key in enumerate(sorted({key for key, _ in test}))}
    hosts = {host: i for i, host in enumerate(sorted({urlsplit(key).netloc for key in keys}))}
    lines = [f"{len(test)} {len(keys)} {len(hosts)}"]
    for key, size in test:
        parsed = urlsplit(key)
        path = parsed.path.lower()
        static = int(path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2")))
        lines.append(f"{keys[key]} {size} {hosts[parsed.netloc]} {len(path)} {static} {int(bool(parsed.query))} {len(key)}")
    model = json.loads((args.model_results / "hgb.json").read_text())
    info = json.loads((args.model_results / "results.json").read_text())
    threshold = info["chosen"]["threshold"] if "chosen" in info else info["chosen_threshold_on_validation"]
    capacity = info["held_out_ml"]["cache_entries"] if "held_out_ml" in info else info["capacity_entries"]
    node_count = sum(len(tree) for tree in model["trees"])
    model_lines = [f"{len(model['trees'])} {model['baseline']:.17g} {threshold:.17g} {capacity} {node_count}"]
    for tree in model["trees"]:
        model_lines.append(str(len(tree)))
        for feature, split, left, right, leaf, value, missing_left in tree:
            model_lines.append(f"{feature} {split:.17g} {left} {right} {int(leaf)} {value:.17g} {int(missing_left)}")
    args.output.mkdir(parents=True)
    (args.output / "test_trace.txt").write_text("\n".join(lines) + "\n")
    (args.output / "model.txt").write_text("\n".join(model_lines) + "\n")
    manifest = {"trace_url": args.trace_url,
                "trace_sha256": hashlib.sha256(args.trace.read_bytes()).hexdigest(),
                "source_model_results": str(args.model_results),
                "test_requests": len(test), "unique_keys": len(keys),
                "partition": "entire independent external trace" if args.all_rows else "final 20% held-out split",
                "shard_count": args.shard_count, "shard_index": args.shard_index,
                "model_stages": len(model["trees"]), "capacity": capacity,
                "threshold_chosen_on_validation": threshold,
                "note": "URL keys become deterministic 4-KiB backing blocks; original web bodies are not available"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
