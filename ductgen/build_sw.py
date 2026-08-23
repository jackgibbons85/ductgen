"""Build the frame in SolidWorks.

Every part is modelled so that no reference plane has to be created at an
arbitrary angle -- angled planes are the fragile part of the SolidWorks API.
The trick is to revolve each duct segment SYMMETRICALLY about the Front plane:

  * the segment then spans -sweep/2 .. +sweep/2, so a sketch drawn at angle
    +phi lands at global +phi or -phi depending on how SolidWorks maps the
    sketch axes -- and because the part is symmetric, that mirror does not
    matter.  Every segment is the same part, printed N times and rotated;
    a mirrored ring assembles exactly the same way.
  * the strut sits at the segment mid-angle, which IS the Front plane, so the
    strut socket is a plain cut-extrude either side of that plane.

The one thing that genuinely has to be discovered at runtime is which way is
"up" for a cut from the mid-height plane.  build_segment() probes it by
watching the centre of mass move, and self-corrects.
"""
from __future__ import annotations
import math
import os

from .params import Frame
from .profile import meridian, ring_volume
from .segment import RingPlan, plan_ring
from .swapi import SolidWorks


# --------------------------------------------------------------------------
def _bodies(sw, model):
    b = sw.part(model).GetBodies2(0, True)
    if b is None:
        return []
    b = list(b) if isinstance(b, (list, tuple)) else [b]
    from .swapi import _w
    return [_w(sw.mod.IBody2, x) for x in b]


def mass_props(sw, model):
    """(volume mm^3, centre of mass in mm) of the first solid body."""
    bs = _bodies(sw, model)
    if not bs:
        return 0.0, (0.0, 0.0, 0.0)
    p = bs[0].GetMassProperties(1000.0)
    return p[3] * 1e9, (p[0] * 1000.0, p[1] * 1000.0, p[2] * 1000.0)


