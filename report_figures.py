"""Draw report diagrams and monochrome plots from saved measured CSV data."""
import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "results_paired_both_review" / "summary.csv"
OUT = ROOT / "output" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
with DATA.open(newline="", encoding="utf-8") as handle:
    SUMMARY = {(r["workload"], r["method"]): r for r in csv.DictReader(handle)}


def font(size, bold=False):
    file = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / file), size)


F = font(40)
FB = font(43, True)
FS = font(32)


def centered(draw, xy, text, face=F, fill="black"):
    box = draw.multiline_textbbox((0, 0), text, font=face, spacing=5, align="center")
    width, height = box[2] - box[0], box[3] - box[1]
    draw.multiline_text((xy[0] - width / 2, xy[1] - height / 2 - box[1]), text,
                        font=face, fill=fill, spacing=5, align="center")


def box(draw, rect, text, size=40, line=4, fill="white"):
    draw.rectangle(rect, fill=fill, outline="black", width=line)
    centered(draw, ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2), text, font(size))


def arrow(draw, points, width=5, dash=False):
    if dash:
        for a, b in zip(points[:-1], points[1:]):
            length = math.dist(a, b)
            steps = max(1, int(length // 32))
            for i in range(0, steps, 2):
                t0, t1 = i / steps, min(i + 1, steps) / steps
                x0, y0 = a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0
                x1, y1 = a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1
                draw.line((x0, y0, x1, y1), fill="black", width=width)
    else:
        draw.line(points, fill="black", width=width, joint="curve")
    a, b = points[-2], points[-1]
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    left = (b[0] - 18 * math.cos(angle) + 10 * math.sin(angle),
            b[1] - 18 * math.sin(angle) - 10 * math.cos(angle))
    right = (b[0] - 18 * math.cos(angle) - 10 * math.sin(angle),
             b[1] - 18 * math.sin(angle) + 10 * math.cos(angle))
    draw.polygon([b, left, right], fill="black")


def architecture():
    im = Image.new("RGB", (2400, 840), "white")
    d = ImageDraw.Draw(im)
    box(d, (70, 340, 350, 500), "Seeded task\nlist")
    d.polygon([(515, 335), (650, 420), (515, 505), (380, 420)],
              fill="white", outline="black", width=4)
    centered(d, (515, 420), "Choose\nmethod", font(35))
    arrow(d, [(350, 420), (380, 420)])
    modes = [
        ((775, 105, 1195, 245), "Online tree\nscheduler", 175),
        ((775, 350, 1195, 490), "Cost balanced\nplanner", 420),
        ((775, 595, 1195, 735), "Fixed chunk 4\nreference", 665),
    ]
    for rect, label, y in modes:
        box(d, rect, label)
        arrow(d, [(650, 420), (710, 420), (710, y), (775, y)])
        arrow(d, [(1195, y), (1300, y), (1300, 420), (1390, 420)])
    box(d, (1390, 340, 1700, 500), "Linux process\npool  2 workers")
    box(d, (1840, 340, 2160, 500), "Compiled C\nwork kernel")
    box(d, (1840, 625, 2160, 765), "Checksum and\ntimed results")
    arrow(d, [(1700, 420), (1840, 420)])
    arrow(d, [(2000, 500), (2000, 625)])
    arrow(d, [(1545, 340), (1545, 80), (985, 80), (985, 105)], dash=True)
    centered(d, (1380, 43), "round measurements to tree path", font(30))
    im.save(OUT / "architecture.png")


def scheduling_flow():
    im = Image.new("RGB", (2400, 880), "white")
    d = ImageDraw.Draw(im)
    d.text((80, 55), "Tree path", font=FB, fill="black")
    tree = [
        ((80, 185, 425, 330), "16 task pilot"),
        ((540, 185, 885, 330), "Measure five\nruntime features"),
        ((1000, 185, 1345, 330), "Saved tree picks\nchunk 1 4 16 64"),
        ((1460, 185, 1805, 330), "Submit next\nround"),
    ]
    for rect, label in tree:
        box(d, rect, label, size=36)
    for a, b in zip(tree[:-1], tree[1:]):
        arrow(d, [(a[0][2], 257), (b[0][0], 257)])
    d.polygon([(2070, 182), (2240, 257), (2070, 332), (1900, 257)],
              fill="white", outline="black", width=4)
    centered(d, (2070, 257), "Tasks\nleft", font(34))
    arrow(d, [(1805, 257), (1900, 257)])
    arrow(d, [(2070, 182), (2070, 100), (700, 100), (700, 185)], width=4)
    d.text((1430, 60), "yes  feedback round", font=FS, fill="black")
    arrow(d, [(2070, 332), (2070, 358)], width=4)
    d.ellipse((1940, 358, 2200, 422), fill="white", outline="black", width=4)
    centered(d, (2070, 390), "Finish", font(31))
    d.text((2210, 350), "no", font=FS, fill="black")
    d.line((80, 445, 2320, 445), fill="#999999", width=3)
    d.text((80, 485), "Cost balanced path", font=FB, fill="black")
    cost = [
        ((80, 615, 425, 760), "Known task\nmetadata"),
        ((540, 615, 885, 760), "Estimate work\nper task"),
        ((1000, 615, 1345, 760), "Pack near equal\ncost batches"),
        ((1460, 615, 1805, 760), "Send longest\nfirst"),
        ((1920, 615, 2265, 760), "One pool\ndispatch"),
    ]
    for rect, label in cost:
        box(d, rect, label, size=36)
    for a, b in zip(cost[:-1], cost[1:]):
        arrow(d, [(a[0][2], 687), (b[0][0], 687)])
    im.save(OUT / "scheduling_flow.png")


def paired_plot():
    kinds = ["uniform", "moderate", "high", "phase_shift", "prime_scan", "late_heavy"]
    names = ["Uniform", "Moderate", "High variance", "Phase shift", "Prime scan", "Late heavy"]
    im = Image.new("RGB", (2400, 1120), "white")
    d = ImageDraw.Draw(im)
    d.text((110, 55), "Median wall-time ratio to fixed chunk 4", font=font(48, True), fill="black")
    d.text((110, 115), "Below 1.00 is faster than fixed 4. Each dot is a median of matched-seed ratios.",
           font=FS, fill="black")
    left, right = 575, 2150
    low, high = 0.75, 1.33
    x = lambda v: left + (v - low) / (high - low) * (right - left)
    for tick in (0.8, 0.9, 1.0, 1.1, 1.2, 1.3):
        xx = x(tick)
        d.line((xx, 225, xx, 910), fill="#D2D2D2" if tick != 1.0 else "black", width=3 if tick != 1.0 else 5)
        centered(d, (xx, 970), f"{tick:.2f}", font(31))
    for i, (kind, name) in enumerate(zip(kinds, names)):
        y = 280 + i * 110
        d.text((110, y - 30), name, font=font(37), fill="black")
        tree = float(SUMMARY[(kind, "ml")]["median_paired_ratio"])
        cost = float(SUMMARY[(kind, "balanced_32")]["median_paired_ratio"])
        xt, xc = x(tree), x(cost)
        d.ellipse((xt - 16, y - 36, xt + 16, y - 4), fill="black")
        d.rectangle((xc - 17, y + 6, xc + 17, y + 40), fill="white", outline="black", width=5)
        d.text((xt + 27, y - 44), f"{tree:.3f}", font=font(32), fill="black")
        label_x = xc - 108 if cost < 1.0 else xc + 27
        d.text((label_x, y + 2), f"{cost:.3f}", font=font(32), fill="black")
    d.ellipse((120, 1030, 150, 1060), fill="black")
    d.text((165, 1027), "Decision tree", font=font(31), fill="black")
    d.rectangle((520, 1030, 550, 1060), fill="white", outline="black", width=4)
    d.text((565, 1027), "Cost balanced 32", font=font(31), fill="black")
    d.text((1500, 1027), "n = 5; late heavy n = 10", font=font(28), fill="black")
    im.save(OUT / "paired_ratio_plot.png")


def late_heavy_plot():
    methods = [("Fixed 4", "fixed_4"), ("Decision tree", "ml"), ("Cost balanced 32", "balanced_32")]
    im = Image.new("RGB", (2400, 920), "white")
    d = ImageDraw.Draw(im)
    d.text((110, 45), "Late-heavy workload  ten matched seeds", font=font(48, True), fill="black")
    d.text((110, 110), "Median full wall time and median batch p95 are different measures, not additive parts.",
           font=FS, fill="black")
    left, right = 610, 2150
    x = lambda v: left + v / 0.62 * (right - left)
    for tick in (0.0, 0.2, 0.4, 0.6):
        xx = x(tick)
        d.line((xx, 215, xx, 790), fill="#CFCFCF", width=3)
        centered(d, (xx, 835), f"{tick:.1f}", font(30))
    d.text((2160, 822), "s", font=font(30), fill="black")
    for i, (label, method) in enumerate(methods):
        row = SUMMARY[("late_heavy", method)]
        wall = float(row["median_wall_s"])
        p95 = float(row["median_batch_p95_s"])
        y = 275 + i * 175
        d.text((110, y + 18), label, font=font(38), fill="black")
        d.rectangle((left, y, x(wall), y + 48), fill="black")
        d.rectangle((left, y + 65, x(p95), y + 113), fill="white", outline="black", width=4)
        d.text((x(wall) + 20, y + 3), f"{wall:.3f}", font=font(31), fill="black")
        d.text((x(p95) + 20, y + 68), f"{p95:.3f}", font=font(31), fill="black")
    d.rectangle((1280, 170, 1315, 205), fill="black")
    d.text((1330, 167), "Full wall time", font=font(29), fill="black")
    d.rectangle((1690, 170, 1725, 205), fill="white", outline="black", width=4)
    d.text((1740, 167), "Batch p95", font=font(29), fill="black")
    im.save(OUT / "late_heavy_plot.png")


if __name__ == "__main__":
    architecture()
    scheduling_flow()
    paired_plot()
    late_heavy_plot()
    print("Wrote four code-generated monochrome figures from", DATA)
