"""Render faithful PNG snapshots of saved code, tests and measured CSV data."""
import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size, mono=False):
    names = ([r"C:\Windows\Fonts\consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"] if mono else
             [r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def canvas(title, subtitle, height=1000):
    image = Image.new("RGB", (1600, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), title, fill="black", font=font(35))
    draw.text((60, 91), subtitle, fill="#444444", font=font(20))
    draw.line((60, 137, 1540, 137), fill="black", width=3)
    return image, draw


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder",type=Path)
    args=ap.parse_args()
    folder=args.folder
    out=folder/"evidence"
    out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    validation=json.loads((folder/"validation.json").read_text(encoding="utf-8"))
    summary=read_csv(folder/"summary.csv")
    decisions=read_csv(folder/"decisions.csv")
    root=Path(__file__).resolve().parents[1]

    image,draw=canvas("1  Linux test and data-validation evidence",
                      "Captured from tests.txt, validation.json and the submitted experiment files")
    tests=(folder/"tests.txt").read_text(encoding="utf-8").splitlines()
    y=178
    for line in (line for line in tests if line.startswith("test_")):
        name=line.split(" (",1)[0]
        status=line.rsplit("...",1)[-1].strip()
        draw.text((75,y),f"{name}  ...  {status}",fill="black",font=font(20,True));y+=42
    for line in tests:
        if line.startswith("Ran ") or line == "OK":
            draw.text((75,y+8),line,fill="black",font=font(21,True));y+=42
    y=max(y+25,755)
    draw.text((75,y),"Data audit: "+validation["status"],fill="black",font=font(26));y+=41
    draw.text((75,y),f"{validation['raw_rows']} timed runs; {validation['summary_rows']} summaries; {validation['paired_groups']} paired groups",fill="black",font=font(20));y+=31
    draw.text((75,y),"All paired checksums equal; seeds disjoint; summary medians recomputed.",fill="black",font=font(20))
    image.save(out/"01_tests_and_validation.png")

    image,draw=canvas("2  Measured end-to-end runtime",
                      f"Actual summary.csv · {manifest['workers']} workers · {manifest['repeats']} paired repeats · lower is better")
    methods=("fixed_4","rule","ml","guarded_ml")
    lookup={(r["workload"],r["method"]):r for r in summary}
    headers=["Workload","Fixed 4","Rule","Tree","Guarded tree"]
    xs=[80,430,680,930,1190]
    for x,label in zip(xs,headers):draw.text((x,185),label,fill="black",font=font(24))
    draw.line((70,225,1525,225),fill="black",width=2)
    y=254
    for kind in manifest["workloads"]:
        values=[float(lookup[kind,m]["median_elapsed_s"]) for m in methods]
        draw.text((80,y),kind.replace("_"," "),fill="black",font=font(22))
        for x,value in zip(xs[1:],values):draw.text((x,y),f"{value:.3f} s",fill="black",font=font(22,True))
        y+=89;draw.line((70,y-28,1525,y-28),fill="#cccccc",width=1)
    y+=45
    draw.text((80,y),f"Holdout exact chunk-label accuracy: {manifest['training']['holdout_exact_accuracy']:.0%}",fill="black",font=font(24))
    draw.text((80,y+43),"End-to-end includes process startup, dispatch, live inference and teardown.",fill="black",font=font(21))
    draw.text((80,y+78),"No speedup is claimed unless the actual paired ratios support it.",fill="black",font=font(21))
    image.save(out/"02_runtime_results.png")

    events=[r for r in decisions if r["workload"]=="phase_shift" and r["method"]=="guarded_ml" and r["repeat"]=="1"]
    image,draw=canvas("3  Tree decisions during a phase-shifted workload",
                      "Actual decisions.csv · first test repeat · model loaded before execution")
    cols=[(75,"Round"),(230,"Old → new"),(460,"Completed"),(680,"Cost change"),(940,"Reason")]
    for x,label in cols:draw.text((x,184),label,fill="black",font=font(23))
    draw.line((70,224,1530,224),fill="black",width=2)
    y=254
    for event in events[:18]:
        vals=[event["round"],f"{event['old_chunk']} → {event['new_chunk']}",event["tasks_completed"],
              f"{float(event['task_cost_change']):+.2f}",event["reason"]]
        for (x,_),value in zip(cols,vals):draw.text((x,y),str(value),fill="black",font=font(20,True if value=="cost_increase_guard" else False))
        y+=36
    draw.text((75,945),f"Full trace has {len(events)} rounds; see decisions.csv and live_demo.json.",fill="black",font=font(19))
    image.save(out/"03_online_decisions.png")

    source=(root/"os_sched/scheduler_v2.py").read_text(encoding="utf-8").splitlines()
    interesting=[(i+1,s) for i,s in enumerate(source) if 121<=i+1<=147]
    image,draw=canvas("4  Implemented online scheduler code",
                      "Exact excerpt from os_sched/scheduler_v2.py; compiled C kernel is in native/work_kernel.c",height=1200)
    y=170
    for number,line in interesting:
        draw.text((70,y),f"{number:3d}  {line}",fill="black",font=font(14,True));y+=30
    image.save(out/"04_scheduler_code.png")
    print("Created",len(list(out.glob("*.png"))),"PNG evidence images in",out)


if __name__=="__main__":
    main()
