"""Build a standalone, offline-openable HTML results and code dashboard."""
import argparse
import csv
import html
import json
from pathlib import Path


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def esc(value):
    return html.escape(str(value))


def code_excerpt(path, first, last):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(f"{i + 1:3d} {line}" for i, line in enumerate(lines) if first <= i + 1 <= last)


def build(folder, output):
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((folder / "validation.json").read_text(encoding="utf-8"))
    summaries = read_csv(folder / "summary.csv")
    raw = read_csv(folder / "raw_results.csv")
    decisions = read_csv(folder / "decisions.csv")
    selected = ("fixed_4", "fixed_16", "rule", "ml", "guarded_ml")
    colors = {"fixed_4": "#111", "fixed_16": "#777", "rule": "#aaa", "ml": "#454545", "guarded_ml": "#999"}
    grouped = {(r["workload"], r["method"]): r for r in summaries}
    charts = []
    for kind in manifest["workloads"]:
        vals = [float(grouped[kind, m]["median_elapsed_s"]) for m in selected]
        maximum = max(vals)
        bars = []
        for i, (method, value) in enumerate(zip(selected, vals)):
            y = 18 + i * 43
            width = 540 * value / maximum
            bars.append(f'<text x="0" y="{y + 17}" class="barlabel">{esc(method)}</text>'
                        f'<rect x="125" y="{y}" width="{width:.1f}" height="26" fill="{colors[method]}"/>'
                        f'<text x="{130 + width:.1f}" y="{y + 18}" class="barvalue">{value:.3f} s</text>')
        charts.append(f'<section class="chart"><h3>{esc(kind.replace("_", " "))}</h3><svg viewBox="0 0 850 245" role="img" aria-label="Median times for {esc(kind)}">{"".join(bars)}</svg></section>')
    summary_table = ''.join('<tr>' + ''.join(f'<td>{esc(round(float(row[k]), 4) if k in ("median_elapsed_s", "min_elapsed_s", "max_elapsed_s", "median_ratio_to_paired_fixed4", "median_batch_latency_p95_s", "median_decision_p95_s") else row[k])}</td>' for k in
                               ("workload", "method", "runs", "median_elapsed_s", "min_elapsed_s", "max_elapsed_s", "median_ratio_to_paired_fixed4", "median_batch_latency_p95_s", "median_decision_p95_s")) + '</tr>' for row in summaries)
    phase_events = [d for d in decisions if d["workload"] == "phase_shift" and d["method"] == "guarded_ml" and d["repeat"] == "1"]
    decision_table = ''.join('<tr>' + ''.join(f'<td>{esc(round(float(event[k]), 6) if k in ("throughput", "mean_task_s", "task_cost_change", "decision_s") else event[k])}</td>' for k in
                                ("round", "old_chunk", "new_chunk", "tasks_completed", "throughput", "mean_task_s", "task_cost_change", "reason", "decision_s")) + '</tr>' for event in phase_events)
    comparison_path = folder / "existing_options_summary.csv"
    if comparison_path.exists():
        options = read_csv(comparison_path)
        option_table = ''.join('<tr>' + ''.join(f'<td>{esc(round(float(row[k]), 4) if k in ("median_elapsed_s", "median_ratio_to_paired_fixed4") else row[k])}</td>' for k in
                               ("workload", "method", "runs", "median_elapsed_s", "median_ratio_to_paired_fixed4")) + '</tr>' for row in options)
        comparison_html = f'''<h2 id="existing">Comparison with existing Python options</h2><p>Separate paired experiment on the same deterministic tasks and seeds. Each run includes process-pool creation and teardown. The built-in APIs have different dispatch paths; this is a practical end-to-end comparison, not an identical-internals microbenchmark.</p><div class="scroll"><table><thead><tr><th>Workload</th><th>Method</th><th>Runs</th><th>Median s</th><th>Ratio to paired fixed4</th></tr></thead><tbody>{option_table}</tbody></table></div>'''
    else:
        comparison_html = ''
    guard_count = sum(int(row["guard_events"]) for row in raw)
    code1 = esc(code_excerpt(root / "os_sched/scheduler_v2.py", 111, 159))
    code2 = esc(code_excerpt(root / "native/work_kernel.c", 1, 30))
    css = """body{font:16px Arial,sans-serif;margin:0;color:#111;background:#fff}header{padding:34px 6%;border-bottom:3px solid #111}h1{margin:0 0 9px;font-size:29px}h2{border-bottom:1px solid #777;padding-bottom:8px;margin-top:38px}h3{margin:0 0 12px}.wrap{max-width:1250px;margin:auto;padding:16px 5% 70px}.muted{color:#555}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.card{border:1px solid #888;padding:17px}.big{font-size:27px;font-weight:bold;margin:8px 0}.chartgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:15px}.chart{border:1px solid #aaa;padding:16px}.chart svg{width:100%;height:auto}.barlabel,.barvalue{font:15px Arial}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #bbb;padding:6px;text-align:left}th{background:#eee;position:sticky;top:0}pre{background:#f4f4f4;border:1px solid #bbb;padding:16px;overflow:auto;font:13px Consolas,monospace}a{color:#111}.note{border-left:4px solid #111;padding:12px 17px;background:#f3f3f3}nav a{margin-right:20px}footer{margin-top:40px;color:#555}code{font-family:Consolas,monospace}"""
    page=f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>OS Scheduler - Measured Results</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>{css}</style>
