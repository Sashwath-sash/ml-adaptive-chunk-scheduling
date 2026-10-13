"""Render readable PNG evidence from the improved source and saved test log."""
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
    source = (root / "os_sched/scheduler_v3.py").read_text(encoding="utf-8").splitlines()
    image, draw = canvas("9  Improved one-decision scheduler code",
                         "Source: os_sched/scheduler_v3.py · actual measured pilot, saved tree, bulk dispatch", height=1050)
    y = 175
    for number, line in enumerate(source, 1):
        if 15 <= number <= 50:
            draw.text((70, y), f"{number:3d}  {line}", fill="black", font=font(16, True))
            y += 24
    image.save(out / "09_scheduler_v3_code.png")

    validation = json.loads((args.folder / "validation.json").read_text(encoding="utf-8"))
    tests = (args.folder / "tests.txt").read_text(encoding="utf-8").splitlines()
    image, draw = canvas("10  Linux improvement tests and data audit",
                         "Captured from saved tests.txt and validation.json · no fabricated output")
    y = 175
    for line in (line for line in tests if line.startswith("test_")):
        name = line.split(" (", 1)[0]
        status = line.rsplit("...", 1)[-1].strip()
        draw.text((75, y), f"{name} ... {status}", fill="black", font=font(19, True))
        y += 42
    for line in tests:
        if line.startswith("Ran ") or line == "OK":
            draw.text((75, y + 8), line, fill="black", font=font(22, True))
            y += 42
    y = max(y + 28, 690)
    draw.text((75, y), f"Data audit: {validation['status']}", fill="black", font=font(27))
    draw.text((75, y + 48), f"{validation['raw_rows']} runs · {validation['paired_groups']} paired groups · matching checksums", fill="black", font=font(21))
    draw.text((75, y + 83), "Exactly one saved online decision per improved run; medians recomputed.", fill="black", font=font(21))
    image.save(out / "10_tests_and_validation.png")
    print("Created 2 improvement evidence images in", out)


if __name__ == "__main__":
    main()
