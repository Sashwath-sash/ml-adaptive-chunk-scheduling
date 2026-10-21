"""Render a self-contained, data-derived HTML evidence page for v7."""
import html
import json
import statistics
from pathlib import Path

from .experiment_v7 import BASELINE, FEATURES, KINDS_V6, csv_read


def escape(value):
    return html.escape(str(value))


def split_description(node):
    if "feature" not in node:
        return escape(node["value"])
    name = FEATURES[node["feature"]]
    return (f"If {escape(name)} ≤ {node['threshold']:.5g}, select {split_description(node['left'])}; "
            f"otherwise select {split_description(node['right'])}.")


def main():
    folder = Path("results_learned_v7_final")
    summary = csv_read(folder / "test_summary.csv")
    raw = csv_read(folder / "test_raw.csv")
    train = json.loads((folder / "train_manifest.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "test_manifest.json").read_text(encoding="utf-8"))
    model = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    lookup = {(row["kind"], row["method"]): row for row in summary}
    methods = ("fixed_4", "pool_map_16", "process_executor_16", "lpt_2", "lpt_4", "learned")
    titles = {"fixed_4": "Fixed 4", "pool_map_16": "Pool.map 16",
              "process_executor_16": "ProcessPool 16", "lpt_2": "LPT 2",
              "lpt_4": "LPT 4", "learned": "Learned", BASELINE: "Cost 32"}
    table = []
    for kind in KINDS_V6:
        cells = [f"<th scope='row'>{escape(kind)}</th>"]
        for method in methods:
            item = lookup[(kind, method)]
            cells.append(f"<td>{float(item['median_paired_ratio']):.3f} "
                         f"<small>({item['paired_wins']}/{item['n']} wins)</small></td>")
        table.append("<tr>" + "".join(cells) + "</tr>")
    counts = {}
    for row in raw:
        if row["method"] == "learned":
            key = row["selected_policy"]
            counts[key] = counts.get(key, 0) + 1
    direct = []
    for kind in KINDS_V6:
        group = [row for row in raw if row["kind"] == kind]
        per_seed = {(int(row["seed"]), row["method"]): float(row["elapsed_s"]) for row in group}
        seeds = sorted({int(row["seed"]) for row in group})
        against_fixed = statistics.median(per_seed[(seed, "learned")] / per_seed[(seed, "fixed_4")] for seed in seeds)
        against_lpt2 = statistics.median(per_seed[(seed, "learned")] / per_seed[(seed, "lpt_2")] for seed in seeds)
        direct.append(f"<tr><th scope='row'>{escape(kind)}</th><td>{against_fixed:.3f}</td><td>{against_lpt2:.3f}</td></tr>")
    confirm_html = ""
    if (folder / "confirm_summary.csv").exists():
        confirmation = csv_read(folder / "confirm_summary.csv")
        conf = {(row["kind"], row["baseline"], row["method"]): row for row in confirmation}
        conf_rows = []
        for kind in KINDS_V6:
            cells = [f"<th scope='row'>{escape(kind)}</th>"]
            for baseline in ("contig_32", "lpt_2"):
                row = conf[(kind, baseline, "learned")]
                cells.append(f"<td>{float(row['median_paired_ratio']):.3f} "
                             f"<small>({row['paired_wins']}/{row['n']} wins; "
                             f"95% bootstrap {float(row['bootstrap_median_95_low']):.3f}–"
                             f"{float(row['bootstrap_median_95_high']):.3f})</small></td>")
            conf_rows.append("<tr>" + "".join(cells) + "</tr>")
        confirm_html = ("<h2>Additional larger-scale confirmation</h2>"
                        "<p>The frozen model was tested again on 20 new seeds per workload at a scale above training. "
                        "This is a separate 120-group, 480-run confirmation. Ratios below 1 are faster.</p>"
                        "<table><thead><tr><th>Workload</th><th>Learned / cost-32</th><th>Learned / LPT-2</th></tr></thead>"
                        f"<tbody>{''.join(conf_rows)}</tbody></table>"
                        "<p><a href='confirm_raw.csv'>Raw confirmation runs</a> · "
                        "<a href='confirm_summary.csv'>Paired summary</a> · "
                        "<a href='confirm_manifest.json'>Protocol</a></p>")
    lo, hi, x0, x1 = .75, 1.25, 205, 840
    scale = lambda value: x0 + (value - lo) / (hi - lo) * (x1 - x0)
    svg = ["<svg viewBox='0 0 900 410' role='img' aria-label='Median paired whole-run ratios to cost-32'>"]
    for tick in (.8, .9, 1, 1.1, 1.2):
        xx = scale(tick)
        svg.append(f"<line x1='{xx:.1f}' x2='{xx:.1f}' y1='20' y2='360' stroke='{'#111' if tick == 1 else '#ccc'}' stroke-width='{'2' if tick == 1 else '1'}'/>")
        svg.append(f"<text x='{xx:.1f}' y='390' text-anchor='middle' font-size='13'>{tick:.2f}</text>")
    for i, kind in enumerate(KINDS_V6):
        y = 52 + 55 * i
        svg.append(f"<text x='5' y='{y + 5}' font-size='14'>{escape(kind)}</text>")
        for method, offset, shape in (("learned", -10, "circle"), ("lpt_2", 0, "square"), ("pool_map_16", 10, "diamond")):
            ratio = float(lookup[(kind, method)]["median_paired_ratio"])
            x = scale(min(hi, max(lo, ratio)))
            yy = y + offset
            if shape == "circle":
                svg.append(f"<circle cx='{x:.1f}' cy='{yy}' r='5' fill='#111'/>")
            elif shape == "square":
                svg.append(f"<rect x='{x-5:.1f}' y='{yy-5}' width='10' height='10' fill='white' stroke='#111' stroke-width='1.5'/>")
            else:
                svg.append(f"<polygon points='{x:.1f},{yy-6} {x+6:.1f},{yy} {x:.1f},{yy+6} {x-6:.1f},{yy}' fill='#888'/>")
    svg.append("</svg>")
    split = split_description(model["model"]["root"])
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Learned scheduler: held-out evidence</title><style>
body{{font:16px/1.5 Georgia,serif;color:#111;background:#fff;max-width:1180px;margin:30px auto;padding:0 20px}}
h1,h2{{font-family:Arial,sans-serif;line-height:1.2}}h1{{margin-bottom:5px}}h2{{margin-top:34px;border-bottom:1px solid #aaa;padding-bottom:4px}}
p{{max-width:1050px}}.meta{{font:14px Arial,sans-serif;color:#444}}.note{{border-left:3px solid #111;padding:6px 14px;background:#f6f6f6}}
table{{border-collapse:collapse;width:100%;font:14px/1.4 Arial,sans-serif}}th,td{{border-bottom:1px solid #ccc;padding:7px;text-align:left;vertical-align:top}}thead th{{background:#eee}}
small{{color:#555}}.scroll{{overflow-x:auto}}svg{{max-width:100%;height:auto;border:1px solid #ccc}}a{{color:#111}}
code,pre{{font-family:Consolas,monospace}}pre{{background:#f5f5f5;padding:14px;white-space:pre-wrap}}
</style></head><body>
<h1>Learned chunk dispatch: actual held-out results</h1>
<p class='meta'>{train['groups']} training groups / {train['timed_runs']} measured runs · {model['validation_groups']} validation groups · {manifest['groups']} final groups / {manifest['timed_runs']} timed runs · 192 C tasks · 2 Linux workers · outputs equal</p>
<p>Python selects application-level batches for compiled-C CPU work. The model is trained on complete timed runs and uses input-task metadata before launching workers; it does <strong>not</strong> change the Linux kernel scheduler and does <strong>not</strong> run a pilot during inference.</p>
<h2>Comparison with cost-balanced 32</h2>
<p>Each number is the median of ten within-seed complete-run time ratios to cost-balanced 32. Below 1 is faster. All timers include model features/inference where applicable, planning, pool startup, dispatch, CPU work, and teardown. ● learned, □ plain LPT-2, ◆ standard Pool.map 16.</p>
{''.join(svg)}
<div class='scroll'><table><thead><tr><th>Workload</th>{''.join('<th>' + escape(titles[m]) + '</th>' for m in methods)}</tr></thead><tbody>{''.join(table)}</tbody></table></div>
<p class='note'>A win over cost-32 does not prove the model beats plain LPT-2. See the direct paired comparison below; small differences and one-host timing noise should not be overclaimed. Bootstrap bounds for each ratio are in <a href='test_summary.csv'>test_summary.csv</a>.</p>
<h2>Does learning add anything beyond LPT-2?</h2>
<p>Direct median paired complete-time ratios, not ratios of separate medians. Below 1 means learned was faster.</p>
<table><thead><tr><th>Workload</th><th>Learned / fixed 4</th><th>Learned / plain LPT-2</th></tr></thead><tbody>{''.join(direct)}</tbody></table>
{confirm_html}
<h2>Actual learned rule</h2>
<p>Validation selected depth {model['chosen']['depth_cap']} and minimum leaf {model['chosen']['min_leaf']} from 25 CART configurations. {split} The final test selected {escape(counts)}. This rule was learned from measured complete-run labels; LPT itself is a classical heuristic, not our invention.</p>
<h2>Protocol, limitations and files</h2>
<p>Training: four seeds per workload at two scales, two timed repetitions per candidate. Validation: three disjoint seeds at a third scale, two repetitions. Final: ten further unseen seeds at a fourth scale, randomized method order within each task group. Six generated workload classes include a real C prime-counting kernel; the others use deterministic C CPU work and a constructed tail-straggler. This is one WSL2 host, not production traces or a cross-platform guarantee. Standard Python APIs have different dispatch internals; comparisons are practical end-to-end results, not identical scheduler overhead microbenchmarks.</p>
<ul><li><a href='model.json'>Saved trained model and selected thresholds</a></li><li><a href='train_raw.csv'>Training candidate timings</a></li><li><a href='train_groups.csv'>Training labels and measured policy medians</a></li><li><a href='validation_scores.csv'>Model selection scores</a></li><li><a href='test_raw.csv'>Every final timed run and checksum</a></li><li><a href='test_summary.csv'>Paired summaries and bootstrap intervals</a></li><li><a href='test_manifest.json'>Machine and protocol</a></li><li><a href='live_demo.json'>Fresh terminal demo trace</a></li></ul>
<pre>bash build.sh
python3 -m unittest discover -s tests -v
python3 -m os_sched.verify_learned_v7 --output results_learned_v7_final
python3 -m os_sched.live_demo_v7</pre>
<p class='meta'>Prior art: <a href='https://github.com/unibas-dmi-hpc/LB4OMP'>LB4OMP</a> already implements adaptive and learning-based loop scheduling. No first-invention claim is made here.</p>
</body></html>"""
    target = folder / "dashboard.html"
    target.write_text(page, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
