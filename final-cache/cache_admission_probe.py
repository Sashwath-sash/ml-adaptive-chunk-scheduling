"""Held-out ML cache-admission probe on a public request trace.

This is trace replay, not a Linux kernel cache or measured network speedup.
"""
import argparse
import csv
import json
import math
from collections import Counter, OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return [(r["cache_key"], max(0, int(r["object_size_bytes"])))
                for r in csv.DictReader(stream)]


def feature_rows(rows):
    counts = Counter()
    hosts = Counter()
    last = {}
    features = []
    for index, (key, size) in enumerate(rows):
        parsed = urlsplit(key)
        host = parsed.netloc
        path = parsed.path.lower()
        static = int(path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2")))
        seen = counts[key]
        age = index - last[key] if key in last else len(rows) + 1
        features.append([math.log1p(size), math.log1p(seen), math.log1p(age),
                         math.log1p(hosts[host]), len(path), static,
                         int(bool(parsed.query)), len(key)])
        counts[key] += 1
        hosts[host] += 1
        last[key] = index
    return np.asarray(features, dtype=np.float32)


def reuse_labels(rows, horizon):
    next_seen = {}
    labels = [0] * len(rows)
    for index in range(len(rows) - 1, -1, -1):
        key = rows[index][0]
        labels[index] = int(key in next_seen and next_seen[key] - index <= horizon)
        next_seen[key] = index
    return np.asarray(labels, dtype=np.uint8)


def replay(rows, policy, capacity, scores=None, threshold=0.5):
    if policy == "two_queue":
        return replay_two_queue(rows, capacity)
    if policy == "tinylfu":
        return replay_tinylfu(rows, capacity)
    cache = OrderedDict()
    seen = Counter()
    hits = 0
    for index, (key, _) in enumerate(rows):
        seen[key] += 1
        if key in cache:
            hits += 1
            cache.move_to_end(key)
            continue
        if policy == "lru":
            admit = True
        elif policy == "second_touch":
            admit = seen[key] >= 2
        elif policy == "ml":
            admit = scores[index] >= threshold
        elif policy == "lfu":
            admit = True
        else:
            raise ValueError(policy)
        if not admit:
            continue
        if len(cache) >= capacity:
            if policy == "lfu":
                victim = min(cache, key=lambda k: (seen[k], cache[k]))
                del cache[victim]
            else:
                cache.popitem(last=False)
        cache[key] = index
    return {"requests": len(rows), "hits": hits, "misses": len(rows) - hits,
            "hit_rate": hits / len(rows), "cache_entries": capacity}


def replay_two_queue(rows, capacity):
    recent = OrderedDict()
    frequent = OrderedDict()
    ghost = OrderedDict()
    recent_limit = max(1, capacity // 4)
    hits = 0
    for key, _ in rows:
        if key in frequent:
            hits += 1
            frequent.move_to_end(key)
            continue
        if key in recent:
            hits += 1
            del recent[key]
            frequent[key] = None
        elif key in ghost:
            del ghost[key]
            frequent[key] = None
        else:
            recent[key] = None
        if len(recent) > recent_limit:
            victim, _ = recent.popitem(last=False)
            ghost[victim] = None
            if len(ghost) > capacity:
                ghost.popitem(last=False)
        while len(recent) + len(frequent) > capacity:
            frequent.popitem(last=False)
    return {"requests": len(rows), "hits": hits, "misses": len(rows) - hits,
            "hit_rate": hits / len(rows), "cache_entries": capacity}


def replay_tinylfu(rows, capacity):
    cache = OrderedDict()
    frequency = Counter()
    hits = 0
    for index, (key, _) in enumerate(rows):
        if index and index % 4096 == 0:
            frequency = Counter({k: v // 2 for k, v in frequency.items() if v >= 2})
        frequency[key] += 1
        if key in cache:
            hits += 1
            cache.move_to_end(key)
            continue
        if len(cache) == capacity:
            victim = next(iter(cache))
            if frequency[key] < frequency[victim]:
                continue
            cache.popitem(last=False)
        cache[key] = None
    return {"requests": len(rows), "hits": hits, "misses": len(rows) - hits,
            "hit_rate": hits / len(rows), "cache_entries": capacity}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", type=Path, default=Path("data/browsetrace_full_400_sessions.csv"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--capacity", type=int, default=512)
    ap.add_argument("--model", choices=("hgb", "tree"), default="hgb")
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output already exists")
    rows = read_rows(args.trace)
    a, b = int(len(rows) * .6), int(len(rows) * .8)
    train, val, test = rows[:a], rows[a:b], rows[b:]
    model = (HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15,
        min_samples_leaf=40, learning_rate=.07, l2_regularization=2,
        random_state=811) if args.model == "hgb" else
        DecisionTreeClassifier(max_depth=8, min_samples_leaf=80,
                               random_state=811))
    model.fit(feature_rows(train), reuse_labels(train, args.capacity * 2))
    val_scores = model.predict_proba(feature_rows(val))[:, 1]
    threshold_candidates = (.1, .2, .3, .4, .5, .6, .7, .8, .9)
    val_ml = {str(t): replay(val, "ml", args.capacity, val_scores, t)
              for t in threshold_candidates}
    chosen = min(threshold_candidates, key=lambda t: val_ml[str(t)]["misses"])
    test_scores = model.predict_proba(feature_rows(test))[:, 1]
    result = {"scope": "trace replay of public browser cache requests; not physical disk reads",
              "model_type": args.model,
              "trace": str(args.trace), "train": len(train), "validation": len(val),
              "test_count": len(test), "capacity_entries": args.capacity,
              "chosen_threshold_on_validation": chosen,
              "validation_ml": val_ml,
              "test": {policy: replay(test, policy, args.capacity,
                                     test_scores if policy == "ml" else None, chosen)
                       for policy in ("lru", "second_touch", "lfu", "two_queue", "tinylfu", "ml")}}
    args.output.mkdir(parents=True)
    joblib.dump(model, args.output / "model.joblib")
    np.save(args.output / "test_scores.npy", test_scores)
    (args.output / "test_scores.json").write_text(json.dumps(test_scores.tolist()))
    if args.model == "tree":
        tree = model.tree_
        nodes = []
        for i in range(tree.node_count):
            values = tree.value[i][0]
            nodes.append({"feature": int(tree.feature[i]),
                          "threshold": float(tree.threshold[i]),
                          "left": int(tree.children_left[i]),
                          "right": int(tree.children_right[i]),
                          "probability": float(values[1] / values.sum())})
        (args.output / "tree.json").write_text(json.dumps(nodes))
    else:
        compact = {"baseline": float(model._baseline_prediction[0, 0]), "trees": []}
        for stage in model._predictors:
            nodes = []
            for node in stage[0].nodes:
                nodes.append([int(node["feature_idx"]), float(node["num_threshold"]),
                              int(node["left"]), int(node["right"]),
                              bool(node["is_leaf"]), float(node["value"]),
                              bool(node["missing_go_to_left"])])
            compact["trees"].append(nodes)
        (args.output / "hgb.json").write_text(json.dumps(compact))
    (args.output / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "validation_ml"}, indent=2))


if __name__ == "__main__":
    main()
