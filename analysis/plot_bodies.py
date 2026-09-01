import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from components import components                       # noqa: E402
from section import slice_y                             # noqa: E402

BG = "#0b0d10"
FG = "#e6e6e6"
GRID = "#2a2f37"


def main(stl, out_png, levels="5,25", label=True):
    ys = [float(v) for v in levels.split(",")]
    bodies = components(stl)
    cmap = plt.get_cmap("turbo")
    fig, axes = plt.subplots(1, len(ys), figsize=(9.5 * len(ys), 9.8),
                             facecolor=BG)
    if len(ys) == 1:
        axes = [axes]
    for ax, y in zip(axes, ys):
        ax.set_facecolor(BG)
        for i, b in enumerate(bodies):
            segs = slice_y(b["faces"], y)
            if len(segs) == 0:
                continue
            c = cmap((i + 0.5) / len(bodies))
            for a, bb in segs:
                ax.plot([a[0], bb[0]], [a[2], bb[2]], color=c, lw=0.9)
            if label:
                p = segs.reshape(-1, 3)
                ax.text(p[:, 0].mean(), p[:, 2].mean(), str(i), fontsize=9,
                        color=c, ha="center", va="center", weight="bold")
        ax.set_aspect("equal")
        ax.set_title(f"Y = {y:g} mm", color=FG, fontsize=13)
        ax.grid(alpha=.25, color=GRID)
        ax.tick_params(colors=FG, labelsize=8)
        for s in ax.spines.values():
            s.set_color(GRID)
    fig.suptitle(os.path.basename(stl) + f"  {len(bodies)} solid bodies",
                 color=FG, fontsize=15)
    fig.tight_layout()
    fig.savefig(out_png, dpi=95, facecolor=BG)
    print("saved", out_png)
    for i, b in enumerate(bodies):
        print(f"[{i:2}] vol {b['vol']/1000:8.2f} cm3  "
              f"size ({b['size'][0]:7.2f},{b['size'][1]:6.2f},{b['size'][2]:7.2f})  "
              f"ctr ({b['ctr'][0]:8.2f},{b['ctr'][1]:6.2f},{b['ctr'][2]:8.2f})")


if __name__ == "__main__":
    main(*sys.argv[1:4])
