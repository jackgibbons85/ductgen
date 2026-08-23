"""The duct meridian section.

One definition, used by both the preview renderer and the SolidWorks builder,
so what you see in the PNG is exactly what gets revolved.

Coordinates are (r, y): r is radius from the duct axis, y is height with 0 at
the exit face and +y toward the inlet.  The section is closed and is revolved
about r = 0.

Entities are emitted as primitives rather than a dense polyline so SolidWorks
gets real lines / arcs / splines instead of a 200-segment approximation.
"""
from __future__ import annotations
import math

from .params import Frame

Line = tuple           # ("line", (r0,y0), (r1,y1))
Arc = tuple            # ("arc", (cx,cy), (r0,y0), (r1,y1), ccw)
Spline = tuple         # ("spline", [(r,y), ...])


def ellipse_quarter(cx, cy, a, b, n=17):
    """From (cx, cy+b) round to (cx-a, cy): the bellmouth quadrant."""
    return [(cx - a * math.sin(math.pi / 2 * i / (n - 1)),
             cy + b * math.cos(math.pi / 2 * i / (n - 1))) for i in range(n)]


def meridian(f: Frame) -> list:
    H = f.duct_height
    rt = f.throat_radius
    ro = f.duct_od / 2.0                         # at the inlet face
    ro_exit = f.duct_od_exit / 2.0               # at the exit face
    lip = f.lip_radius
    a = lip * f.duct.lip_ellipse_ratio          # horizontal semi-axis
    b = lip                                      # vertical semi-axis
    y_prop = H - f.prop_plane_y                  # prop plane height
    y_throat_end = H - b                         # bottom of the bellmouth
    te = f.duct.trailing_edge_r
    r_exit = f.exit_radius

    if y_throat_end < y_prop:
        # bellmouth is deeper than the prop plane -- clamp so the throat exists
        b = min(b, H - y_prop)
        a = b * f.duct.lip_ellipse_ratio
        y_throat_end = H - b

    ents: list = []

    # 1. inlet bellmouth, from the top face down to the throat
    if f.duct.lip_ellipse_ratio == 1.0:
        ents.append(("arc", (rt + a, H - b), (rt + a, H), (rt, H - b), True))
    else:
        ents.append(("spline", ellipse_quarter(rt + a, H - b, a, b)))

    # 2. throat: constant radius from the bellmouth down to the prop plane
    if y_throat_end - y_prop > 1e-6:
        ents.append(("line", (rt, y_throat_end), (rt, y_prop)))

    # 3. diffuser: prop plane down to the start of the exit round
    ents.append(("line", (rt, y_prop), (r_exit, te)))

    # 4. exit round onto the bottom face
    ents.append(("arc", (r_exit + te, te), (r_exit, te), (r_exit + te, 0.0), True))

    # 5. bottom face outward
    ents.append(("line", (r_exit + te, 0.0), (ro_exit, 0.0)))

    # 6. outer skin, tapering out toward the inlet where the lip needs the room
    ents.append(("line", (ro_exit, 0.0), (ro, H)))

    # 7. top face: the rim land, inward to close on the bellmouth
    ents.append(("line", (ro, H), (rt + a, H)))

    return ents


def polyline(f: Frame, n_arc: int = 24) -> list:
    """Flatten the section to points, for plotting and for area/volume checks."""
    pts: list = []
    for e in meridian(f):
        if e[0] == "line":
            pts += [e[1], e[2]]
        elif e[0] == "spline":
            pts += list(e[1])
        else:
            _, (cx, cy), p0, p1, ccw = e
            a0 = math.atan2(p0[1] - cy, p0[0] - cx)
            a1 = math.atan2(p1[1] - cy, p1[0] - cx)
            r = math.hypot(p0[0] - cx, p0[1] - cy)
            if ccw and a1 < a0:
                a1 += 2 * math.pi
            if not ccw and a1 > a0:
                a1 -= 2 * math.pi
            pts += [(cx + r * math.cos(a0 + (a1 - a0) * i / n_arc),
                     cy + r * math.sin(a0 + (a1 - a0) * i / n_arc))
                    for i in range(n_arc + 1)]
    # drop consecutive duplicates, and the repeated closing vertex -- a
    # zero-length edge makes every self-intersection test ambiguous
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, out[-1]) > 1e-7:
            out.append(p)
    while len(out) > 2 and math.dist(out[-1], out[0]) <= 1e-7:
        out.pop()
    return out


def section_area(f: Frame) -> float:
    p = polyline(f)
    s = 0.0
    for i in range(len(p)):
        x0, y0 = p[i]
        x1, y1 = p[(i + 1) % len(p)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def ring_volume(f: Frame) -> float:
    """Pappus: section area times the path of its centroid."""
    p = polyline(f)
    a2 = 0.0
    cx = 0.0
    for i in range(len(p)):
        x0, y0 = p[i]
        x1, y1 = p[(i + 1) % len(p)]
        cr = x0 * y1 - x1 * y0
        a2 += cr
        cx += (x0 + x1) * cr
    area = abs(a2) / 2.0
    cx = cx / (3.0 * a2) if a2 else 0.0
    return 2 * math.pi * abs(cx) * area


def section_perimeter(f: Frame) -> float:
    p = polyline(f)
    return sum(math.dist(p[i], p[(i + 1) % len(p)]) for i in range(len(p)))


def ring_surface_area(f: Frame) -> float:
    """Pappus again, on the perimeter rather than the area."""
    p = polyline(f)
    tot = 0.0
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        L = math.dist(a, b)
        tot += L * 2 * math.pi * (a[0] + b[0]) / 2.0
    return tot


def print_mass(f: Frame, walls: int = 3, infill: float = 0.15,
               density: float = 1.24e-3) -> dict:
    """Grams of filament for one full ring, printed the usual way.

    density is g/mm^3 (1.24e-3 = PLA, 1.04e-3 = PETG, 1.20e-3 = ABS).
    """
    vol = ring_volume(f)
    skin = min(ring_surface_area(f) * walls * f.printer.nozzle * 1.05, vol)
    core = max(vol - skin, 0.0) * infill
    return dict(volume_cm3=vol / 1000.0,
                shell_cm3=skin / 1000.0,
                infill_cm3=core / 1000.0,
                grams=(skin + core) * density)
