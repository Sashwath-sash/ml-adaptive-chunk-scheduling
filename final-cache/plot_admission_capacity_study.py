"""Render a reproducible black-and-white figure from saved native read counts."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
STREAMS = ("BrowseTrace A", "BrowseTrace B", "NASA August", "Calgary")
SHORT = ("Browse A", "Browse B", "NASA Aug", "Calgary")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    selected = json.loads((ROOT / "results_selected_thresholds_2026-10-27.json").read_text())
    fig, axes = plt.subplots(2, 3, figsize=(12.8, 7.6), sharey=True)
    x = np.arange(len(STREAMS))
    for col, capacity in enumerate((256, 512, 1024)):
        entries = selected["capacities"][str(capacity)]
        for row, kind in enumerate(("original_fixed_threshold_direct_reads", "calibrated_direct_reads")):
            ax = axes[row, col]
            for shift, parent, hatch in ((-.18, "arc", "///"), (.18, "s3fifo", "xxx")):
                values = []
                for stream in STREAMS:
                    d = entries[stream][parent]
                    values.append(100 * (d["parent_direct_reads"] - d[kind]) /
                                  d["parent_direct_reads"])
                ax.bar(x + shift, values, width=.33, color="white", edgecolor="black",
                       hatch=hatch, linewidth=.8, label=parent.upper() if parent == "arc" else "S3-FIFO")
            ax.axhline(0, color="black", linewidth=.8)
            ax.grid(axis="y", color=".84", linewidth=.5)
            ax.set_axisbelow(True)
            ax.set_xticks(x, SHORT, rotation=20, ha="right", fontsize=8)
            ax.set_title(f"{capacity} entries ({capacity * 4 // 1024} MiB data)", fontsize=10)
            if col == 0:
                ax.set_ylabel(("Fixed 0.2" if row == 0 else "Validation-selected") +
                              "\nread-call reduction (%)", fontsize=9)
    axes[0, 0].legend(ncol=2, fontsize=8, loc="lower left")
    fig.suptitle("Learned admission versus each unfiltered parent; negative bars mean more reads", fontsize=12, y=.985)
    fig.tight_layout(rect=(0, .09, 1, .95), h_pad=2.3)
    fig.text(.5, .015, "Same frozen model; 4 held-out request streams. Capacity calibration is exploratory and post hoc.",
             ha="center", fontsize=8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(args.output)


if __name__ == "__main__":
    main()
