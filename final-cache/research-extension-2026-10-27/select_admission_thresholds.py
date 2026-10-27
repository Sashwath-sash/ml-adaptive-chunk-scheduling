"""Select frozen-model admission cutoffs using validation streams only.

This is an exploratory follow-up to the original 512-entry experiment. It
compares one fixed model across cache capacities; no held-out request stream
is read during selection.
"""
import argparse
import json
from pathlib import Path

import joblib

from arc_reference_probe import arc_misses
from cache_admission_probe import feature_rows, read_rows
from s3fifo_reference_probe import simulate as s3fifo_misses


ROOT = Path(__file__).resolve().parent
CAPACITIES = (256, 512, 1024)
THRESHOLDS = (.05, .1, .15, .2, .3, .4, .5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    model = joblib.load(ROOT / "results_cache_three_source_v1/model.joblib")
    specs = {
        "BrowseTrace A val": ("browsetrace_full_400_sessions.csv", None),
        "BrowseTrace B val": ("browsetrace_llm_full_901.csv", None),
        "NASA July val": ("nasa_jul_last_300k_cache.csv", (150000, 200000)),
    }
    streams = {}
    for name, (file, bounds) in specs.items():
        rows = read_rows(ROOT / "data" / file)
        rows = rows[slice(*bounds)] if bounds else rows[int(len(rows) * .6):int(len(rows) * .8)]
        keys = [k for k, _ in rows]
        scores = model.predict_proba(feature_rows(rows))[:, 1]
        streams[name] = (keys, scores)
    result = {"selection_splits": list(streams), "capacities": {},
              "threshold_candidates": THRESHOLDS,
              "objective": "minimize worst validation ratio to unfiltered parent; mean ratio breaks ties"}
    for capacity in CAPACITIES:
        entry = {}
        for parent in ("arc", "s3fifo"):
            per_stream = {}
            for name, (keys, scores) in streams.items():
                baseline = (arc_misses(keys, capacity) if parent == "arc" else
                            s3fifo_misses(keys, capacity))
                candidates = {}
                for threshold in THRESHOLDS:
                    misses = (arc_misses(keys, capacity, scores, threshold)
                              if parent == "arc" else
                              s3fifo_misses(keys, capacity, scores >= threshold))
                    candidates[str(threshold)] = misses
                per_stream[name] = {"parent_reads": baseline, "ml_reads": candidates}
            ranking = []
            for threshold in THRESHOLDS:
                ratios = [d["ml_reads"][str(threshold)] / d["parent_reads"]
                          for d in per_stream.values()]
                ranking.append({"threshold": threshold, "worst_ratio": max(ratios),
                                "mean_ratio": sum(ratios) / len(ratios)})
            chosen = min(ranking, key=lambda r: (r["worst_ratio"], r["mean_ratio"]))
            entry[parent] = {"chosen": chosen, "ranking": ranking,
                             "validation": per_stream}
            print(capacity, parent, chosen, flush=True)
        result["capacities"][str(capacity)] = entry
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
