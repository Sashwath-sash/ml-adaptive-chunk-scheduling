"""Independent classifier and Python-cache check for the sampled MetaCDN stress test."""
import argparse
import hashlib
import io
import itertools
import json
from pathlib import Path

import joblib
import numpy as np
import zstandard
from sklearn.metrics import average_precision_score, roc_auc_score

from arc_reference_probe import arc_misses
from cache_admission_probe import feature_rows, reuse_labels
from s3fifo_reference_probe import simulate


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/metaCDN.sample10.txt.zst")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    manifest = json.loads((ROOT / "cache_native_input_metacdn_sample10_100k/manifest.json").read_text())
    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    assert digest == manifest["compressed_sha256"]
    with args.source.open("rb") as raw:
        with zstandard.ZstdDecompressor().stream_reader(raw) as stream:
            reader = io.TextIOWrapper(stream, encoding="utf-8")
            rows = [(key.strip(), 0) for key in itertools.islice(reader, manifest["rows"])]
    assert len(rows) == manifest["rows"]
    keys = [key for key, _ in rows]
    model = joblib.load(ROOT / "results_cache_three_source_v1/model.joblib")
    scores = model.predict_proba(feature_rows(rows))[:, 1]
    labels = reuse_labels(rows, 1024)
    admit = scores >= .2
    independent = {
        "arc": arc_misses(keys, 512),
        "hybrid_arc": arc_misses(keys, 512, scores, .2),
        "s3fifo": simulate(keys, 512),
        "hybrid_s3fifo": simulate(keys, 512, admit),
    }
    native = json.loads((ROOT / "results_metacdn_sample10_100k_512.json").read_text())
    native = native["streams"]["MetaCDN-sampled"]["policies"]
    for policy, count in independent.items():
        assert native[policy]["direct_reads"] == count, policy
    result = {
        "source_sha256": digest, "rows": len(rows), "unique_keys": len(set(keys)),
        "positive_fraction_future_1024": float(np.mean(labels)),
        "score_mean": float(np.mean(scores)),
        "score_quantiles_0_10_50_90_100": np.quantile(scores, [0, .1, .5, .9, 1]).tolist(),
        "admit_fraction_threshold_0_2": float(np.mean(admit)),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "average_precision": float(average_precision_score(labels, scores)),
        "precision_threshold_0_2": float(np.mean(labels[admit])),
        "recall_threshold_0_2": float(np.mean(admit[labels == 1])),
        "independent_reference_read_counts": independent,
        "scope": "Key-only, sampled, out-of-domain stress test; not a like-for-like CDN benchmark",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