def _wedge(sm, sw, r0, r1, a0_deg, a1_deg, n=24):
    """Closed annular-sector sketch profile, angles in the sketch's own frame."""
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    outer = [(r1 * math.cos(a0 + (a1 - a0) * i / n),
              r1 * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    inner = [(r0 * math.cos(a0 + (a1 - a0) * i / n),
              r0 * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n, -1, -1)]
    sw.arc(sm, (0, 0), outer[0], outer[-1], True)
    sw.line(sm, outer[-1], inner[0])
    sw.arc(sm, (0, 0), inner[0], inner[-1], False)
    sw.line(sm, inner[-1], outer[0])


# --------------------------------------------------------------------------
def build_segment(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
                  with_strut_socket: bool = True, keep_open: bool = False):
    """One duct arc. All N of them are this same part, rotated."""
    seg = ring.segments[0]
    sweep = seg.sweep_deg
    lap = f.joint.lap_deg
    H = f.duct_height
    y_mid = H * f.joint.lap_height_frac
    rt = f.throat_radius
    ro = f.duct_od / 2.0

    model = sw.new_part()
    front, top, right = sw.base_planes(model)

    # ---- 1. the revolved arc ------------------------------------------
    sm = sw.begin_sketch(model, front)
    sw.centerline(sm, (0.0, -10.0), (0.0, H + 10.0))
    for e in meridian(f):
        if e[0] == "line":
            sw.line(sm, e[1], e[2])
        elif e[0] == "arc":
            sw.arc(sm, e[1], e[2], e[3], e[4])
        else:
            sw.spline(sm, e[1])
    s_prof = sw.end_sketch(model)

    sw.revolve(model, s_prof, sweep / 2.0, angle2_deg=sweep / 2.0)

    vol0, com0 = mass_props(sw, model)
    expect = ring_volume(f) * sweep / 360.0
    if abs(vol0 - expect) / max(expect, 1.0) > 0.05:
        raise RuntimeError(f"revolve volume {vol0/1000:.1f} cm3 does not match "
                           f"the analytic {expect/1000:.1f} cm3 -- the section "
                           "is probably self-intersecting")

    # ---- 2. lap at the +phi end: remove the material ABOVE mid-height ---
    p_mid = sw.offset_plane(model, top, y_mid)
    a1 = sweep / 2.0
    a0 = a1 - lap

    sm = sw.begin_sketch(model, p_mid)
    _wedge(sm, sw, rt - 2.0, ro + 2.0, a0, a1)
    s_lapA = sw.end_sketch(model)

    reverse = False
    sw.cut(model, s_lapA, depth=H, reverse=reverse)
    vol1, com1 = mass_props(sw, model)
    if com1[1] > com0[1] + 1e-6:
        # centre of mass went UP, so we removed the lower half. Flip and redo.
        model.EditUndo2(1)
        reverse = True
        sw.cut(model, s_lapA, depth=H, reverse=reverse)
        vol1, com1 = mass_props(sw, model)
        if com1[1] > com0[1] + 1e-6:
            raise RuntimeError("could not work out which way is up for the "
                               "lap cut; centre of mass rose both times")

    # ---- 3. lap at the -phi end: remove the material BELOW mid-height ---
    sm = sw.begin_sketch(model, p_mid)
    _wedge(sm, sw, rt - 2.0, ro + 2.0, -a1, -a0)
    s_lapB = sw.end_sketch(model)
    sw.cut(model, s_lapB, depth=H, reverse=not reverse)

    # ---- 4. joint bolts, vertical through the two overlaps -------------
    em = f.joint.bolt_edge_margin
    dia = f.joint.bolt_size + f.joint.bolt_clearance
    radii = [rt + em, ro - em] if f.joint.bolts == 2 else \
            [rt + em + (ro - rt - 2 * em) * i / max(f.joint.bolts - 1, 1)
             for i in range(f.joint.bolts)]
    phi = math.radians((a0 + a1) / 2.0)
    sm = sw.begin_sketch(model, top)
    for r in radii:
        for s in (1.0, -1.0):
            sw.circle(sm, (r * math.cos(s * phi), r * math.sin(s * phi)), dia)
    s_bolts = sw.end_sketch(model)
    sw.cut(model, s_bolts, through_both=True)

    # ---- 5. strut socket on the Front plane ----------------------------
    if with_strut_socket and f.struts.count:
        depth = f.socket_depth
        y0 = f.strut_y - f.struts.chord / 2.0
        y1 = y0 + f.struts.chord
        r_in = rt - 0.5
        sm = sw.begin_sketch(model, front)
        sw.polygon(sm, [(r_in, y0), (r_in + depth, y0),
                        (r_in + depth, y1), (r_in, y1)])
        s_sock = sw.end_sketch(model)
        sw.cut(model, s_sock, depth=(f.struts.thickness + 0.3) / 2.0,
               both_dirs=True)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_duct_segment")
    paths = [sw.save(model, base + ".SLDPRT"),
             sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, _ = mass_props(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part="duct segment", qty=4 * ring.count, files=paths,
                volume_cm3=vol / 1000.0, sweep_deg=sweep,
                lap_cut_reversed=reverse)


# --------------------------------------------------------------------------
def build_hub(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
              keep_open: bool = False):
    """Motor mount disc: bolt pattern, shaft relief, radial strut slots."""
    st = f.struts
    n = st.count or ring.count
    model = sw.new_part()
    front, top, right = sw.base_planes(model)

    sm = sw.begin_sketch(model, top)
    sw.circle(sm, (0, 0), st.hub_od)
    s = sw.end_sketch(model)
    sw.extrude(model, s, st.hub_thickness)

    sm = sw.begin_sketch(model, top)
    sw.circle(sm, (0, 0), f.motor.boss_dia)
    for x, y in f.motor.hole_xy():
        sw.circle(sm, (x, y), f.motor.hole_dia)
    s = sw.end_sketch(model)
    sw.cut(model, s, through_both=True)

    # radial slots for the strut tabs, cut vertically through the disc
    tab = 8.0
    w = st.thickness + 0.3
    sm = sw.begin_sketch(model, top)
    for i in range(n):
        a = math.radians(360.0 * i / n)
        ca, sa = math.cos(a), math.sin(a)
        r0, r1 = st.hub_od / 2.0 - tab, st.hub_od / 2.0 + 1.0
        pts = [(r0 * ca - (-w / 2) * sa, r0 * sa + (-w / 2) * ca),
               (r1 * ca - (-w / 2) * sa, r1 * sa + (-w / 2) * ca),
               (r1 * ca - (w / 2) * sa, r1 * sa + (w / 2) * ca),
               (r0 * ca - (w / 2) * sa, r0 * sa + (w / 2) * ca)]
        sw.polygon(sm, pts)
    s = sw.end_sketch(model)
    sw.cut(model, s, through_both=True)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_motor_hub")
    paths = [sw.save(model, base + ".SLDPRT"), sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, _ = mass_props(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part="motor hub", qty=4, files=paths, volume_cm3=vol / 1000.0)


def build_strut(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
                keep_open: bool = False):
    """One stator vane: a flat plate with a tab at each end."""
    st = f.struts
    H = f.duct_height
    y_c = f.strut_y
    r0 = st.hub_od / 2.0 - 8.0
    r1 = f.throat_radius + f.socket_depth - 0.3      # matches the duct socket
    c = st.chord

    model = sw.new_part()
    front, top, right = sw.base_planes(model)
    sm = sw.begin_sketch(model, front)
    sw.polygon(sm, [(r0, y_c - c / 2), (r1, y_c - c / 2),
                    (r1, y_c + c / 2), (r0, y_c + c / 2)])
    s = sw.end_sketch(model)
    sw.extrude(model, s, st.thickness / 2.0, both=True)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_strut")
    paths = [sw.save(model, base + ".SLDPRT"), sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, _ = mass_props(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part="strut", qty=4 * (st.count or ring.count), files=paths,
                volume_cm3=vol / 1000.0, length_mm=r1 - r0)


# --------------------------------------------------------------------------
def build_all(f: Frame, outdir: str, visible: bool = True, ring=None,
              keep_open: bool = False):
    ring = ring or plan_ring(f)
    os.makedirs(outdir, exist_ok=True)
    sw = SolidWorks(visible=visible)
    made = [build_segment(sw, f, ring, outdir, keep_open=keep_open),
            build_hub(sw, f, ring, outdir, keep_open=keep_open),
            build_strut(sw, f, ring, outdir, keep_open=keep_open)]
    return made


def placement_table(f: Frame, ring: RingPlan):
    """Where every copy of the duct segment goes, for assembly by hand or
    by a follow-up macro."""
    rows = []
    s = f.motor_spacing / 2.0
    for mi, (mx, my) in enumerate([(-s, -s), (s, -s), (s, s), (-s, s)]):
        for seg in ring.segments:
            rows.append(dict(duct=mi + 1, segment=seg.index + 1,
                             x=round(mx, 2), y=round(my, 2),
                             rotation_deg=round(seg.mid_deg, 2)))
    return rows
