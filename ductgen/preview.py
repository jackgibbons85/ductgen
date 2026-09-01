from __future__ import annotations
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon

from .params import Frame, check
from .profile import polyline
from .segment import plan_ring, sector_polygon
from .layout3d import (bridge_outline_world, center_rods, outer_rods,
                       motor_rods, duct_centers, ring_offset)

BG = "#0b0d10"
PANEL = "#12151a"
FG = "#e8eaed"
DIM = "#8b93a1"
GRID = "#232830"
ACCENT = "#ff6b6b"
SEG = ["#4ea1ff", "#ffb454", "#5ddba0", "#c792ea", "#ffd866", "#ff7fb0"]
BRIDGE = "#2ec4b6"
PLATE = "#ffd166"
ROD = "#d0d4da"
LEVEL = {"ok": "#5ddba0", "warn": "#ffb454", "fail": "#ff6b6b"}

SLICE = "#4ea1ff"
SLICE_DIM = "#2f6ea8"
LW_SLICE = 0.9
LW_JOINT = 1.6

SECTION_PAD_R = 96.0


def _style(ax, title=None):
    ax.set_facecolor(PANEL)
    ax.grid(alpha=.25, color=GRID, lw=.6)
    ax.tick_params(colors=DIM, labelsize=8)
    for s in ax.spines.values():
        s.set_color(GRID)
    if title:
        ax.set_title(title, color=FG, fontsize=10.5, pad=8)


def _rot(pts, deg, dx=0.0, dy=0.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(p[0] * c - p[1] * s + dx, p[0] * s + p[1] * c + dy) for p in pts]


def _section(ax, f: Frame):
    p = polyline(f)
    H, rt, ro = f.duct_height, f.throat_radius, f.duct_od / 2.0
    ax.add_patch(Polygon(p, closed=True, fc="#1d4e6b", ec="#6cc7ff", lw=1.5))
    ax.add_patch(Polygon([(-x, y) for x, y in p], closed=True,
                         fc="#1d4e6b", ec="#6cc7ff", lw=1.5, alpha=.4))

    yp = H - f.prop_plane_y
    R = f.prop.diameter / 2.0
    ax.plot([-R, R], [yp, yp], color=ACCENT, lw=2.2)
    ax.plot([0, 0], [-4, H + 4], color=DIM, ls="-.", lw=.7)
    arw = dict(arrowstyle="->", color=DIM, lw=.9)

    ax.annotate(f"prop plane  {f.prop.diameter_in}\" x {f.prop.blades}\n"
                f"{f.prop_plane_y:.0f} mm below the lip "
                f"({f.duct.prop_plane_frac*100:.0f}% of chord)",
                (0, yp), (0, yp - .24 * H), ha="center", fontsize=8,
                color=ACCENT, arrowprops=dict(arrowstyle="->", color=ACCENT))
    lip = f.lip_radius
    ax.annotate(f"lip R {lip:.1f} mm = {lip/f.prop.diameter*100:.1f}% of D",
                (rt + lip * .3, H - lip * .3), (rt - 2.1 * lip, H + .24 * H),
                fontsize=8, color=FG, arrowprops=arw)
    ax.annotate(f"throat {f.duct_id:.1f} mm\n"
                f"(tip gap {(f.duct_id-f.prop.diameter)/2:.1f} mm/side)",
                (rt, yp + 2), (rt + .16 * ro, H * .64),
                fontsize=8, color=FG, arrowprops=arw)
    ax.annotate(f"diffuser {f.duct.diffuser_deg:.0f} deg\n"
                f"sigma = {f.expansion_ratio:.2f}   ideal gain x{f.ideal_thrust_gain:.2f}",
                (f.exit_radius, 1), (f.exit_radius - 1.0 * ro, -.27 * H),
                fontsize=8, color=FG, arrowprops=arw)
    ax.annotate("", (-ro - 14, 0), (-ro - 14, H),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=.9))
    ax.text(-ro - 18, H / 2, f"chord {H:.0f} mm\n({f.duct.chord_ratio*100:.0f}% of D)",
            rotation=90, va="center", ha="right", fontsize=8, color=FG)

    ax.set_aspect("equal")
    ax.set_xlim(-ro - 62, ro + SECTION_PAD_R)
    ax.set_ylim(-.34 * H, H * 1.44)
    _style(ax, "duct section (revolved about the dash-dot axis)")
    ax.set_xlabel("radius, mm", color=DIM, fontsize=8)


