"""Render the design before committing it to CAD.

Four panels: the duct section, the frame in plan with the cut lines on it,
one segment laid out on the bed, and the design-rule table.
"""
from __future__ import annotations
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon

from .params import Frame, check
from .profile import polyline
from .segment import plan_ring, sector_polygon


def _rot(pts, deg, dx=0.0, dy=0.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(p[0] * c - p[1] * s + dx, p[0] * s + p[1] * c + dy) for p in pts]


def _section(ax, f: Frame):
    p = polyline(f)
    H, rt, ro = f.duct_height, f.throat_radius, f.duct_od / 2.0
    ax.add_patch(Polygon(p, closed=True, fc="#9fc5e8", ec="#1f4e79", lw=1.4))
    ax.add_patch(Polygon([(-x, y) for x, y in p], closed=True,
                         fc="#9fc5e8", ec="#1f4e79", lw=1.4, alpha=.35))

    y_prop = H - f.prop_plane_y
    R = f.prop.diameter / 2.0
    ax.plot([-R, R], [y_prop, y_prop], color="#cc0000", lw=2.2)
    ax.plot([0, 0], [-4, H + 4], color="k", ls="-.", lw=.7)
    ax.annotate(f"prop plane  {f.prop.diameter_in}\" x {f.prop.blades}\n"
                f"{f.prop_plane_y:.0f} mm below the lip "
                f"({f.duct.prop_plane_frac*100:.0f}% of chord)",
                (0, y_prop), (0, y_prop - .22 * H), ha="center", fontsize=8,
                color="#cc0000", arrowprops=dict(arrowstyle="->", color="#cc0000"))

    lip = f.lip_radius
    ax.annotate(f"lip R {lip:.1f} mm = {lip/f.prop.diameter*100:.1f}% of D",
                (rt + lip * .3, H - lip * .3), (rt - 1.9 * lip, H + .22 * H),
                fontsize=8, arrowprops=dict(arrowstyle="->"))
    ax.annotate(f"throat {f.duct_id:.1f} mm\n(tip gap {(f.duct_id-f.prop.diameter)/2:.1f} mm/side)",
                (rt, y_prop + (H - f.prop_plane_y) * .0 + 2), (rt + .18 * ro, H * .62),
                fontsize=8, arrowprops=dict(arrowstyle="->"))
    ax.annotate(f"diffuser {f.duct.diffuser_deg:.0f} deg\nsigma = {f.expansion_ratio:.2f}\n"
                f"ideal gain x{f.ideal_thrust_gain:.2f}",
                (f.exit_radius, 1), (f.exit_radius - .95 * ro, -.26 * H),
                fontsize=8, arrowprops=dict(arrowstyle="->"))

    ax.annotate("", (-ro - 14, 0), (-ro - 14, H), arrowprops=dict(arrowstyle="<->"))
    ax.text(-ro - 17, H / 2, f"chord {H:.0f} mm\n({f.duct.chord_ratio*100:.0f}% of D)",
            rotation=90, va="center", ha="right", fontsize=8)

    ax.set_aspect("equal")
    ax.set_xlim(-ro - 60, ro + 20)
    ax.set_ylim(-.32 * H, H * 1.42)
    ax.set_title("duct section (revolved about the dash-dot axis)", fontsize=10)
    ax.grid(alpha=.25)
    ax.set_xlabel("radius, mm")


