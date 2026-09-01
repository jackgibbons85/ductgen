from __future__ import annotations
from dataclasses import dataclass, field
import math

from .params import Frame
from .bridge import Bridge


def sector_polygon(r_in: float, r_out: float, sweep_deg: float, n: int = 96):
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


@dataclass
class Segment:
    index: int
    start_deg: float
    sweep_deg: float
    lap_start: float
    lap_end: float
    start_half: str
    end_half: str
    plate_angle: float = 0.0
    plate_w: float = 0.0
    plate_h: float = 0.0
    utilisation: float = 0.0
    struts: list = field(default_factory=list)

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
    interface_deg: float = 0.0
    interface_center_deg: float = 0.0
    split_deg: float = 360.0


@dataclass
class PartPlan:
    name: str
    w: float
    h: float
    z: float
    qty: int
    fits: bool
    note: str = ""


def strut_angles(f: Frame, phase: float = 45.0):
    n = max(f.struts.count, 1)
    return [(phase + 360.0 * i / n) % 360.0 for i in range(n)]


def _rods_collide(f: Frame, ring) -> bool:
    from .layout3d import rod_segment_plan
    placed = [(di, si) for di, si, _, _, _, role in rod_segment_plan(f, ring)
              if si is not None and role == "main"]
    return len(placed) != len(set(placed))


def plan_ring(f: Frame, force_count: int | None = None) -> RingPlan:
    ri = f.duct_id / 2.0 - 1.0
    ro = f.duct_od / 2.0
    bx = f.printer.bed_x - 2 * f.printer.margin
    by = f.printer.bed_y - 2 * f.printer.margin
    lap = f.joint.lap_deg

    if f.connector.enabled:
        br = Bridge(f)
        iface, iface_c = br.interface_deg, br.interface_center_deg
    else:
        iface, iface_c = 0.0, 0.0
    split = 360.0 - iface


    def candidate(n):
        pts = sector_polygon(ri, ro, split / n + lap)
        fits, ang, w, h, u = best_plate_fit(pts, bx, by,
                                            f.printer.allow_diagonal)
        return _assemble(f, n, split, iface, iface_c, lap, ang, w, h, u, fits)

    if force_count:
        return candidate(force_count)

    for n in range(1, 40):
        plan = candidate(n)
        if plan.fits:
            return plan
    return candidate(39)


def _assemble(f: Frame, n, split, iface, iface_c, lap, ang, w, h, u, fits):
    step = split / n

    origin = (iface_c + iface / 2.0) % 360.0

    sa = strut_angles(f)
    note = (f"connector takes {iface:.1f} deg of each ring; the remaining "
            f"{split:.1f} deg splits into {n}, {u*100:.0f}% of the plate")

    segs = []
    for i in range(n):
        s0 = (origin + i * step) % 360.0
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
                    joint_angles=[(origin + i * step) % 360.0
                                  for i in range(n + 1)],
                    strut_angles=sa,
                    arc_length=math.pi * f.duct_od * (step + lap) / 360.0,
                    fits=fits, note=note,
                    interface_deg=iface, interface_center_deg=iface_c,
                    split_deg=split)


def plan_other_parts(f: Frame, rings: RingPlan) -> list[PartPlan]:
    bx = f.printer.bed_x - 2 * f.printer.margin
    by = f.printer.bed_y - 2 * f.printer.margin
    bz = f.printer.bed_z
    out = []


    mo = f.mount
    span = 2 * f.mount_reach
    out.append(PartPlan("motor mount", span, span, f.mount_height, 4,
                        span <= bx and span <= by,
                        f"{f.rods.motor_count} arms at "
                        f"{360.0/max(f.rods.motor_count,1):.0f} deg, "
                        f"dia {f.mount_bore_dia:.1f} tube bores"))

    if f.connector.enabled:
        from .bridge import Bridge
        pts = Bridge(f).part_points(f.joint.lap_deg)
        fits, ang, w, h, u = best_plate_fit(pts, bx, by,
                                            f.printer.allow_diagonal)
        out.append(PartPlan("connector", w, h, f.duct_height, 2, fits,
                            f"bridges one duct pair; rotate {ang:.0f} deg, "
                            "inlet face up"))

    pc = f.center
    ph = f.center_plate_height
    out.append(PartPlan("center plate", f.plate_x, f.plate_z, ph, 1,
                        f.plate_x <= bx and f.plate_z <= by,
                        f"FC mount {pc.fc_span:g}x{pc.fc_span:g} M{pc.fc_bolt:g}"))

    from .layout3d import rod_cut_list
    for row in rod_cut_list(f):
        out.append(PartPlan(f"{row['name']} ({row['section']})", row["length"],
                            row["size"], row["size"], row["qty"], True,
                            "carbon, cut to length, not printed"))

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
         "it. Enable supports for that face only, it is two small patches per "
         "part, not a support-everything job."),
        "Layer lines run around the ring, i.e. perpendicular to the bolt axis of "
        "a half_lap joint and parallel to the hoop load. Wrap the finished ring "
        "if you want the hoop strength back.",
    ]
