"""Standalone browser report for balanced batching and its targeted stress test."""
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
    ap.add_argument("--project", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.project
    stress = root / "results_straggler_corrected"
    broad = root / "results_balanced_corrected"
    sv = json.loads((stress / "validation.json").read_text(encoding="utf-8"))
    bv = json.loads((broad / "validation.json").read_text(encoding="utf-8"))
    ssum, sraw, bsum = read(stress / "summary.csv"), read(stress / "raw.csv"), read(broad / "summary.csv")
    esc = html.escape
    methods = ("fixed_4", "fixed_16", "pool_map_16", "balanced_8", "balanced_16", "balanced_32", "balanced_fifo_16")
    sl = {r["method"]: r for r in ssum}
    max_s = max(float(sl[m]["median_s"]) for m in methods)
    bars = []
    for i, method in enumerate(methods):
        value = float(sl[method]["median_s"])
        y = 20 + i * 48
        width = 580 * value / max_s
        color = "#111" if method == "balanced_32" else "#aaa" if method == "fixed_4" else "#666"
        bars.append(f'<text x="0" y="{y + 20}">{method}</text><rect x="180" y="{y}" width="{width:.1f}" height="30" fill="{color}"/><text x="{188 + width:.1f}" y="{y + 21}">{value:.3f} s</text>')
    fixed = {int(r["seed"]): float(r["elapsed_s"]) for r in sraw if r["method"] == "fixed_4"}
    selected = {int(r["seed"]): float(r["elapsed_s"]) for r in sraw if r["method"] == "balanced_32"}
    paired = ''.join(f'<tr><td>{seed}</td><td>{fixed[seed]:.4f}</td><td>{selected[seed]:.4f}</td><td>{selected[seed]/fixed[seed]:.3f}</td></tr>' for seed in sorted(fixed))
    broadrows = []
    for kind in ("uniform", "moderate", "high", "phase_shift", "prime_scan"):
        f = next(r for r in bsum if r["workload"] == kind and r["method"] == "fixed_4")
        l = next(r for r in bsum if r["workload"] == kind and r["method"] == "balanced_32")
        q = next(r for r in bsum if r["workload"] == kind and r["method"] == "balanced_fifo_16")
        broadrows.append(f'<tr><td>{esc(kind)}</td><td>{float(f["median_s"]):.3f}</td><td>{float(l["median_s"]):.3f}</td><td>{float(l["median_ratio_to_paired_fixed4"]):.3f}</td><td>{float(q["median_ratio_to_paired_fixed4"]):.3f}</td></tr>')
    css = '''body{font:16px Arial,sans-serif;color:#111;margin:0}header{padding:32px 6%;border-bottom:3px solid #111}h1{margin:0 0 8px;font-size:29px}.wrap{max-width:1240px;margin:auto;padding:18px 5% 70px}h2{margin-top:35px;border-bottom:1px solid #777;padding-bottom:8px}.note{background:#f1f1f1;border-left:4px solid #111;padding:14px 17px}svg{width:100%;max-width:1050px;height:auto;font:17px Arial}table{border-collapse:collapse;width:100%;font-size:15px}td,th{padding:8px;border:1px solid #bbb;text-align:left}th{background:#eee}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px}.scroll{overflow:auto}code{font:14px Consolas,monospace}nav a{margin-right:18px;color:#111}'''
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cost-balanced scheduling: measured results</title><style>{css}</style>
<header><h1>Cost-balanced scheduling: measured results</h1><div>Application-level Linux process scheduling · compiled C CPU tasks</div></header>
<div class="wrap"><nav><a href="#stress">Tail-straggler test</a><a href="#paired">Every paired run</a><a href="#broad">Broader workloads</a><a href="#evidence">Evidence</a></nav>
<p class="note"><strong>Where it works:</strong> one expensive task near the tail of a queue. The algorithm estimates batch cost from known task metadata, forms variable-size batches and submits the longest batches first in one pool dispatch. On this targeted workload it was faster than fixed chunk 4 in all ten fresh paired runs. <strong>Limit:</strong> it did not win every workload in the broader five-class test.</p>
<h2 id="stress">Fresh tail-straggler test</h2><p>Ten seeds (10001–10010); one 40× C task randomly among the last eight of 192 tasks; two workers. Corrected end-to-end wall time includes batch planning, process startup, dispatch and teardown. The timing-correction plan was recorded before these new measurements. Dataset, order and checksums are saved. Validation: {sv['status']}.</p>
<p><strong>Declared method:</strong> balanced_32. Median paired ratio to fixed_4 = <strong>{sv['selected_median_paired_ratio_to_fixed4']:.3f}</strong>; lower than 1 is faster. The paired ratio is the primary result, not an isolated best run.</p>
<svg viewBox="0 0 1000 385" role="img" aria-label="Median runtime of seven methods on tail-spike workload">{''.join(bars)}</svg>
<h2 id="paired">All ten paired comparisons</h2><table><thead><tr><th>Seed</th><th>Fixed 4 (s)</th><th>Balanced 32 (s)</th><th>Ratio</th></tr></thead><tbody>{paired}</tbody></table>
<h2 id="broad">Generalization check: five ordinary workloads</h2><p>Fresh seeds 6001–6005, {bv['raw_rows']} timed runs across seven methods; same two-worker setup and corrected timing boundary. These workloads have no 40× tail spike. A ratio below 1 is faster than paired fixed_4. `balanced_fifo_16` was selected on separate development seeds before this broader test.</p>
<div class="scroll"><table><thead><tr><th>Workload</th><th>Fixed 4 median (s)</th><th>Balanced 32 median (s)</th><th>Balanced 32 paired ratio</th><th>Selected FIFO 16 paired ratio</th></tr></thead><tbody>{''.join(broadrows)}</tbody></table></div>
<h2 id="evidence">Openable evidence</h2><p>Source: <code>os_sched/scheduler_v4.py</code>. Stress-test files: <code>results_straggler_corrected/dataset.csv</code>, <code>raw.csv</code>, <code>summary.csv</code>, <code>validation.json</code>, <code>manifest.json</code> and <code>tests.txt</code>. Broader test: <code>results_balanced_corrected</code>. Pre-rerun plan: <code>TIMING_CORRECTION_PLAN.md</code>. Earlier result folders are retained but superseded. All values shown here come from saved measured files, not projections.</p></div></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print("Created", args.output)


if __name__ == "__main__":
    main()
