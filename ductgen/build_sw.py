from __future__ import annotations
import math
import os

from .params import Frame
from .profile import meridian, ring_volume
from .segment import RingPlan, plan_ring
from .swapi import SolidWorks


def _bodies(sw, model):
    b = sw.part(model).GetBodies2(0, True)
    if b is None:
        return []
    b = list(b) if isinstance(b, (list, tuple)) else [b]
    from .swapi import _w
    return [_w(sw.mod.IBody2, x) for x in b]


def mass_props(sw, model):
    bs = _bodies(sw, model)
    if not bs:
        return 0.0, (0.0, 0.0, 0.0)
    best = None
    for b in bs:
        p = b.GetMassProperties(1000.0)
        if best is None or p[3] > best[3]:
            best = p
    return best[3] * 1e9, (best[0] * 1000.0, best[1] * 1000.0, best[2] * 1000.0)


def body_count(sw, model):
    return len(_bodies(sw, model))


def _rotate_by(sw, model, delta_deg):
    if abs(delta_deg) < 1e-9:
        return

    def com_ang():
        _, com = mass_props(sw, model)
        return math.degrees(math.atan2(com[2], com[0]))

    want = (delta_deg + 180.0) % 360.0 - 180.0
    a0 = com_ang()
    for sgn in (1.0, -1.0):
        sw.rotate_bodies_y(model, sgn * delta_deg)
        mv = (com_ang() - a0 + 180.0) % 360.0 - 180.0
        if abs(mv - want) <= 0.5:
            return
        model.EditUndo2(1)
    raise RuntimeError(f"body rotate by {delta_deg:.2f} deg moved the "
                       "centroid the wrong way in both senses")


def _shift(sw, model, ax, d):
    if abs(d) < 1e-9:
        return
    _, c0 = mass_props(sw, model)
    kw = ("dx", "dy", "dz")[ax]
    for sgn in (1.0, -1.0):
        sw.move_bodies(model, **{kw: sgn * d})
        _, c1 = mass_props(sw, model)
        if abs((c1[ax] - c0[ax]) - d) <= 0.05:
            return
        model.EditUndo2(1)
    raise RuntimeError(f"body shift of {d:.2f} mm along {kw[-1]} moved the "
                       "centroid the wrong way in both senses")


def _shift_z(sw, model, dz):
    _shift(sw, model, 2, dz)


