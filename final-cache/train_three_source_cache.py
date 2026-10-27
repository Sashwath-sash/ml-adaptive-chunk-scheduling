"""Exploratory three-source training; August NASA remains untouched until export."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from cache_admission_probe import feature_rows, read_rows, replay, reuse_labels


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output already exists")
    a = read_rows(Path("data/browsetrace_full_400_sessions.csv"))
    b = read_rows(Path("data/browsetrace_llm_full_901.csv"))
    c = read_rows(Path("data/nasa_jul_last_300k_cache.csv"))
    groups = {
        "scripted": (a[:int(len(a) * .6)], a[int(len(a) * .6):int(len(a) * .8)]),
        "llm": (b[:int(len(b) * .6)], b[int(len(b) * .6):int(len(b) * .8)]),
        "nasa_july": (c[:150_000], c[150_000:200_000]),
    }
    train_x = np.concatenate([feature_rows(train) for train, _ in groups.values()])
    train_y = np.concatenate([reuse_labels(train, 1024) for train, _ in groups.values()])
    model = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15,
        min_samples_leaf=40, learning_rate=.07, l2_regularization=2, random_state=811)
    model.fit(train_x, train_y)
    thresholds = (.2, .4, .6)
    stages = (40, 100)
    validation = {}
    scores = {}
    for name, (_, val) in groups.items():
        validation[name] = {policy: replay(val, policy, 512)["misses"]
                            for policy in ("lru", "second_touch", "two_queue", "tinylfu")}
        scores[name] = {i: pred[:, 1] for i, pred in
                        enumerate(model.staged_predict_proba(feature_rows(val)), 1) if i in stages}
    candidates = []
    for stage in stages:
        for threshold in thresholds:
            misses = {name: replay(val, "ml", 512, scores[name][stage], threshold)["misses"]
                      for name, (_, val) in groups.items()}
            ratios = [misses[name] / min(validation[name].values()) for name in groups]
            candidates.append({"stages": stage, "threshold": threshold, "misses": misses,
                               "worst_ratio": max(ratios), "mean_ratio": sum(ratios) / len(ratios)})
    chosen = min(candidates, key=lambda item: (item["worst_ratio"], item["mean_ratio"], item["stages"]))
    export = {"baseline": float(model._baseline_prediction[0, 0]), "trees": []}
    for stage in model._predictors[:chosen["stages"]]:
        export["trees"].append([[int(n["feature_idx"]), float(n["num_threshold"]),
            int(n["left"]), int(n["right"]), bool(n["is_leaf"]), float(n["value"]),
            bool(n["missing_go_to_left"])] for n in stage[0].nodes])
    info = {"capacity_entries": 512, "chosen": chosen, "validation": validation,
            "train_val_counts": {name: [len(train), len(val)] for name, (train, val) in groups.items()},
            "nasa_july_tail_excluded": 100_000,
            "note": "Exploratory after observing old model fail on July tail; August is subsequent untouched test."}
    args.output.mkdir(parents=True)
    joblib.dump(model, args.output / "model.joblib")
    (args.output / "hgb.json").write_text(json.dumps(export))
    (args.output / "results.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
