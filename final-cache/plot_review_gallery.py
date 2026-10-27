"""Rebuild monochrome Review 3 figures from saved, measured project results."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "final_review_materials" / "output" / "review_plots"
OUT.mkdir(parents=True, exist_ok=True)

with (ROOT / "results_hybrid_native_benchmark.json").open() as f:
    arc_data = json.load(f)
with (ROOT / "results_calgary_hybrid_arc_5runs.json").open() as f:
    arc_data.update(json.load(f))
with (ROOT / "results_hybrid_s3_native_benchmark.json").open() as f:
    s3_data = json.load(f)
with (ROOT / "final_review_materials/output/frozen_model_diagnostics.json").open() as f:
    diag = json.load(f)

keys = ["scripted", "llm", "nasa_aug", "calgary"]
labels = ["BrowseTrace A", "BrowseTrace B", "NASA web", "Calgary web"]
pairs = [("ARC", "ML + ARC", arc_data, "arc", "hybrid_arc"),
         ("S3-FIFO", "ML + S3-FIFO", s3_data, "s3fifo", "hybrid_s3fifo")]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
    "axes.labelsize": 10, "figure.facecolor": "white", "axes.facecolor": "white",
    "savefig.facecolor": "white", "axes.edgecolor": "black", "text.color": "black",
    "axes.labelcolor": "black", "xtick.color": "black", "ytick.color": "black",
})

def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)

def arr(data, field, policy):
    return np.array([data[k][policy][field] for k in keys], dtype=float)

# 1. Absolute direct-read calls, with baseline and ML paired inside each parent.
fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(4)
width = .2
styles = ["", "///", "xx", "\\\\"]
for j, (title, ml_title, data, parent, ml) in enumerate(pairs):
    for offset, label, policy in [(0, title, parent), (1, ml_title, ml)]:
        vals = arr(data, "direct_reads", policy)
        ax.bar(x + (j * 2 + offset - 1.5) * width, vals, width,
               color=["white", ".70", ".93", ".42"][j * 2 + offset],
               edgecolor="black", hatch=styles[j * 2 + offset], label=label)
ax.set_xticks(x, labels)
ax.set_ylabel("Aligned 4 KiB direct-read calls (lower is better)")
ax.set_ylim(0, 23000)
ax.set_title("Native cache replay: direct reads across four held-out streams")
ax.legend(ncol=4, loc="upper center", fontsize=8)
ax.grid(axis="y", alpha=.3)
save(fig, "01_direct_read_calls.png")

# 2. The within-parent read reduction, not a comparison between unlike parents.
fig, ax = plt.subplots(figsize=(9, 4.8))
for j, (title, _, data, parent, ml) in enumerate(pairs):
    base = arr(data, "direct_reads", parent)
    gain = 100 * (base - arr(data, "direct_reads", ml)) / base
    ax.bar(x + (j - .5) * .34, gain, .34, facecolor=["white", ".65"][j],
           edgecolor="black", hatch=["///", "xx"][j], label=f"ML vs {title}")
    for xx, yy in zip(x + (j - .5) * .34, gain):
        ax.text(xx, yy + .12, f"{yy:.1f}%", ha="center", va="bottom", fontsize=8)
ax.set_xticks(x, labels)
ax.set_ylim(0, 9)
ax.set_ylabel("Reduction in direct-read calls (%)")
ax.set_title("ML admission reduced reads in all eight saved comparisons")
ax.legend(frameon=False)
ax.grid(axis="y", alpha=.3)
save(fig, "02_read_reduction_percent.png")

# 3. Full five-run timing observations, so variability is visible.
fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=False)
for col, (title, ml_title, data, parent, ml) in enumerate(pairs):
    for row in range(2):
        ax = axes[row, col]
        for i in range(row * 2, row * 2 + 2):
            k = keys[i]
            for p_idx, (policy, desc) in enumerate([(parent, title), (ml, ml_title)]):
                vals = [r["wall_seconds"] for r in data[k][policy]["raw_runs"]]
                yy = i % 2 * 2 + p_idx
                ax.scatter(vals, np.full(len(vals), yy), facecolors="white" if p_idx == 0 else "black",
                           edgecolors="black", s=35, zorder=3)
                ax.plot(np.median(vals), yy, marker="|", color="black", markersize=18, markeredgewidth=2)
        ax.set_yticks(np.arange(4), [f"{labels[i]} · {p}" for i in range(row * 2, row * 2 + 2)
                                       for p in (title, ml_title)], fontsize=8)
        ax.set_xlabel("Measured loop time per run (seconds)")
        ax.grid(axis="x", alpha=.3)
        if row == 0:
            ax.set_title(f"{title} pair")
fig.suptitle("Five saved runs per policy; vertical tick = median", y=1.02)
save(fig, "03_timing_all_runs.png")

# 4. Median timing changes, with negative cases clearly below zero.
fig, ax = plt.subplots(figsize=(9, 5))
for j, (title, _, data, parent, ml) in enumerate(pairs):
    base = arr(data, "median_loop_seconds", parent)
    change = 100 * (base - arr(data, "median_loop_seconds", ml)) / base
    ax.bar(x + (j - .5) * .34, change, .34, facecolor=["white", ".65"][j],
           edgecolor="black", hatch=["///", "xx"][j], label=f"ML vs {title}")
    for xx, yy in zip(x + (j - .5) * .34, change):
        ax.text(xx, yy + (.3 if yy >= 0 else -.3), f"{yy:+.1f}%", ha="center",
                va="bottom" if yy >= 0 else "top", fontsize=8)
ax.axhline(0, color="black", lw=1)
ax.set_xticks(x, labels)
ax.set_ylim(-7, 12)
ax.set_ylabel("Median loop-time improvement (%)")
ax.set_title("Saved timing: two of eight ML comparisons are slower")
ax.legend(frameon=False)
ax.grid(axis="y", alpha=.3)
save(fig, "04_median_time_change.png")

# 5. Two objectives together, retaining slower-but-fewer-read cases.
fig, ax = plt.subplots(figsize=(8, 6))
for title, _, data, parent, ml in pairs:
    base_reads = arr(data, "direct_reads", parent)
    base_time = arr(data, "median_loop_seconds", parent)
    read_gain = 100 * (base_reads - arr(data, "direct_reads", ml)) / base_reads
    time_gain = 100 * (base_time - arr(data, "median_loop_seconds", ml)) / base_time
    for i in range(4):
        marker = "o" if title == "ARC" else "s"
        ax.scatter(read_gain[i], time_gain[i], marker=marker, s=75,
                   facecolors="white" if title == "ARC" else ".6", edgecolors="black")
        ax.annotate(f"{labels[i]} / {title}", (read_gain[i], time_gain[i]),
                    xytext=(5, 4 if i % 2 else -11), textcoords="offset points", fontsize=7)
ax.axhline(0, color="black", lw=1)
ax.axvline(0, color="black", lw=1)
ax.set_xlim(-.5, 9)
ax.set_ylim(-6, 12)
ax.set_xlabel("Direct-read reduction (%)")
ax.set_ylabel("Median loop-time improvement (%)")
ax.set_title("Read savings do not guarantee lower elapsed time")
ax.grid(alpha=.25)
save(fig, "05_reads_vs_time_tradeoff.png")

# 6. Hit rates derived from hits and misses, which are directly measured.
fig, ax = plt.subplots(figsize=(9, 5))
for j, (title, ml_title, data, parent, ml) in enumerate(pairs):
    for off, label, policy in [(0, title, parent), (1, ml_title, ml)]:
        h = np.array(
            [data[k][policy]["raw_runs"][0]["hits"] for k in keys], dtype=float)
        m = arr(data, "direct_reads", policy)
        hit_rate = 100 * h / (h + m)
        ax.plot(x, hit_rate, marker=["o", "s", "^", "D"][j * 2 + off],
                linestyle=["-", "--", ":", "-."][j * 2 + off], color="black",
                label=label)
ax.set_xticks(x, labels)
ax.set_ylabel("Cache hit rate (%)")
ax.set_ylim(45, 95)
ax.set_title("Observed hits / (hits + misses)")
ax.legend(ncol=2, fontsize=8)
ax.grid(alpha=.3)
save(fig, "06_cache_hit_rates.png")

# 7. Classifier quality: held-out streams, with prevalence explicitly shown.
fig, ax = plt.subplots(figsize=(9, 5))
dx = np.arange(4)
names = ["browsetrace_a", "browsetrace_b", "nasa_august", "calgary"]
for j, (field, desc, hatch, shade) in enumerate([
    ("roc_auc", "ROC AUC", "", "white"),
    ("average_precision", "Average precision", "///", ".7"),
    ("positive_fraction", "Reuse prevalence", "xx", ".9"),
]):
    vals = [diag[k][field] for k in names]
    ax.bar(dx + (j - 1) * .25, vals, .25, color=shade,
           edgecolor="black", hatch=hatch, label=desc)
ax.set_xticks(dx, labels)
ax.set_ylim(0, 1.07)
ax.set_ylabel("Fraction / score")
ax.set_title("Frozen model on four held-out streams")
ax.legend(ncol=3, fontsize=8)
ax.grid(axis="y", alpha=.3)
save(fig, "07_model_quality_and_prevalence.png")

# 8. Precision/recall at the operational threshold, with a caveat in index.
fig, ax = plt.subplots(figsize=(9, 5))
for j, (field, label) in enumerate([("precision", "Precision"), ("recall", "Recall")]):
    vals = [diag[k][field] for k in names]
    ax.bar(dx + (j - .5) * .35, vals, .35,
           color=["white", ".65"][j], edgecolor="black",
           hatch=["///", "xx"][j], label=label)
    for xx, yy in zip(dx + (j - .5) * .35, vals):
        ax.text(xx, yy + .012, f"{yy:.2f}", ha="center", fontsize=8)
ax.set_xticks(dx, labels)
ax.set_ylim(0, 1.1)
ax.set_ylabel("Score at 0.2 admission threshold")
ax.set_title("Model predicts reuse within the next 1,024 requests")
ax.legend(frameon=False)
ax.grid(axis="y", alpha=.3)
save(fig, "08_precision_recall_at_threshold.png")

# 9. Decision outcome composition on held-out streams.
fig, ax = plt.subplots(figsize=(9, 5))
bottom = np.zeros(4)
for label, field, color, hatch in [
    ("True positive", "tp", "white", ""),
    ("False positive", "fp", ".65", "///"),
    ("False negative", "fn", ".88", "xx"),
    ("True negative", "tn", ".3", "\\\\"),
]:
    vals = np.array([100 * diag[k][field] / diag[k]["requests"] for k in names])
    ax.bar(dx, vals, bottom=bottom, color=color, edgecolor="black", hatch=hatch, label=label)
    bottom += vals
ax.set_xticks(dx, labels)
ax.set_ylabel("Share of held-out requests (%)")
ax.set_title("Frozen-model decisions at score threshold 0.2")
ax.legend(ncol=2, fontsize=8, loc="upper center")
ax.set_ylim(0, 105)
save(fig, "09_classification_outcomes.png")

# 10. Warm-up checkpoints are exact cumulative miss counts at 1k, 2k, 4k requests.
fig, axes = plt.subplots(2, 2, figsize=(10, 7))
for i, k in enumerate(keys):
    ax = axes.flat[i]
    for title, ml_title, data, parent, ml in pairs:
        for policy, label, style in [(parent, title, "-"), (ml, ml_title, "--")]:
            raw = data[k][policy]["raw_runs"][0]
            pts = raw["prefix_misses"]
            if len(pts) != 3 or any(v < 0 for v in pts):
                continue
            ax.plot([1024, 2048, 4096], pts, marker="o" if title == "ARC" else "s",
                    linestyle=style, color="black", label=label)
    ax.set_title(labels[i])
    ax.set_xlabel("Requests processed")
    ax.set_ylabel("Cumulative misses")
    ax.grid(alpha=.3)
axes[0, 0].legend(fontsize=7)
fig.suptitle("Initial 4,096 requests: exact recorded miss checkpoints", y=1.02)
save(fig, "10_early_stream_misses.png")

# Keep the exact plotted aggregates convenient for independent inspection.
with (OUT / "plot_values.csv").open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["stream", "parent", "policy", "direct_reads", "hits", "median_loop_seconds",
                     "five_run_seconds", "read_reduction_vs_parent_pct", "median_time_improvement_vs_parent_pct"])
    for k, label in zip(keys, labels):
        for title, ml_title, data, parent, ml in pairs:
            base_reads = data[k][parent]["direct_reads"]
            base_time = data[k][parent]["median_loop_seconds"]
            for p, p_label in [(parent, title), (ml, ml_title)]:
                obj = data[k][p]
                writer.writerow([label, title, p_label, obj["direct_reads"], obj["raw_runs"][0]["hits"],
                                 obj["median_loop_seconds"],
                                 ";".join(str(v["wall_seconds"]) for v in obj["raw_runs"]),
                                 100 * (base_reads - obj["direct_reads"]) / base_reads,
                                 100 * (base_time - obj["median_loop_seconds"]) / base_time])

print(f"Wrote 10 PNGs and plot_values.csv to {OUT}")