def _wedge(sm, sw, r0, r1, a0_deg, a1_deg, n=24):
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    outer = [(r1 * math.cos(a0 + (a1 - a0) * i / n),
              r1 * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    inner = [(r0 * math.cos(a0 + (a1 - a0) * i / n),
              r0 * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n, -1, -1)]
    sw.arc(sm, (0, 0), outer[0], outer[-1], True)
    sw.line(sm, outer[-1], inner[0])
    sw.arc(sm, (0, 0), inner[0], inner[-1], False)
    sw.line(sm, inner[-1], outer[0])


def build_segment(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
                  with_strut_socket: bool = True, keep_open: bool = False,
                  rods=None, tag: str = ""):
    seg = ring.segments[0]
    sweep = seg.sweep_deg
    lap = f.joint.lap_deg
    H = f.duct_height
    ym = H * f.joint.lap_height_frac
    rt = f.throat_radius
    ro = f.duct_od / 2.0

    rods = tuple(rods or ())
    mn = sorted((r for r in rods if r[3] == "main"),
                key=lambda r: abs(r[1]))
    main = mn[0] if mn else None
    rest = [r for r in rods if r is not main]
    pm = main[1] if main else 0.0
    po = -pm

    model = sw.new_part()
    front, top, right = sw.base_planes(model)

    sm = sw.begin_sketch(model, front)
    sw.centerline(sm, (0.0, -10.0), (0.0, H + 10.0))
    for e in meridian(f):
        if e[0] == "line":
            sw.line(sm, e[1], e[2])
        elif e[0] == "arc":
            sw.arc(sm, e[1], e[2], e[3], e[4])
        else:
            sw.spline(sm, e[1])
    sp = sw.end_sketch(model)

    sw.revolve(model, sp, sweep / 2.0 - po,
               angle2_deg=sweep / 2.0 + po)

    vol0, com0 = mass_props(sw, model)
    want = ring_volume(f) * sweep / 360.0
    if abs(vol0 - want) / max(want, 1.0) > 0.05:
        raise RuntimeError(f"revolve volume {vol0/1000:.1f} cm3 does not match "
                           f"the analytic {want/1000:.1f} cm3, the section "
                           "is probably self-intersecting")

    p_mid = sw.offset_plane(model, top, ym)
    a_hi = sweep / 2.0 - po
    a_lo = -(sweep / 2.0 + po)
    a1 = a_hi
    a0 = a1 - lap

    sm = sw.begin_sketch(model, p_mid)
    _wedge(sm, sw, rt - 2.0, ro + 2.0, a0, a1)
    sa = sw.end_sketch(model)

    rev = False
    try:
        sw.cut(model, sa, depth=H, reverse=rev)
        vol1, com1 = mass_props(sw, model)
        good = com1[1] <= com0[1] + 1e-6
        if not good:
            model.EditUndo2(1)
    except RuntimeError:
        good = False
    if not good:
        rev = True
        sw.cut(model, sa, depth=H, reverse=rev)
        vol1, com1 = mass_props(sw, model)
        if com1[1] > com0[1] + 1e-6:
            raise RuntimeError("could not work out which way is up for the "
                               "lap cut; centre of mass rose both times")

    sm = sw.begin_sketch(model, p_mid)
    _wedge(sm, sw, rt - 2.0, ro + 2.0, a_lo, a_lo + lap)
    sb = sw.end_sketch(model)
    sw.cut(model, sb, depth=H, reverse=not rev)

    dpz = f.stud_depth
    for ac, hiend in ((a1 - lap / 2.0, True), (a_lo + lap / 2.0, False)):
        sm = sw.begin_sketch(model, p_mid if f.joint.stud > 0 else top)
        for r in f.joint_hole_radii():
            a = math.radians(ac)
            sw.circle(sm, (r * math.cos(a), r * math.sin(a)),
                      (f.joint.stud + 0.15) if f.joint.stud > 0
                      else f.joint.bolt_size + f.joint.bolt_clearance)
        sj = sw.end_sketch(model)
        if f.joint.stud > 0:
            sw.cut(model, sj, depth=dpz,
                   reverse=(not rev if hiend else rev))
        else:
            sw.cut(model, sj, through_both=True)

    cr = None
    if main is not None and main[0] == "side":
        dia = f.outer_rod + f.rods.clearance
        sm = sw.begin_sketch(model, front)
        sw.circle(sm, (main[2], f.outer_rod_duct_y), dia)
        sr = sw.end_sketch(model)
        sw.cut(model, sr, through_both=True)
        cr = main[2]
    elif main is not None:
        sm = sw.begin_sketch(model, right)
        sw.circle(sm, (0.0, f.motor_rod_duct_y), f.mount_bore_dia)
        sr = sw.end_sketch(model)
        sw.cut(model, sr, through_both=True)
        cr = (rt + ro) / 2.0

    if cr is not None and f.joint.bolt_size > 0:
        d = f.joint.bolt_size + f.joint.bolt_clearance
        sm = sw.begin_sketch(model, top)
        sw.circle(sm, sw.top_xy(cr, 0.0), d)
        sc = sw.end_sketch(model)
        sw.cut(model, sc, through_both=True)

    for kd, pe, rd, _role in rest:
        th = (pe - pm + 180.0) % 360.0 - 180.0
        _rotate_by(sw, model, -th)
        v0, _ = mass_props(sw, model)
        if kd == "side":
            sm = sw.begin_sketch(model, front)
            sw.circle(sm, (rd, f.outer_rod_duct_y),
                      f.outer_rod + f.rods.clearance)
        else:
            sm = sw.begin_sketch(model, right)
            sw.circle(sm, (0.0, f.motor_rod_duct_y), f.mount_bore_dia)
        st = sw.end_sketch(model)
        sw.cut(model, st, through_both=True)
        v1, _ = mass_props(sw, model)
        if v1 >= v0 - 1.0:
            raise RuntimeError(f"pass-through {kd} cut at "
                               f"{pe:+.2f} deg removed no material")
        _rotate_by(sw, model, th)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_duct_segment{tag}")
    paths = [sw.save(model, base + ".SLDPRT"),
             sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, _ = mass_props(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part=f"duct segment{tag}", qty=0, files=paths,
                volume_cm3=vol / 1000.0, sweep_deg=sweep,
                lap_cut_reversed=rev,
                rods=[(k, p) for k, p, _r, _ro in rods])


def build_mount(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
                keep_open: bool = False):
    mo = f.mount
    n = max(f.rods.motor_count, 1)
    model = sw.new_part()
    front, top, right = sw.base_planes(model)

    sm = sw.begin_sketch(model, top)
    sw.circle(sm, (0.0, 0.0), f.mount_hub_od)
    sh = sw.end_sketch(model)
    sw.extrude(model, sh, f.mount_height)

    axis = sw.axis_from_planes(model, front, right)

    yr = f.mount_rod_y
    sm = sw.begin_sketch(model, right)
    sw.circle(sm, (0.0, yr), f.mount_boss_od)
    sb = sw.end_sketch(model)
    sw.extrude(model, sb, f.mount_reach)
    fb = sw.last_feature_name(model)

    sm = sw.begin_sketch(model, right)
    sw.circle(sm, (0.0, yr), f.mount_bore_dia)
    sr = sw.end_sketch(model)
    _, c0 = mass_props(sw, model)
    sw.cut(model, sr, depth=f.mount_reach, reverse=False)
    _, c1 = mass_props(sw, model)
    if c1[0] >= c0[0]:
        model.EditUndo2(1)
        sw.cut(model, sr, depth=f.mount_reach, reverse=True)
        _, c1 = mass_props(sw, model)
        if c1[0] >= c0[0]:
            raise RuntimeError("tube bore went into the hub both ways round")
    fh = sw.last_feature_name(model)

    if n > 1:
        sw.circular_pattern(model, [fb, fh], axis, n, 360.0)

    if f.mount_bore_inner_r > 0:
        sm = sw.begin_sketch(model, top)
        sw.circle(sm, (0.0, 0.0), 2.0 * f.mount_bore_inner_r)
        sg = sw.end_sketch(model)
        sw.extrude(model, sg, f.mount_height, merge=True)

    sm = sw.begin_sketch(model, top)
    if f.motor.boss_dia > 0:
        sw.circle(sm, (0.0, 0.0), f.motor.boss_dia)
    for x, z in f.motor_hole_xy():
        sw.circle(sm, (x, z), f.motor.hole_dia)
    sx = sw.end_sketch(model)
    sw.cut(model, sx, through_both=True)

    if mo.clamp_bolt > 0:
        dia = mo.clamp_bolt + mo.clamp_bolt_clearance
        sm = sw.begin_sketch(model, top)
        for i in range(n):
            a = math.radians(360.0 * i / n)
            sw.circle(sm, (f.mount_clamp_r * math.cos(a),
                           f.mount_clamp_r * math.sin(a)),
                      dia)
        sc = sw.end_sketch(model)
        sw.cut(model, sc, through_both=True)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_motor_mount")
    paths = [sw.save(model, base + ".SLDPRT"), sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, _ = mass_props(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part="motor mount", qty=4, files=paths,
                volume_cm3=vol / 1000.0, arms=n)


def build_strut(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
                keep_open: bool = False):
    st = f.struts
    H = f.duct_height
    y_c = f.strut_y
    r0 = st.hub_od / 2.0 - 8.0
    r1 = f.throat_radius + f.socket_depth - 0.3
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


def build_all(f: Frame, outdir: str, visible: bool = True, ring=None,
              keep_open: bool = False, assembly: bool = True):
    from .build_parts import (build_connector, build_center_plate, build_rod,
                              rod_specs)
    from .build_asm import build_assembly

    ring = ring or plan_ring(f)
    os.makedirs(outdir, exist_ok=True)
    sw = SolidWorks(visible=visible)
    sw.close_all()
    sw.prime()

    from .layout3d import variant_key, instances
    from .layout3d import rod_variants
    import collections

    used = collections.Counter(k for k, _, _ in instances(f, ring))

    plain = build_segment(sw, f, ring, outdir, keep_open=keep_open)
    plain["qty"] = used.get("duct_segment", 0)
    made = [plain]
    files = {"duct_segment": plain["files"][0]}

    for feats, _members in sorted(
            (k, v) for k, v in rod_variants(f, ring).items() if k is not None):
        key = variant_key(feats)
        r = build_segment(sw, f, ring, outdir, keep_open=keep_open,
                          rods=feats,
                          tag="_" + key.split("duct_segment_")[1])
        r["qty"] = used.get(key, 0)
        made.append(r)
        files[key] = r["files"][0]

    r = build_mount(sw, f, ring, outdir, keep_open=keep_open)
    made.append(r)
    files["motor_mount"] = r["files"][0]

    if f.connector.enabled:
        r = build_connector(sw, f, ring, outdir, keep_open=keep_open)
        made.append(r)
        files["connector"] = r["files"][0]

    r = build_center_plate(sw, f, outdir, keep_open=keep_open)
    made.append(r)
    files["center_plate"] = r["files"][0]

    for tag, (size, L) in rod_specs(f).items():
        r = build_rod(sw, f, size, L, tag, outdir, keep_open=keep_open)
        r["qty"] = used.get("rod_" + tag, 0)
        made.append(r)
        files["rod_" + tag] = r["files"][0]

    if assembly:
        made.append(build_assembly(sw, f, ring, files, outdir))
    return made


from .layout3d import placement_table  # noqa: E402,F401
