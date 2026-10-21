"""Build a local, self-contained evidence page from saved v6 benchmark data."""
import html
import json
from pathlib import Path

from .experiment_v6 import KINDS_V6, csv_read
from .scheduler_v6 import FEATURES


def esc(value):
    return html.escape(str(value))


def main():
    folder = Path("results_live_v6")
    summary = csv_read(folder / "test_summary.csv")
    manifest = json.loads((folder / "test_manifest.json").read_text(encoding="utf-8"))
    model = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    runtime = json.loads((folder / "model_runtime_only.json").read_text(encoding="utf-8"))
    rows = {(row["kind"], row["method"]): row for row in summary}
    labels = {"uniform": "Uniform", "moderate": "Moderate", "high": "High variation",
              "phase_shift": "Phase shift", "prime_scan": "Prime scan", "late_heavy": "Late heavy"}
    methods = [("cost32_no_pilot", "Cost 32, no pilot", "square"),
               ("live_tree", "Mixed tree + pilot", "circle"),
               ("live_tree_runtime_only", "Measured-only tree + pilot", "diamond")]
    svg = ['<svg viewBox="0 0 850 380" role="img" aria-label="Paired full-run ratios by workload">']
    lo, hi, x0, x1 = 0.80, 1.10, 220, 770
    x = lambda value: x0 + (value - lo) / (hi - lo) * (x1 - x0)
    for tick in (0.8, 0.9, 1.0, 1.1):
        xx = x(tick)
        svg.append(f'<line x1="{xx:.1f}" y1="25" x2="{xx:.1f}" y2="340" stroke="{ "#111" if tick == 1 else "#bbb" }" stroke-width="{2 if tick == 1 else 1}"/>')
        svg.append(f'<text x="{xx:.1f}" y="363" text-anchor="middle" font-size="13">{tick:.2f}</text>')
    for i, kind in enumerate(KINDS_V6):
        yy = 56 + i * 48
        svg.append(f'<text x="5" y="{yy+4}" font-size="14">{esc(labels[kind])}</text>')
        for j, (method, _, shape) in enumerate(methods):
            ratio = float(rows[(kind, method)]["median_paired_ratio"])
            xx = x(min(hi, max(lo, ratio)))
            y = yy + (j - 1) * 11
            if shape == "circle":
                svg.append(f'<circle cx="{xx:.1f}" cy="{y}" r="5" fill="#111"/>')
            elif shape == "square":
                svg.append(f'<rect x="{xx-5:.1f}" y="{y-5}" width="10" height="10" fill="white" stroke="#111" stroke-width="1.5"/>')
            else:
                svg.append(f'<polygon points="{xx:.1f},{y-6} {xx+6:.1f},{y} {xx:.1f},{y+6} {xx-6:.1f},{y}" fill="#888"/>')
    svg.append('</svg>')
    table_rows = []
    for kind in KINDS_V6:
        cells = [f'<th scope="row">{esc(labels[kind])}</th>']
        for method, _, _ in methods:
            row = rows[(kind, method)]
            cells.append(f'<td>{float(row["median_paired_ratio"]):.3f} '
                         f'<small>({row["paired_wins"]}/{row["n"]} wins)</small></td>')
        table_rows.append('<tr>' + ''.join(cells) + '</tr>')
    feature_rows = []
    for i, name in enumerate(FEATURES):
        source = "Measured from completed C pilot" if i < 6 else "Known remaining-task metadata"
        feature_rows.append(f'<tr><td>{esc(name)}</td><td>{source}</td></tr>')
    mixed_root = model["tree"]["root"]
    mixed_splits = []
    def walk(node):
        if "feature" in node:
            mixed_splits.append(FEATURES[node["feature"]])
            walk(node["left"])
            walk(node["right"])
    walk(mixed_root)
    used = ', '.join(sorted(set(mixed_splits)))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Measured scheduler evidence</title><style>
