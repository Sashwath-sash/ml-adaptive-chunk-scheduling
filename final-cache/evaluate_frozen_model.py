"""Evaluate the saved admission model on chronological held-out request slices.

These are classifier diagnostics, distinct from the native cache-read benchmark.
The reuse label is right-censored at the end of each finite slice.
"""
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from cache_admission_probe import feature_rows, read_rows, reuse_labels


def main():
    root = Path(__file__).resolve().parent
    model = joblib.load(root / 'results_cache_three_source_v1' / 'model.joblib')
    specs = {
        'browsetrace_a': ('browsetrace_full_400_sessions.csv', 'last20'),
        'browsetrace_b': ('browsetrace_llm_full_901.csv', 'last20'),
        'nasa_august': ('nasa_aug_last_100k_cache.csv', 'all'),
        'calgary': ('calgary_last_100k_cache.csv', 'all'),
    }
    output = {}
    for name, (filename, split) in specs.items():
        rows = read_rows(root / 'data' / filename)
        if split == 'last20':
            rows = rows[int(len(rows) * .8):]
        x = feature_rows(rows)
        y = reuse_labels(rows, 1024)
        prob = model.predict_proba(x)[:, 1]
        pred = prob >= .2
        tp = int(np.sum(pred & (y == 1)))
        fp = int(np.sum(pred & (y == 0)))
        fn = int(np.sum(~pred & (y == 1)))
        tn = int(np.sum(~pred & (y == 0)))
        output[name] = {
            'requests': len(rows),
            'positive_fraction': float(np.mean(y)),
            'roc_auc': float(roc_auc_score(y, prob)),
            'average_precision': float(average_precision_score(y, prob)),
            'brier_score': float(brier_score_loss(y, prob)),
            'log_loss': float(log_loss(y, prob)),
            'threshold': .2,
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': tp / (tp + fp),
            'recall': tp / (tp + fn),
        }
        print(name, json.dumps(output[name]), flush=True)
    dest = root / 'final_review_materials' / 'output' / 'frozen_model_diagnostics.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(dest)
    dest.write_text(json.dumps(output, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