def _plan(ax, f: Frame, ring):
    s = f.motor_spacing / 2.0
    ro, ri = f.duct_od / 2.0, f.throat_radius
    cols = ["#4472c4", "#ed7d31", "#70ad47", "#ffc000", "#7030a0", "#c00000"]
    for mx, my in [(-s, -s), (s, -s), (s, s), (-s, s)]:
        for seg in ring.segments:
            poly = sector_polygon(ri, ro, seg.sweep_deg, 72)
            ax.add_patch(Polygon(_rot(poly, seg.start_deg, mx, my), closed=True,
                                 fc=cols[seg.index % len(cols)], ec="k", lw=.5, alpha=.75))
        for j in ring.joint_angles:
            a = math.radians(j)
            ax.plot([mx + ri * math.cos(a), mx + ro * math.cos(a)],
                    [my + ri * math.sin(a), my + ro * math.sin(a)], "k-", lw=1.6)
        for a_deg in ring.strut_angles:
            a = math.radians(a_deg)
            ax.plot([mx + f.struts.hub_od / 2 * math.cos(a), mx + ri * math.cos(a)],
                    [my + f.struts.hub_od / 2 * math.sin(a), my + ri * math.sin(a)],
                    color="#555", lw=f.struts.thickness / 2)
        ax.add_patch(Circle((mx, my), f.struts.hub_od / 2, fc="#333", ec="k"))
        ax.add_patch(Circle((mx, my), f.prop.diameter / 2, fc="none",
                            ec="#cc0000", ls=":", lw=1.0))
    for a, b in [((-s, -s), (s, -s)), ((s, -s), (s, s)), ((s, s), (-s, s)), ((-s, s), (-s, -s))]:
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#222", lw=f.layout.rod_size / 3)

    lim = f.footprint / 2 + 25
    ax.annotate("", (-s, -lim + 12), (s, -lim + 12), arrowprops=dict(arrowstyle="<->"))
    ax.text(0, -lim + 16, f"motor spacing {f.motor_spacing:.0f} mm  "
                          f"(diagonal {f.motor_diagonal:.0f} mm)",
            ha="center", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_title(f"plan: {ring.count} segments per ring, "
                 f"{4*ring.count} printed arcs total", fontsize=10)
    ax.grid(alpha=.25)


def _plate(ax, f: Frame, ring):
    bx, by = f.printer.bed_x, f.printer.bed_y
    m = f.printer.margin
    seg = ring.segments[0]
    ax.add_patch(Rectangle((0, 0), bx, by, fc="#f2f2f2", ec="#888"))
    ax.add_patch(Rectangle((m, m), bx - 2 * m, by - 2 * m, fc="none",
                           ec="#bbb", ls="--"))
    poly = _rot(sector_polygon(f.throat_radius, f.duct_od / 2.0, seg.sweep_deg, 72),
                seg.plate_angle)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    dx = bx / 2 - (max(xs) + min(xs)) / 2
    dy = by / 2 - (max(ys) + min(ys)) / 2
    ax.add_patch(Polygon([(x + dx, y + dy) for x, y in poly], closed=True,
                         fc="#4472c4", ec="k", lw=.8, alpha=.8))
    ax.add_patch(Rectangle((bx / 2 - seg.plate_w / 2, by / 2 - seg.plate_h / 2),
                           seg.plate_w, seg.plate_h, fc="none", ec="#cc0000", ls=":"))
    ok = "FITS" if ring.fits else "DOES NOT FIT"
    ax.set_title(f"{f.printer.name} plate {bx:.0f}x{by:.0f} -- {ok}\n"
                 f"segment {seg.plate_w:.0f} x {seg.plate_h:.0f} x {f.duct_height:.0f} mm "
                 f"rotated {seg.plate_angle:.0f} deg, {seg.utilisation*100:.0f}% of bed",
                 fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-10, bx + 10)
    ax.set_ylim(-10, by + 10)


def _checks(ax, f: Frame):
    ax.axis("off")
    col = {"ok": "#2e7d32", "warn": "#ef6c00", "fail": "#c62828"}
    y = 1.0
    ax.set_xlim(0, 1.15)
    ax.text(0, y, f"{f.name}   {f.prop.diameter_in}\" x {f.prop.blades}   "
                  f"{f.motor.stator} {f.motor.kv}kV {f.motor.cells}S",
            fontsize=11, weight="bold", va="top")
    y -= .085
    for c in check(f):
        ax.text(0, y, c.level.upper(), color=col[c.level], fontsize=8,
                weight="bold", va="top")
        ax.text(.13, y, c.label, fontsize=8.5, va="top")
        val = c.value if len(c.value) <= 40 else c.value[:38] + ".."
        ax.text(.42, y, val, fontsize=8.5, va="top", family="monospace")
        ax.text(.82, y, f"want {c.want}", fontsize=8, va="top", color="#555")
        y -= .05
        if c.note and c.level != "ok":
            ax.text(.13, y, c.note, fontsize=7.5, va="top", color="#777",
                    wrap=True)
            y -= .045
    y -= .02
    ax.text(0, y, f"ideal duct thrust gain x{f.ideal_thrust_gain:.2f} at equal shaft "
                  f"power (2*sigma)^(1/3) -- only if the lip stays attached",
            fontsize=8, va="top", color="#555")


def render(f: Frame, path: str, ring=None):
    ring = ring or plan_ring(f)
    fig = plt.figure(figsize=(16, 11))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1])
    _section(fig.add_subplot(gs[0, 0]), f)
    _plan(fig.add_subplot(gs[0, 1]), f, ring)
    _plate(fig.add_subplot(gs[1, 0]), f, ring)
    _checks(fig.add_subplot(gs[1, 1]), f)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
