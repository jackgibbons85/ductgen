"""Split the duct ring into printable arc segments.

The interesting part is not the boolean -- it is deciding where to cut.
Rules applied here, in order:

1.  Pick the smallest segment count whose arc sector actually fits the bed,
    testing every in-plane rotation (a 256 mm bed swallows a ~345 mm part on
    the diagonal, which is how the reference build got its 286 mm arcs down).
2.  Rotate the joint phase so no joint lands on a strut root.  A joint at the
    strut root puts the glue line exactly where the motor loads enter the ring.
3.  Extend every segment by the lap angle at one end so consecutive segments
    overlap, and alternate which half of the section is removed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from .params import Frame


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def sector_polygon(r_in: float, r_out: float, sweep_deg: float, n: int = 96):
    """Outline of an annular sector starting at angle 0, in its own frame."""
    a = [math.radians(sweep_deg) * i / n for i in range(n + 1)]
    pts = [(r_out * math.cos(t), r_out * math.sin(t)) for t in a]
    pts += [(r_in * math.cos(t), r_in * math.sin(t)) for t in reversed(a)]
    return pts


def rotated_bbox(pts, deg: float):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    xs = [p[0] * c - p[1] * s for p in pts]
    ys = [p[0] * s + p[1] * c for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def best_plate_fit(pts, bed_x: float, bed_y: float, allow_diagonal: bool,
                   step: float = 0.5):
    """Smallest bed utilisation over all in-plane rotations.

    Returns (fits, angle_deg, w, h, utilisation).  Utilisation is
    max(w/bed_x, h/bed_y); anything <= 1 fits.
    """
    angles = [0.0, 90.0]
    if allow_diagonal:
        angles = [i * step for i in range(int(180 / step))]
    best = None
    for a in angles:
        w, h = rotated_bbox(pts, a)
        for ww, hh in ((w, h), (h, w)):
            u = max(ww / bed_x, hh / bed_y)
            if best is None or u < best[4]:
                best = (u <= 1.0, a, ww, hh, u)
    return best


# --------------------------------------------------------------------------
# plan objects
# --------------------------------------------------------------------------
@dataclass
class Segment:
    index: int
    start_deg: float        # where the body starts, including the incoming lap
    sweep_deg: float        # total swept angle of the solid
    lap_start: float        # lap angle consumed at the start end
    lap_end: float          # lap angle consumed at the finish end
    start_half: str         # which half is removed at the start end
    end_half: str           # ... and at the finish end
    plate_angle: float = 0.0
    plate_w: float = 0.0
    plate_h: float = 0.0
    utilisation: float = 0.0
    struts: list = field(default_factory=list)   # strut angles carried by this segment

    @property
    def end_deg(self):
        return self.start_deg + self.sweep_deg

    @property
    def mid_deg(self):
        return self.start_deg + self.sweep_deg / 2.0


@dataclass
class RingPlan:
    count: int
    segments: list
    joint_angles: list
    strut_angles: list
    arc_length: float
    fits: bool
    note: str = ""


@dataclass
class PartPlan:
    name: str
    w: float
    h: float
    z: float
    qty: int
    fits: bool
    note: str = ""


# --------------------------------------------------------------------------
# the planner
# --------------------------------------------------------------------------
def strut_angles(f: Frame, phase: float = 45.0):
    n = max(f.struts.count, 1)
    return [(phase + 360.0 * i / n) % 360.0 for i in range(n)]


def plan_ring(f: Frame, force_count: int | None = None) -> RingPlan:
    ri = f.duct_id / 2.0 - 1.0            # inner arc of the sector footprint
    ro = f.duct_od / 2.0
    bx = f.printer.bed_x - 2 * f.printer.margin
    by = f.printer.bed_y - 2 * f.printer.margin
    lap = f.joint.lap_deg

    chosen = None
    for n in ([force_count] if force_count else range(2, 25)):
        pts = sector_polygon(ri, ro, 360.0 / n + lap)
        fits, ang, w, h, u = best_plate_fit(pts, bx, by, f.printer.allow_diagonal)
        if fits or force_count:
            chosen = (n, ang, w, h, u, fits)
            break
    if chosen is None:
        n = 24
        pts = sector_polygon(ri, ro, 360.0 / n + lap)
        fits, ang, w, h, u = best_plate_fit(pts, bx, by, f.printer.allow_diagonal)
        chosen = (n, ang, w, h, u, fits)

    n, ang, w, h, u, fits = chosen
    step = 360.0 / n

    # --- rule 2: keep joints off the strut roots -------------------------
    sa = strut_angles(f)
    phase = 0.0
    best_clear = -1.0
    for k in range(72):                      # 5 deg increments over one segment
        p = k * step / 72.0
        joints = [(p + i * step) % 360.0 for i in range(n)]
        clear = min(min(abs((j - s + 180) % 360 - 180) for s in sa) for j in joints)
        if clear > best_clear:
            best_clear, phase = clear, p
    note = (f"joint phase {phase:.1f} deg keeps every joint {best_clear:.1f} deg "
            f"clear of the nearest strut root")

    segs = []
    for i in range(n):
        s0 = (phase + i * step) % 360.0
        seg = Segment(
            index=i,
            start_deg=s0 - lap / 2.0,
            sweep_deg=step + lap,
            lap_start=lap, lap_end=lap,
            start_half="upper" if i % 2 == 0 else "lower",
            end_half="lower" if i % 2 == 0 else "upper",
            plate_angle=ang, plate_w=w, plate_h=h, utilisation=u,
        )
        seg.struts = [a for a in sa
                      if ((a - s0) % 360.0) < step]
        segs.append(seg)

    return RingPlan(count=n, segments=segs,
                    joint_angles=[(phase + i * step) % 360.0 for i in range(n)],
                    strut_angles=sa,
                    arc_length=math.pi * f.duct_od * (step + lap) / 360.0,
                    fits=fits, note=note)


def plan_other_parts(f: Frame, rings: RingPlan) -> list[PartPlan]:
    bx = f.printer.bed_x - 2 * f.printer.margin
    by = f.printer.bed_y - 2 * f.printer.margin
    bz = f.printer.bed_z
    out = []

    hub = f.struts.hub_od
    out.append(PartPlan("motor hub", hub, hub, f.struts.hub_thickness, 4,
                        hub <= bx and hub <= by,
                        "prints flat, bolt face down"))

    strut_len = f.duct_id / 2.0 - f.struts.hub_od / 2.0 + 12.0   # +tenon
    out.append(PartPlan("strut", strut_len, f.struts.chord, f.struts.thickness,
                        4 * f.struts.count,
                        strut_len <= max(bx, by),
                        "print on edge so layers run along the span"))

    arm = f.motor_spacing / 2.0
    out.append(PartPlan("arm spar (carbon, cut to length)", arm, f.layout.rod_size,
                        f.layout.rod_size, 4, True, "not printed -- cut list only"))

    seg = rings.segments[0]
    out.append(PartPlan("duct segment", seg.plate_w, seg.plate_h, f.duct_height,
                        4 * rings.count, rings.fits and f.duct_height <= bz,
                        f"rotate {seg.plate_angle:.0f} deg on the plate, inlet face UP"))
    return out


def print_notes(f: Frame) -> list[str]:
    return [
        "Orient every duct segment with the INLET FACE UP. The bellmouth then "
        "recedes layer over layer and needs no support; inverted it is a full "
        "overhang at the lip.",
        f"The {f.duct.diffuser_deg:.0f} deg diffuser is the only overhanging bore "
        "surface and is far inside the self-supporting range.",
        (f"The half-lap tab at one end of each segment is a "
         f"{f.duct_height*f.joint.lap_height_frac:.0f} mm shelf with air under "
         "it. Enable supports for that face only -- it is two small patches per "
         "part, not a support-everything job."),
        "Layer lines run around the ring, i.e. perpendicular to the bolt axis of "
        "a half_lap joint and parallel to the hoop load. Wrap the finished ring "
        "if you want the hoop strength back.",
    ]