def _plan_geometry(ax, f: Frame, ring, show=("ducts", "connector", "plate",
                                             "rods", "prop"),
                   lw: float = LW_SLICE, lw_joint: float = LW_JOINT):
    ro, ri = f.duct_od / 2.0, f.throat_radius
    line = dict(fc="none", ec=SLICE, lw=lw)
    show = set(show)

    if f.connector.enabled and "connector" in show:
        for sign in (+1, -1):
            ax.add_patch(Polygon(bridge_outline_world(f, sign), closed=True,
                                 **line))

    for mx, mz in duct_centers(f):
        off = ring_offset(f, mx, mz, ring)
        if "ducts" in show:
            for seg in ring.segments:
                poly = sector_polygon(ri, ro, seg.sweep_deg, 72)
                ax.add_patch(Polygon(_rot(poly, seg.start_deg + off, mx, mz),
                                     closed=True, **line))
            for j in ring.joint_angles:
                a = math.radians(j + off)
                ax.plot([mx + ri * math.cos(a), mx + ro * math.cos(a)],
                        [mz + ri * math.sin(a), mz + ro * math.sin(a)],
                        color=SLICE, lw=lw_joint)
            ax.add_patch(Circle((mx, mz), f.struts.hub_od / 2, zorder=6,
                                **line))
        if "prop" in show:
            ax.add_patch(Circle((mx, mz), f.prop.diameter / 2, fc="none",
                                ec=SLICE_DIM, ls=":", lw=lw))

    if "plate" in show:
        c = f.center
        ax.add_patch(Rectangle((-f.plate_x / 2, -f.plate_z / 2), f.plate_x,
                               f.plate_z, zorder=4, **line))
        h = c.fc_span / 2.0
        for sx in (-h, h):
            for sz in (-h, h):
                ax.add_patch(Circle((sx, sz), c.fc_bolt / 2 + .4, zorder=6,
                                    **line))

    if "rods" in show:
        for x, z0, z1, sz in center_rods(f):
            ax.add_patch(Rectangle((x - sz / 2, z0), sz, z1 - z0, zorder=5,
                                   **line))
        for x0, z0, x1, z1, sz in outer_rods(f):
            if x0 == x1:
                ax.add_patch(Rectangle((x0 - sz / 2, z0), sz, z1 - z0,
                                       zorder=5, **line))
            else:
                ax.add_patch(Rectangle((x0, z0 - sz / 2), x1 - x0, sz,
                                       zorder=5, **line))
        for cx, cz, a, L, sz, _tg in motor_rods(f):
            h = f.motor_rod_r0
            pts = _rot([(h, -sz / 2), (h + L, -sz / 2),
                        (h + L, sz / 2), (h, sz / 2)], a, cx, cz)
            ax.add_patch(Polygon(pts, closed=True, zorder=5, **line))


def _plan(ax, f: Frame, ring):
    _plan_geometry(ax, f, ring)

    c = f.center
    h = c.fc_span / 2.0
    ax.annotate(f"FC / PDB  {c.fc_span:g} x {c.fc_span:g}  M{c.fc_bolt:g}",
                (h, -h), (f.plate_x * 1.5, -f.plate_z * 1.15), fontsize=8,
                color=DIM, ha="left",
                arrowprops=dict(arrowstyle="->", color=DIM, lw=.8))

    s = f.motor_spacing / 2.0
    lim = f.footprint / 2 + 40
    ax.annotate("", (-s, -lim + 16), (s, -lim + 16),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=.9))
    ax.text(0, -lim + 22, f"motor spacing {f.motor_spacing:.0f} mm   "
                          f"(diagonal {f.motor_diagonal:.0f} mm)",
            ha="center", fontsize=8, color=DIM)
    ax.set_aspect("equal")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    nr = len(center_rods(f)) + len(outer_rods(f)) + len(motor_rods(f))
    _style(ax, f"plan: {ring.count} arcs + 1 connector per ring pair, "
               f"{4*ring.count} printed arcs, {nr} carbon rods")


def _plate(ax, f: Frame, ring):
    bx, by = f.printer.bed_x, f.printer.bed_y
    m = f.printer.margin
    seg = ring.segments[0]
    ax.add_patch(Rectangle((0, 0), bx, by, fc="#181c22", ec=GRID))
    ax.add_patch(Rectangle((m, m), bx - 2 * m, by - 2 * m, fc="none",
                           ec=GRID, ls="--"))
    poly = _rot(sector_polygon(f.throat_radius, f.duct_od / 2.0,
                               seg.sweep_deg, 72), seg.plate_angle)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    dx = bx / 2 - (max(xs) + min(xs)) / 2
    dy = by / 2 - (max(ys) + min(ys)) / 2
    ax.add_patch(Polygon([(x + dx, y + dy) for x, y in poly], closed=True,
                         fc=SLICE, ec=SLICE, lw=LW_SLICE, alpha=.16))
    ax.add_patch(Polygon([(x + dx, y + dy) for x, y in poly], closed=True,
                         fc="none", ec=SLICE, lw=LW_SLICE))
    ax.add_patch(Rectangle((bx / 2 - seg.plate_w / 2, by / 2 - seg.plate_h / 2),
                           seg.plate_w, seg.plate_h, fc="none", ec=ACCENT, ls=":"))
    ok = "FITS" if ring.fits else "DOES NOT FIT"
    _style(ax, f"{f.printer.name} plate {bx:.0f}x{by:.0f}, {ok}\n"
               f"segment {seg.plate_w:.0f} x {seg.plate_h:.0f} x {f.duct_height:.0f} mm "
               f"rotated {seg.plate_angle:.0f} deg, {seg.utilisation*100:.0f}% of bed")
    ax.set_aspect("equal")
    ax.set_xlim(-10, bx + 10)
    ax.set_ylim(-10, by + 10)