<header><h1>Machine-Learning-Assisted Adaptive Chunk Scheduling</h1><div>Actual implementation and measured results · {esc(manifest['system'])}</div></header>
<div class="wrap"><nav><a href="#results">Results</a><a href="#existing">Existing options</a><a href="#decisions">Live decisions</a><a href="#code">Code evidence</a><a href="#files">Open data</a></nav>
<div class="note"><strong>Scope:</strong> The saved decision tree changes application-level dispatch to OS worker processes during execution. It does not modify the Linux kernel scheduler. These runs do not establish a general speedup.</div>
<h2>Experiment record</h2><div class="cards">
<div class="card">Validation<div class="big">{esc(validation['status'])}</div><small>{validation['paired_groups']} paired workload/seed groups; matching checksums</small></div>
<div class="card">Measured runs<div class="big">{validation['raw_rows']}</div><small>{manifest['repeats']} repeats · {len(manifest['workloads'])} workloads · {len(manifest['methods'])} methods</small></div>
<div class="card">Trained tree<div class="big">{manifest['training']['holdout_exact_accuracy']:.0%}</div><small>Exact chunk-label accuracy on {manifest['training']['holdout_rows']} held-out windows</small></div>
<div class="card">Online guard actions<div class="big">{guard_count}</div><small>Measured cost-increase interventions</small></div>
<div class="card">Total pipeline<div class="big">{manifest['total_pipeline_s']:.0f} s</div><small>Includes offline profiling, training and test runs</small></div></div>
<p class="muted">{manifest['task_count']} tasks per run; {manifest['workers']} workers; synthetic base {manifest['synthetic_base_iterations']:,} C iterations; prime scan {manifest['prime_numbers_per_task']:,} integers/task. Training seeds, holdout seeds, and test seeds are disjoint.</p>
<h2 id="results">End-to-end time by workload</h2><p>Median wall-clock seconds across five paired seeds. Lower is better. Worker startup, dispatch, inference and teardown are included.</p><div class="chartgrid">{''.join(charts)}</div>
<h2>All methods and latency metrics</h2><p><code>Ratio to paired fixed_4 &lt; 1</code> means faster than fixed_4 for that workload; values are medians across matched seeds. Batch latency is dispatch-to-completion, not just C service time.</p>
<div class="scroll"><table><thead><tr><th>Workload</th><th>Method</th><th>Runs</th><th>Median s</th><th>Min s</th><th>Max s</th><th>Ratio to fixed4</th><th>Median batch p95 s</th><th>Decision p95 s</th></tr></thead><tbody>{summary_table}</tbody></table></div>
{comparison_html}
<h2 id="decisions">Actual online decisions: phase shift, first repeat</h2><p>The model is loaded from <code>model.json</code> and predicts after each completed round. The guard may override a prediction when mean measured task cost rises by more than 25%. All chunk values are bounded to 1–64.</p>
<div class="scroll"><table><thead><tr><th>Round</th><th>Old</th><th>New</th><th>Tasks</th><th>Throughput</th><th>Mean task s</th><th>Cost change</th><th>Reason</th><th>Decision s</th></tr></thead><tbody>{decision_table}</tbody></table></div>
<h2 id="code">Code evidence</h2><h3>Online decision path</h3><pre>{code1}</pre><h3>Compiled C tasks</h3><pre>{code2}</pre>
<h2 id="files">Openable raw evidence</h2><p>This HTML is standalone. In the project folder, the corresponding data are <code>{esc(folder.name)}/raw_results.csv</code>, <code>summary.csv</code>, <code>decisions.csv</code>, <code>training_data.csv</code>, <code>dataset.csv</code>, <code>model.json</code>, <code>manifest.json</code>, <code>validation.json</code> and <code>existing_options_raw.csv</code>. Open CSV files in Excel or a text editor.</p>
<footer>Generated only from saved experiment files. No fabricated result values.</footer></div></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(f"Created {output}")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder",type=Path)
    ap.add_argument("output",type=Path)
    args=ap.parse_args()
    build(args.folder,args.output)


if __name__=="__main__":
    main()