body{{font:16px/1.45 Georgia,serif;max-width:1050px;margin:36px auto;padding:0 24px;color:#111;background:#fff}}
h1,h2{{font-family:Arial,sans-serif;line-height:1.16}}h1{{font-size:2rem;margin-bottom:6px}}h2{{margin-top:34px;border-bottom:1px solid #bbb;padding-bottom:5px}}
.lead{{font-size:1.1rem;max-width:850px}}.meta{{font-family:Arial,sans-serif;color:#444;font-size:.9rem}}
table{{border-collapse:collapse;width:100%;font-size:.95rem}}th,td{{border-bottom:1px solid #ccc;text-align:left;padding:8px 10px;vertical-align:top}}th{{background:#f1f1f1}}
svg{{max-width:100%;height:auto;border:1px solid #ddd}}code,pre{{font-family:Consolas,monospace}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:14px}}
.note{{border-left:4px solid #444;padding:8px 14px;background:#f7f7f7}}a{{color:#111}}
</style></head><body>
<h1>Adaptive chunk scheduling: measured evidence</h1>
<p class="lead">Real Linux worker processes execute a compiled C kernel. The application controller compares a fixed four-task baseline, cost-aware batching, and two trees that make a choice after a completed pilot. The Linux kernel scheduler is not modified.</p>
<p class="meta">{manifest['groups']} matched final-test groups · {manifest['raw_rows']} timed final-test runs · {len(model['train_seeds']) * len(KINDS_V6) * len(model['train_scales'])} training groups · {len(model['validation_seeds']) * len(KINDS_V6)} validation groups · equal checksums throughout</p>
<h2>End-to-end results on unseen seeds and scale</h2>
<p>Each mark is the median of within-seed complete-run time ratios to fixed chunk four. Left of 1.00 means faster; right means slower. □ cost-aware 32 without a pilot; ● mixed tree; ◆ measured-only tree.</p>
{''.join(svg)}
<table><thead><tr><th>Workload</th><th>Cost 32 / no pilot</th><th>Mixed tree / pilot</th><th>Measured-only / pilot</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table>
<p class="note"><strong>Interpretation:</strong> The mixed tree wins on the constructed late-heavy workload but is not the fastest approach there; cost-aware 32 without the pilot is faster. On ordinary workloads the pilot and its decision can erase gains. Bootstrap intervals and all timing rows are in the saved CSV files.</p>
<h2>What the tree actually learned</h2>
<p>The mixed CART was trained on repeated <em>whole-invocation</em> candidate timings. Validation selected a depth cap of {model['chosen_hyperparameters']['depth_cap']} and minimum leaf size {model['chosen_hyperparameters']['min_leaf']} from 24 combinations. Its actual split features are: <strong>{esc(used)}</strong>. None are live pilot measurements in this selected model. This is an observed result, not a claim that the pilot was useful for these tasks.</p>
<p>The measured-only ablation was given just six real pilot timings. Validation selected a depth cap of {runtime['chosen_hyperparameters']['depth_cap']}; both leaves predict fixed four. A short pilot cannot observe the hidden expensive task near the end, so it cannot reliably choose early cost ordering by itself.</p>
<table><thead><tr><th>Model input</th><th>Source</th></tr></thead><tbody>{''.join(feature_rows)}</tbody></table>
<h2>Protocol and limits</h2>
<p>Training uses seeds 6001–6004 at two workload scales; validation uses 7001–7003 at an unseen middle scale; final testing uses 8001–8010 at another unseen scale. Every method runs on the same 192 tasks with two workers, and method order is shuffled within each group. The primary timer includes feature extraction, pilot execution, inference, batching, pool startup, dispatch, and teardown. Offline fitting is excluded because the saved model is reused.</p>
<p>These are generated workloads on one WSL2 machine. The late-heavy pattern was deliberately constructed to stress a costly task near the queue tail; it is not a production trace. The pilot is a blocking round, and the selected tree does not show a general speedup. Numerical differences of a few percent require more hosts and longer runs before generalization.</p>
<h2>Inspect the real artifacts</h2>
<ul><li><a href="test_raw.csv">480 raw final-test rows</a></li><li><a href="test_summary.csv">Paired summary and bootstrap intervals</a></li><li><a href="test_manifest.json">Seeds, timing boundary, system and checks</a></li><li><a href="model.json">Mixed tree with split thresholds</a></li><li><a href="model_runtime_only.json">Measured-only tree</a></li><li><a href="train_raw.csv">384 measured training runs</a></li><li><a href="validation_model_scores.csv">Depth and leaf-size validation scores</a></li><li><a href="live_demo_v6.json">Fresh live trace after running the demo</a></li></ul>
<pre>bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.verify_live_v6
python3 -m os_sched.live_demo_v6 --kind late_heavy</pre>
<p class="meta">Related prior work: <a href="https://github.com/unibas-dmi-hpc/LB4OMP">LB4OMP</a> and <a href="https://github.com/petuum/adaptdl">AdaptDL</a> demonstrate that adaptive and learning-based scheduling already exist. This project does not claim first invention.</p>
</body></html>'''
    target = folder / "dashboard.html"
    target.write_text(page, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
