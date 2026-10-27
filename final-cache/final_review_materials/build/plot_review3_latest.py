"""Build submission figures from saved native and model evidence."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "final_review_materials" / "output" / "report3_latest_figures"
OUT.mkdir(parents=True, exist_ok=True)
STREAMS = ["BrowseTrace A", "BrowseTrace B", "NASA August", "Calgary"]
SHORT = ["Browse A", "Browse B", "NASA Aug", "Calgary"]

def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def finish(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUT / name)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": "black", "axes.labelcolor": "black",
                     "text.color": "black", "xtick.color": "black", "ytick.color": "black"})

# New October 27 native controls: each ML result has two matched comparisons.
controls = read("results_admission_controls_2026-10-27.json")["streams"]
fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.75), sharey=True)
x = np.arange(4)
for ax, (parent, second, hybrid, title) in zip(axes, [
    ("arc", "second_touch_arc", "hybrid_arc", "ARC parent"),
    ("s3fifo", "second_touch_s3fifo", "hybrid_s3fifo", "Local S3-FIFO parent"),
]):
    parent_gain = []
    second_gain = []
    for stream in STREAMS:
        p = controls[stream]["policies"]
        m = p[hybrid]["direct_reads"]
        parent_gain.append(100 * (p[parent]["direct_reads"] - m) / p[parent]["direct_reads"])
        second_gain.append(100 * (p[second]["direct_reads"] - m) / p[second]["direct_reads"])
    ax.bar(x-.17, parent_gain, .34, color="white", edgecolor="black", hatch="///", label="vs unfiltered parent")
    ax.bar(x+.17, second_gain, .34, color=".7", edgecolor="black", hatch="xx", label="vs second-touch")
    ax.set_xticks(x, SHORT, rotation=18, ha="right")
    ax.set_title(title)
    ax.set_ylim(0, 14)
    ax.grid(axis="y", color=".82", linewidth=.6)
    ax.set_axisbelow(True)
axes[0].set_ylabel("Fewer direct-read calls (%)")
axes[0].legend(loc="upper left", frameon=False, fontsize=8)
fig.suptitle("Learned admission at 512 entries: matched controls", fontsize=11)
fig.tight_layout(rect=(0, 0, 1, .94))
finish(fig, "01_latest_512_controls.png")

# Frozen classifier diagnostics, redrawn rather than embedding the older gallery image.
diag = read("final_review_materials/output/frozen_model_diagnostics.json")
dkeys = ["browsetrace_a", "browsetrace_b", "nasa_august", "calgary"]
fig, ax = plt.subplots(figsize=(8.4, 3.4))
for shift, key, label, color, hatch in [
    (-.24, "roc_auc", "ROC AUC", "white", ""),
    (0, "average_precision", "Average precision", ".78", "///"),
    (.24, "positive_fraction", "Reuse prevalence", ".45", "xx"),
]:
    vals = [diag[k][key] for k in dkeys]
    ax.bar(x+shift, vals, .23, color=color, edgecolor="black", hatch=hatch, label=label)
ax.set_ylim(0, 1.08)
ax.set_ylabel("Fraction or score")
ax.set_xticks(x, SHORT)
ax.grid(axis="y", color=".84", linewidth=.6)
ax.set_axisbelow(True)
ax.legend(loc="upper center", bbox_to_anchor=(.5, -.14), ncol=3, frameon=False, fontsize=8)
ax.set_title("Frozen model on the four final request streams")
fig.tight_layout(rect=(0,.08,1,1))
finish(fig, "02_latest_frozen_model.png")

# The timing source is the original five-run benchmark, not the one-run control sweep.
arc = read("results_hybrid_native_benchmark.json")
arc.update(read("results_calgary_hybrid_arc_5runs.json"))
s3 = read("results_hybrid_s3_native_benchmark.json")
timing_keys = ["scripted", "llm", "nasa_aug", "calgary"]
fig, ax = plt.subplots(figsize=(8.6, 3.6))
for shift, data, parent, hybrid, label, color, hatch in [
    (-.17, arc, "arc", "hybrid_arc", "ML + ARC", "white", "///"),
    (.17, s3, "s3fifo", "hybrid_s3fifo", "ML + S3-FIFO", ".67", "xx"),
]:
    values = [100*(data[k][parent]["median_loop_seconds"]-data[k][hybrid]["median_loop_seconds"])/data[k][parent]["median_loop_seconds"] for k in timing_keys]
    ax.bar(x+shift, values, .34, color=color, edgecolor="black", hatch=hatch, label=label)
    for xi, yi in zip(x+shift, values):
        ax.text(xi, yi + (.25 if yi >= 0 else -.3), f"{yi:+.1f}%", ha="center", va="bottom" if yi >= 0 else "top", fontsize=7.5)
ax.axhline(0, color="black", linewidth=.9)
ax.set_ylim(-6, 11)
ax.set_ylabel("Median request-loop time improvement (%)")
ax.set_xticks(x, SHORT)
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.grid(axis="y", color=".84", linewidth=.6)
ax.set_axisbelow(True)
ax.set_title("Five-run saved timing at 512 entries; positive is faster")
fig.tight_layout()
finish(fig, "03_latest_five_run_timing.png")

# Capacity grid generated from the later validation-selected experiment.
selected = read("results_selected_thresholds_2026-10-27.json")["capacities"]
fig, axes = plt.subplots(2, 3, figsize=(11.8, 6.0), sharey=True)
for col, capacity in enumerate((256, 512, 1024)):
    for row, field in enumerate(("original_fixed_threshold_direct_reads", "calibrated_direct_reads")):
        ax = axes[row, col]
        for shift, parent, hatch, color in [(-.17, "arc", "///", "white"), (.17, "s3fifo", "xx", ".7")]:
            values = []
            for stream in STREAMS:
                d = selected[str(capacity)][stream][parent]
                values.append(100*(d["parent_direct_reads"]-d[field])/d["parent_direct_reads"])
            ax.bar(x+shift, values, .32, color=color, edgecolor="black", hatch=hatch,
                   label="ARC" if parent=="arc" else "S3-FIFO")
        ax.axhline(0, color="black", linewidth=.8)
        ax.set_xticks(x, SHORT, rotation=18, ha="right", fontsize=7.4)
        ax.grid(axis="y", color=".84", linewidth=.5)
        ax.set_axisbelow(True)
        ax.set_title(f"{capacity} slots / {capacity*4//1024} MiB", fontsize=9)
        if col==0:
            ax.set_ylabel(("Fixed 0.2 cutoff" if row==0 else "Validation-selected cutoff")+"\nread saving (%)", fontsize=8)
axes[0,0].legend(frameon=False, ncol=2, fontsize=7, loc="lower left")
fig.suptitle("Capacity sensitivity: every saved parent comparison, including losses", fontsize=11)
fig.tight_layout(rect=(0,0,1,.95), h_pad=1.8)
finish(fig, "04_latest_capacity_sensitivity.png")

# The transfer stress is a distinct key-only experiment, so it gets its own compact figure.
stress = read("results_metacdn_sample10_100k_512.json")["streams"]["MetaCDN-sampled"]["policies"]
fig, ax = plt.subplots(figsize=(7.0, 3.0))
groups = [("ARC", "arc", "hybrid_arc"), ("Local S3-FIFO", "s3fifo", "hybrid_s3fifo")]
for i, (label, parent, hybrid) in enumerate(groups):
    ax.barh(i-.18, stress[parent]["direct_reads"], .32, color="white", edgecolor="black", hatch="///", label="Parent" if i==0 else None)
    ax.barh(i+.18, stress[hybrid]["direct_reads"], .32, color=".7", edgecolor="black", hatch="xx", label="ML admission" if i==0 else None)
ax.set_yticks(range(2), [g[0] for g in groups])
ax.invert_yaxis()
ax.set_xlim(0, 80000)
ax.set_xlabel("Native direct-read calls on sampled key-only stream")
ax.grid(axis="x", color=".84", linewidth=.6)
ax.set_axisbelow(True)
fig.suptitle("Transfer stress: missing URL and object-size features", y=.99)
fig.legend(loc="upper center", bbox_to_anchor=(.5,.90), frameon=False, ncol=2, fontsize=8)
fig.tight_layout(rect=(0,0,1,.80))
finish(fig, "05_latest_key_only_transfer.png")
