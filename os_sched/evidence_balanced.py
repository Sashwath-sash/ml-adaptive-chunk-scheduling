"""Render faithful code and test snapshots for the cost-balanced result."""
import argparse
import json
from pathlib import Path

from .evidence_images import canvas, font


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args()
    out = args.folder / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    source = (root / "os_sched/scheduler_v4.py").read_text(encoding="utf-8").splitlines()
    image, draw = canvas("11  Cost-balanced batch scheduler code",
                         "Exact excerpt from os_sched/scheduler_v4.py · estimated cost, batch sorting and one pool dispatch", height=1080)
    y = 170
    for number, line in enumerate(source, 1):
        if 21 <= number <= 50:
            draw.text((70, y), f"{number:3d}  {line}", fill="black", font=font(16, True))
            y += 27
    image.save(out / "11_balanced_scheduler_code.png")

    tests = (args.folder / "tests.txt").read_text(encoding="utf-8").splitlines()
    validation = json.loads((args.folder / "validation.json").read_text(encoding="utf-8"))
    image, draw = canvas("12  Linux tests and paired-data audit",
                         "Saved tests.txt and validation.json · tail-straggler evaluation")
    y = 170
    for line in (line for line in tests if line.startswith("test_")):
        name = line.split(" (", 1)[0]
        status = line.rsplit("...", 1)[-1].strip()
        draw.text((75, y), f"{name} ... {status}", fill="black", font=font(18, True))
        y += 36
    for line in tests:
        if line.startswith("Ran ") or line == "OK":
            draw.text((75, y + 7), line, fill="black", font=font(20, True))
            y += 36
    y = max(y + 24, 745)
    draw.text((75, y), f"Data audit: {validation['status']}", fill="black", font=font(26))
    draw.text((75, y + 42), f"{validation['raw_rows']} runs; {validation['paired_groups']} pairs; {validation['dataset_rows']} task inputs", fill="black", font=font(20))
    draw.text((75, y + 75), f"Selected paired ratio: {validation['selected_median_paired_ratio_to_fixed4']:.3f}; matching checksums.", fill="black", font=font(20))
    image.save(out / "12_tests_and_validation.png")
    print("Created balanced evidence images in", out)


if __name__ == "__main__":
    main()
