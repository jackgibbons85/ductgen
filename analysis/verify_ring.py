import sys
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from stlread import read_stl                                   # noqa: E402
from section import slice_y                                    # noqa: E402
from ductgen.params import Frame                               # noqa: E402
from ductgen.segment import plan_ring                          # noqa: E402


def rot_y(v, deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    out = v.copy()
    out[..., 0] = v[..., 0] * c + v[..., 2] * s
    out[..., 2] = -v[..., 0] * s + v[..., 2] * c
    return out


def main(stl, out_png, preset=None):
    f = Frame.from_json(preset) if preset else Frame()
    ring = plan_ring(f)
    n = ring.count
    step = 360.0 / n
    tris, _ = read_stl(stl)

    H = f.duct_height
    levels = [0.15 * H, 0.5 * H - 2, 0.5 * H + 2, 0.85 * H]
    fig, axes = plt.subplots(1, len(levels), figsize=(5.2 * len(levels), 5.6))
    cols = plt.get_cmap("tab10")

    report = []
    for ax, y in zip(axes, levels):
        cover = []
        for i in range(n):
            t = rot_y(tris, i * step)
            segs = slice_y(t, y)
            if len(segs) == 0:
                continue
            for a, b in segs:
                ax.plot([a[0], b[0]], [a[2], b[2]], color=cols(i), lw=0.7)
            a = segs[:, 0, :]
            b = segs[:, 1, :]
            for k in range(11):
                p = a + (b - a) * (k / 10.0)
                cover.append(np.degrees(np.arctan2(p[:, 2], p[:, 0])) % 360)
        allth = np.concatenate(cover) if cover else np.array([])
        occupied = np.zeros(360, bool)
        occupied[np.floor(allth).astype(int) % 360] = True
        gaps = 360 - occupied.sum()
        report.append((y, gaps))
        ax.set_aspect("equal")
        ax.set_title(f"y = {y:.0f} mm   angular gaps: {gaps} deg")
        ax.grid(alpha=.3)

    fig.suptitle(f"{n} copies of {os.path.basename(stl)} rotated {step:.0f} deg "
                 f"-- ring closure check", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_png, dpi=100)
    print(f"saved {out_png}")
    for y, g in report:
        verdict = "closed" if g == 0 else f"{g} deg OPEN"
        print(f"  y={y:6.1f} mm : {verdict}")
    return report


if __name__ == "__main__":
    main(*sys.argv[1:4])
