"""Create a standalone browser page from the measured improvement CSVs."""
import argparse
import csv
import html
import json
from pathlib import Path


def read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    manifest = json.loads((args.folder / "manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((args.folder / "validation.json").read_text(encoding="utf-8"))
    summary = read(args.folder / "summary.csv")
    decisions = read(args.folder / "decisions.csv")
    lookup = {(r["workload"], r["method"]): r for r in summary}
    shown = ("fixed_4", "fixed_16", "ml", "ml_once", "pool_map_16", "process_executor_16")
    esc = html.escape
    cards = []
    for kind in manifest["workloads"]:
        rows = [lookup[kind, method] for method in shown]
        max_time = max(float(r["median_s"]) for r in rows)
        bars = []
        for index, row in enumerate(rows):
            method = row["method"]
            value = float(row["median_s"])
            y = 18 + 45 * index
            width = 470 * value / max_time
            color = "#111" if method == "ml_once" else "#aaa" if method == "ml" else "#666"
            bars.append(f'<text x="0" y="{y + 18}">{esc(method)}</text>'
                        f'<rect x="160" y="{y}" width="{width:.1f}" height="28" fill="{color}"/>'
                        f'<text x="{168 + width:.1f}" y="{y + 19}">{value:.3f} s</text>')
        cards.append(f'<section><h3>{esc(kind.replace("_", " "))}</h3><svg viewBox="0 0 840 305" role="img" aria-label="Measured times for {esc(kind)}">{"".join(bars)}</svg></section>')
    trs = []
    for row in summary:
        vals = [row["workload"], row["method"], row["runs"],
                f'{float(row["median_s"]):.4f}',
                f'{float(row["median_ratio_to_paired_fixed4"]):.3f}',
                f'{float(row["median_ratio_to_paired_old_tree"]):.3f}',
                f'{float(row["median_decision_p95_s"]) * 1e6:.1f}']
        trs.append('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in vals) + '</tr>')
    samples = [r for r in decisions if r["method"] == "ml_once" and r["workload"] == "high"]
    sample_rows = ''.join(f'<tr><td>{esc(r["repeat"])}</td><td>{esc(r["old_chunk"])} → {esc(r["new_chunk"])}</td>'
                          f'<td>{esc(r["tasks_completed"])}</td><td>{float(r["decision_s"]) * 1e6:.1f}</td></tr>'
                          for r in samples)
    css = '''body{font:16px Arial,sans-serif;color:#111;margin:0}header{border-bottom:3px solid #111;padding:30px 6%}h1{margin:0 0 8px;font-size:29px}.wrap{max-width:1250px;margin:auto;padding:15px 5% 60px}h2{margin-top:36px;border-bottom:1px solid #777;padding-bottom:7px}.note{background:#f2f2f2;border-left:4px solid #111;padding:12px 16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(475px,1fr));gap:15px}.grid section{border:1px solid #aaa;padding:16px}.grid svg{width:100%;height:auto;font:15px Arial}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{border:1px solid #bbb;padding:7px;text-align:left}th{background:#eee}code{font:14px Consolas,monospace}nav a{color:#111;margin-right:18px}'''
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Improved Adaptive Scheduler — Measured Results</title><style>{css}</style>
<header><h1>Improved adaptive chunk scheduler</h1><div>One online tree decision, then bulk dispatch · Linux measurements</div></header>
<div class="wrap"><nav><a href="#charts">Charts</a><a href="#table">All methods</a><a href="#trace">Actual decisions</a><a href="#files">Evidence files</a></nav>
<p class="note">The one-decision version reduces synchronization and was faster than the previous repeated-round tree in this paired experiment. It did <strong>not</strong> beat the best fixed or standard-library option in every workload. This is application-level scheduling, not a Linux kernel patch.</p>
<p><strong>{validation['raw_rows']} timed runs</strong> in {validation['paired_groups']} paired workload/seed groups; {len(manifest['methods'])} methods; matching checksums; {validation['status']} data audit. Each run includes worker startup, dispatch, inference and teardown.</p>
<h2 id="charts">End-to-end time</h2><p>Median seconds across five paired test seeds; lower is better. Dark bar = one-decision tree, pale bar = old repeated-round tree.</p><div class="grid">{''.join(cards)}</div>
<h2 id="table">All methods</h2><p>Paired ratio below 1 means faster than that baseline. Decision p95 is shown in microseconds; standard APIs have no custom tree decision.</p>
<div class="scroll"><table><thead><tr><th>Workload</th><th>Method</th><th>Runs</th><th>Median s</th><th>Ratio to fixed 4</th><th>Ratio to old tree</th><th>Decision p95 μs</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
<h2 id="trace">Actual online decisions, high-variance workload</h2><p>The saved tree was loaded before each run. It predicts after 16 completed pilot tasks, and the remaining 176 tasks are dispatched in one bulk stage.</p>
<table><thead><tr><th>Repeat</th><th>Chunk change</th><th>Completed at decision</th><th>Decision μs</th></tr></thead><tbody>{sample_rows}</tbody></table>
<h2 id="files">Openable evidence</h2><p>Source: <code>os_sched/scheduler_v3.py</code>. Data in <code>results_improvement/raw.csv</code>, <code>summary.csv</code>, <code>decisions.csv</code>, <code>validation.json</code>, <code>tests.txt</code> and <code>live_demo.json</code>. The old experiment remains in <code>results_final_linux</code>. All values on this page come from saved measured files.</p></div></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print("Created", args.output)


if __name__ == "__main__":
    main()
