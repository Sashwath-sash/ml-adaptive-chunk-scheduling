"""Render factual black-and-white PNG flowcharts for the final cache report."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

OUT = Path(__file__).resolve().parent / "final_review_materials" / "output"
OUT.mkdir(parents=True, exist_ok=True)

def canvas(width, height):
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax

def box(ax, cx, cy, w, h, label, fontsize=11.5):
    ax.add_patch(Rectangle((cx-w/2, cy-h/2), w, h, facecolor="white",
                           edgecolor="black", linewidth=1.25, zorder=3))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=fontsize,
            family="DejaVu Sans", color="black", linespacing=1.3, zorder=4)

def diamond(ax, cx, cy, w, h, label, fontsize=11):
    ax.add_patch(Polygon([(cx,cy+h/2),(cx+w/2,cy),(cx,cy-h/2),(cx-w/2,cy)],
                         closed=True, facecolor="white", edgecolor="black",
                         linewidth=1.25, zorder=3))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=fontsize,
            family="DejaVu Sans", color="black", linespacing=1.25, zorder=4)

def route(ax, points, label=None, label_xy=None, style="solid"):
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0],b[0]],[a[1],b[1]],color="black",linewidth=1.18,
                linestyle=style, zorder=1)
    a, b = points[-2:]
    ax.annotate("", xy=b, xytext=a,
                arrowprops={"arrowstyle":"-|>","lw":1.18,"color":"black",
                            "linestyle":style,"mutation_scale":12}, zorder=2)
    if label:
        ax.text(*label_xy, label, fontsize=10, ha="center", va="center",
                family="DejaVu Sans", bbox={"facecolor":"white","edgecolor":"none","pad":1.2},
                zorder=5)

# Chronological source split, validation feedback, frozen model and separate replay.
fig, ax = canvas(9.4, 7.4)
ax.text(50, 96, "Data and model path", ha="center", va="center", fontsize=16,
        fontweight="bold", color="black")
box(ax, 50, 83, 27, 10, "BrowseTrace A/B + NASA July")
box(ax, 50, 68, 27, 10, "Extract keys and sizes;\nkeep request order")
box(ax, 50, 52, 22, 10, "Chronological split")
box(ax, 83, 67, 23, 10, "NASA August + Calgary\nseparate test sources")
route(ax, [(50,78),(50,73)])
route(ax, [(50,63),(50,57)])

box(ax, 17, 37, 23, 10, "Earlier requests\ntraining features + labels")
box(ax, 50, 37, 23, 10, "Later requests\nvalidation")
box(ax, 83, 37, 23, 10, "Held-out requests\nfinal evaluation")
route(ax, [(39,52),(17,52),(17,42)], "train", (26,54))
route(ax, [(50,47),(50,42)], "validate", (58,45))
route(ax, [(61,52),(66,52),(66,37),(71.5,37)], "BrowseTrace test", (72,54))
route(ax, [(83,62),(83,42)])

box(ax, 17, 18, 23, 10, "Fit gradient-boosted\ncandidate models")
box(ax, 50, 18, 23, 10, "Compare validation\ncache misses")
box(ax, 83, 18, 23, 10, "Export selected\nC tree nodes")
route(ax, [(17,32),(17,23)])
route(ax, [(50,32),(50,23)])
route(ax, [(28.5,18),(38.5,18)])
route(ax, [(61.5,18),(71.5,18)], "selected", (66,21))
route(ax, [(50,13),(50,4),(17,4),(17,13)], "next candidate", (35,5))

box(ax, 83, 5, 23, 9, "Native C replay\nread counts + checksum")
route(ax, [(83,13),(83,9.5)])
route(ax, [(94.5,37),(98,37),(98,5),(94.5,5)])
fig.tight_layout(pad=.4)
fig.savefig(OUT / "cache_data_flow.png", dpi=230, bbox_inches="tight")
plt.close(fig)

# The online branches correspond to cache_native.c lines 211-252.
fig, ax = canvas(8.5, 8.3)
ax.set_ylim(-8, 101)
ax.text(50, 97, "Native request handling", ha="center", va="center", fontsize=16,
        fontweight="bold", color="black")
box(ax, 50, 88, 26, 9, "Next request key")
box(ax, 50, 75, 28, 9, "Lookup in 512-block cache")
diamond(ax, 50, 59, 27, 13, "Cache hit?")
route(ax, [(50,83.5),(50,79.5)])
route(ax, [(50,70.5),(50,65.5)])
box(ax, 19, 45, 24, 10, "Return cached block;\nupdate policy state")
box(ax, 79, 45, 29, 10, "Miss: aligned 4 KiB\nO_DIRECT read")
route(ax, [(36.5,59),(19,59),(19,50)], "yes", (27,61))
route(ax, [(63.5,59),(79,59),(79,50)], "no", (70,61))
box(ax, 79, 31, 29, 10, "Eight past/current features\n+ frozen model score")
route(ax, [(79,40),(79,36)])
diamond(ax, 79, 17, 29, 12, "Score >= 0.2?")
route(ax, [(79,26),(79,23)])
box(ax, 52, 2, 20, 9, "Bypass insertion")
box(ax, 88, 2, 20, 9, "ARC or S3-FIFO\ninsert / evict")
route(ax, [(64.5,17),(52,17),(52,6.5)], "no", (57,19))
route(ax, [(93.5,17),(98,17),(98,8),(88,8),(88,6.5)], "yes", (95,20))
box(ax, 19, 17, 24, 10, "Same output block\n+ checksum")
route(ax, [(19,40),(19,22)])
route(ax, [(52,-2.5),(52,-5),(19,-5),(19,12)])
route(ax, [(88,-2.5),(88,-7),(19,-7),(19,12)])
route(ax, [(7,17),(3,17),(3,88),(37,88)], "repeat", (5,83))
fig.tight_layout(pad=.4)
fig.savefig(OUT / "cache_request_flow.png", dpi=230, bbox_inches="tight")
plt.close(fig)
print(OUT / "cache_data_flow.png")
print(OUT / "cache_request_flow.png")

# Matched evaluation: three admissions are replayed from the same test input.
fig, ax = canvas(9.2, 6.7)
ax.text(50, 96, "Matched policy evaluation", ha="center", va="center",
        fontsize=16, fontweight="bold", color="black")
box(ax, 50, 82, 40, 10, "Frozen test trace + backing file\nselect one capacity and parent")
for x, label in [(17, "Parent\nno admission filter"),
                 (50, "Second touch\ncheap admission control"),
                 (83, "Frozen ML\nscore and admit")]:
    box(ax, x, 56, 26, 12, label)
    route(ax, [(50,77),(50,70),(x,70),(x,62)])
    box(ax, x, 35, 26, 10, "Native replay\nreads + checksum")
    route(ax, [(x,50),(x,40)])
box(ax, 50, 17, 42, 10, "Check equal checksums; compare\nreads with unchanged parent")
for x in (17, 50, 83):
    route(ax, [(x,30),(x,25),(50,25),(50,22)])
box(ax, 50, 5, 42, 8, "Save JSON; generate tables and plots")
route(ax, [(50,12),(50,9)])
fig.tight_layout(pad=.4)
fig.savefig(OUT / "cache_evaluation_flow.png", dpi=230, bbox_inches="tight")
plt.close(fig)
print(OUT / "cache_evaluation_flow.png")