def _checks(ax, f: Frame):
    ax.axis("off")
    ax.set_facecolor(PANEL)
    ax.set_xlim(0, 1.16)
    y = 1.0
    ax.text(0, y, f"{f.name}   {f.prop.diameter_in}\" x {f.prop.blades}   "
                  f"{f.motor.stator} {f.motor.kv}kV {f.motor.cells}S",
            fontsize=11.5, weight="bold", va="top", color=FG)
    y -= .075
    for c in check(f):
        ax.text(0, y, c.level.upper(), color=LEVEL[c.level], fontsize=8,
                weight="bold", va="top")
        ax.text(.12, y, c.label, fontsize=8.5, va="top", color=FG)
        val = c.value if len(c.value) <= 40 else c.value[:38] + ".."
        ax.text(.41, y, val, fontsize=8.5, va="top", family="monospace",
                color=FG)
        ax.text(.82, y, f"want {c.want}", fontsize=8, va="top", color=DIM)
        y -= .046
        if c.note and c.level != "ok":
            ax.text(.12, y, c.note, fontsize=7.5, va="top", color=DIM)
            y -= .042
    y -= .02
    ax.text(0, y, f"ideal duct thrust gain x{f.ideal_thrust_gain:.2f} at equal "
                  f"shaft power, (2*sigma)^(1/3), only if the lip stays attached",
            fontsize=8, va="top", color=DIM)


def render_section(f: Frame, path: str, dpi: int = 160, width_in: float = 12.0):
    ro, H = f.duct_od / 2.0, f.duct_height
    wd = (ro + SECTION_PAD_R) - (-ro - 62)
    hd = 1.44 * H - (-.34 * H)
    pad = 1.5
    ha = max(1.5, width_in * hd / max(wd, 1e-6))
    fig = plt.figure(figsize=(width_in, ha + pad), facecolor=BG)
    _section(fig.add_subplot(1, 1, 1), f)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return path


PLAN_LAYERS = [
    ("1_ducts", ("ducts",)),
    ("2_connectors", ("connector", "plate")),
    ("3_rods", ("rods",)),
]


def render_layers(f: Frame, outdir: str, ring=None, px: tuple = (1920, 1080),
                  dpi: int = 120, lw: float = 1.7, lw_joint: float = 2.8,
                  transparent: bool = True, prefix: str = "layer"):
    ring = ring or plan_ring(f)
    os.makedirs(outdir, exist_ok=True)
    wp, hp = px
    fsz = (wp / dpi, hp / dpi)

    lim = f.footprint / 2 + 40
    xlim = lim * (wp / hp)

    out = []
    for name, show in PLAN_LAYERS + [("_all", sum((s for _, s in PLAN_LAYERS),
                                                  ()))]:
        fig = plt.figure(figsize=fsz, dpi=dpi,
                         facecolor="none" if transparent else BG)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("none" if transparent else BG)
        ax.axis("off")
        _plan_geometry(ax, f, ring, show=show, lw=lw, lw_joint=lw_joint)
        ax.set_aspect("equal")
        ax.set_xlim(-xlim, xlim)
        ax.set_ylim(-lim, lim)
        p = os.path.join(outdir, f"{prefix}{name}.png")
        fig.savefig(p, dpi=dpi, transparent=transparent,
                    facecolor="none" if transparent else BG)
        plt.close(fig)
        out.append(p)
    return out


def render(f: Frame, path: str, ring=None, section_path: str | None = None):
    ring = ring or plan_ring(f)
    fig = plt.figure(figsize=(16, 11), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1])
    _section(fig.add_subplot(gs[0, 0]), f)
    _plan(fig.add_subplot(gs[0, 1]), f, ring)
    _plate(fig.add_subplot(gs[1, 0]), f, ring)
    _checks(fig.add_subplot(gs[1, 1]), f)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=BG)
    plt.close(fig)

    if section_path is None:
        base, ext = os.path.splitext(path)
        section_path = f"{base}_section{ext or '.png'}"
    if section_path:
        render_section(f, section_path)
    return path
