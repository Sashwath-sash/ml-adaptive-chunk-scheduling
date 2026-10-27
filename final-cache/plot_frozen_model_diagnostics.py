"""Rebuild ROC and calibration figures for the frozen admission classifier."""
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_curve

from cache_admission_probe import feature_rows, read_rows, reuse_labels


ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'final_review_materials' / 'output' / 'frozen_model_diagnostics_bw.png'
model = joblib.load(ROOT / 'results_cache_three_source_v1' / 'model.joblib')
specs = [
    ('BrowseTrace A', 'browsetrace_full_400_sessions.csv', 'last20', '-'),
    ('BrowseTrace B', 'browsetrace_llm_full_901.csv', 'last20', '--'),
    ('NASA web', 'nasa_aug_last_100k_cache.csv', 'all', ':'),
    ('Calgary web', 'calgary_last_100k_cache.csv', 'all', '-.'),
]
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9})
fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
for name, filename, split, linestyle in specs:
    rows = read_rows(ROOT / 'data' / filename)
    if split == 'last20':
        rows = rows[int(len(rows) * .8):]
    y = reuse_labels(rows, 1024)
    score = model.predict_proba(feature_rows(rows))[:, 1]
    fpr, tpr, _ = roc_curve(y, score)
    axes[0].plot(fpr, tpr, color='black', linestyle=linestyle, linewidth=1.5, label=name)
    observed, predicted = calibration_curve(y, score, n_bins=10, strategy='quantile')
    axes[1].plot(predicted, observed, color='black', linestyle=linestyle,
                 marker='o', markersize=3, linewidth=1.3, label=name)
axes[0].plot([0,1],[0,1],color='0.55',linewidth=.8)
axes[1].plot([0,1],[0,1],color='0.55',linewidth=.8)
axes[0].set(title='Future reuse discrimination',xlabel='False positive rate',ylabel='True positive rate')
axes[1].set(title='Probability calibration',xlabel='Predicted reuse probability',ylabel='Observed reuse fraction')
for ax in axes:
    ax.set(xlim=(0,1),ylim=(0,1))
    ax.grid(color='0.85',linewidth=.5)
axes[0].legend(frameon=False,loc='lower right',fontsize=8)
fig.suptitle('Frozen 100-stage classifier on held-out request slices')
fig.tight_layout()
OUT.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(OUT,dpi=200,bbox_inches='tight')
print(OUT)
