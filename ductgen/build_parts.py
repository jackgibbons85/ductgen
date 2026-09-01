from __future__ import annotations
import math
import os

from .params import Frame
from .profile import meridian
from .bridge import Bridge
from .segment import RingPlan
from .swapi import SolidWorks
from .layout3d import center_rods, outer_rods, motor_rods


def _mass(sw, model):
    from .build_sw import mass_props
    return mass_props(sw, model)


def _sector(sm, sw, cx, cz, r0, r1, a0_deg, a1_deg):
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    c = sw.top_xy(cx, cz)

    def pt(r, a):
        return sw.top_xy(cx + r * math.cos(a), cz + r * math.sin(a))

    ccw = (a1 > a0) == (sw.top_sketch_z_sign() > 0)
    o0, o1, i0, i1 = pt(r1, a0), pt(r1, a1), pt(r0, a0), pt(r0, a1)
    sw.arc(sm, c, o0, o1, ccw)
    sw.line(sm, o1, i1)
    sw.arc(sm, c, i1, i0, not ccw)
    sw.line(sm, i0, o0)


def _rod_socket(sm, sw, f: Frame, x: float, y_center: float):
    r = f.rods
    if r.shape == "round":
        sw.circle(sm, (x, y_center), f.center_rod + r.clearance)
    else:
        w = (f.center_rod + r.clearance) / 2.0
        sw.polygon(sm, [(x - w, y_center - w), (x + w, y_center - w),
                        (x + w, y_center + w), (x - w, y_center + w)])


def _poly(sm, sw, pts):
    q = [sw.top_xy(x, z) for x, z in pts]
    for i in range(len(q)):
        sw.line(sm, q[i], q[(i + 1) % len(q)])


def build_connector(sw: SolidWorks, f: Frame, ring: RingPlan, outdir: str,
                    keep_open: bool = False):
    br = Bridge(f)
    S = f.motor_spacing
    Ro = f.duct_od / 2.0
    H = f.duct_height
    a_lo = (br.interface_center_deg - br.interface_deg / 2.0) % 360.0
    a_hi = (br.interface_center_deg + br.interface_deg / 2.0) % 360.0

    sw.prime()
    model = sw.new_part()
    front, top, right = sw.base_planes(model)

    for sgn in (+1, -1):
        axis = sgn * S / 2.0
        sm = sw.begin_sketch(model, front)
        sw.centerline(sm, (axis, -H), (axis, H))
        for e in meridian(f):
            def m(p):
                return (axis - sgn * p[0], p[1] - H / 2.0)
            if e[0] == "line":
                sw.line(sm, m(e[1]), m(e[2]))
            elif e[0] == "arc":
                sw.arc(sm, m(e[1]), m(e[2]), m(e[3]), not e[4])
            else:
                sw.spline(sm, [m(p) for p in e[1]])
        s = sw.end_sketch(model)
        sw.revolve(model, s, 360.0, merge=False)

    sm = sw.begin_sketch(model, top)
    _poly(sm, sw, [(x, z) for x, z in br.outline(64)])
    s_web = sw.end_sketch(model)
    sw.extrude(model, s_web, H / 2.0, both=True, merge=True,
                feat_scope=False)

    lap = f.joint.lap_deg
    ends = []
    for sgn in (+1, -1):
        cx = sgn * S / 2.0
        lo, hi = (a_lo, a_hi) if sgn > 0 else (180.0 - a_hi, 180.0 - a_lo)
        lo, hi = lo - lap / 2.0, hi + lap / 2.0
        ends.append((cx, lo, hi))
        keep = (hi - lo) % 360.0
        gap = 360.0 - keep
        for k in range(2):
            g0 = hi + k * gap / 2.0
            g1 = g0 + gap / 2.0
            sm = sw.begin_sketch(model, top)
            _sector(sm, sw, cx, 0.0, f.throat_radius * 0.5, Ro + 0.05, g0, g1)
            s = sw.end_sketch(model)
            sw.cut(model, s, through_both=True, feat_scope=False)

    up = sw.cut_up_reverse()
    for cx, lo, hi in ends:
        for a0, a1, rmup in ((hi - lap, hi, False), (lo, lo + lap, True)):
            sm = sw.begin_sketch(model, top)
            _sector(sm, sw, cx, 0.0, f.throat_radius - 2.0, Ro + 0.05, a0, a1)
            s = sw.end_sketch(model)
            sw.cut(model, s, depth=H, reverse=(up if rmup else not up),
                   feat_scope=False)

    dp = f.stud_depth
    up = sw.cut_up_reverse()
    for cx, lo, hi in ends:
        for ac, hiend in ((hi - lap / 2.0, True), (lo + lap / 2.0, False)):
            sm = sw.begin_sketch(model, top)
            for rr in f.joint_hole_radii():
                x = cx + rr * math.cos(math.radians(ac))
                z = rr * math.sin(math.radians(ac))
                sw.circle(sm, sw.top_xy(x, z),
                          (f.joint.stud + 0.15) if f.joint.stud > 0
                          else f.joint.bolt_size + f.joint.bolt_clearance)
            s = sw.end_sketch(model)
            if f.joint.stud > 0:
                sw.cut(model, s, depth=dp,
                       reverse=(up if hiend else not up), feat_scope=False)
            else:
                sw.cut(model, s, through_both=True, feat_scope=False)

    yr = H * (f.rods.center_y_frac - 0.5)
    for x, _, _, _ in center_rods(f):
        sm = sw.begin_sketch(model, front)
        _rod_socket(sm, sw, f, x, yr)
        s = sw.end_sketch(model)
        sw.cut(model, s, through_both=True, feat_scope=False)

    from .build_sw import _rotate_by, _shift_z
    from .layout3d import motor_rod_angles, duct_centers
    y_rod = f.motor_rod_duct_y - H / 2.0
    reach = Ro + f.rods.motor_protrude
    cent = duct_centers(f)

    def meets(cx, lo, hi, ang, n=96):
        a = math.radians(ang)
        span = (hi - lo) % 360.0
        for i in range(1, n + 1):
            t = reach * i / n
            x, z = cx + t * math.cos(a), t * math.sin(a)
            d = math.hypot(x - cx, z)
            if f.throat_radius <= d <= Ro:
                th = math.degrees(math.atan2(z, x - cx))
                if ((th - lo) % 360.0) <= span:
                    return True
            if br.contains(x, z):
                return True
        return False

    for (cx, lo, hi), di in zip(ends, (2, 3)):
        for ang in motor_rod_angles(f, *cent[di]):
            if not meets(cx, lo, hi, ang):
                continue
            delta = 90.0 - ang
            _rotate_by(sw, model, delta)
            r = math.radians(delta if cx > 0 else delta + 180.0)
            zc = S / 2.0 * math.sin(r)
            _shift_z(sw, model, -zc)
            sm = sw.begin_sketch(model, front)
            sw.circle(sm, (S / 2.0 * math.cos(r), y_rod), f.mount_bore_dia)
            s = sw.end_sketch(model)
            sw.cut(model, s, depth=reach, reverse=sw.cut_front_reverse(),
                   feat_scope=False)
            _shift_z(sw, model, zc)
            _rotate_by(sw, model, -delta)
            if f.joint.bolt_size > 0 and ((ang - lo) % 360.0) <= (hi - lo) % 360.0:
                rw = (f.throat_radius + Ro) / 2.0
                sm = sw.begin_sketch(model, top)
                sw.circle(sm, sw.top_xy(cx + rw * math.cos(math.radians(ang)),
                                        rw * math.sin(math.radians(ang))),
                          f.joint.bolt_size + f.joint.bolt_clearance)
                s = sw.end_sketch(model)
                sw.cut(model, s, through_both=True, feat_scope=False)

    d = f.center.cross_bolt + 0.4
    hs = br.rod_cross_bolts(d) if f.center.cross_bolt > 0 else []
    if hs:
        sm = sw.begin_sketch(model, top)
        for hx, hz in hs:
            sw.circle(sm, sw.top_xy(hx, hz), d)
        s = sw.end_sketch(model)
        sw.cut(model, s, through_both=True)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_connector")
    paths = [sw.save(model, base + ".SLDPRT"), sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, com = _mass(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part="connector", qty=2, files=paths, volume_cm3=vol / 1000.0,
                interface_deg=round(br.interface_deg, 2), origin="mid-plane",
                rod_bolts=len(hs), corners_rounded=br.corners_rounded)


def build_center_plate(sw: SolidWorks, f: Frame, outdir: str,
                       keep_open: bool = False):
    from .build_sw import _rotate_by, _shift
    from .layout3d import motor_rods, motor_arm_bolt_r
    c = f.center
    lo, hi = f.center_plate_span()
    H = hi - lo
    bd = f.center_bore_dia
    sw.prime()
    model = sw.new_part()
    front, top, right = sw.base_planes(model)

    sm = sw.begin_sketch(model, top)
    _poly(sm, sw, [(-f.plate_x / 2, -f.plate_z / 2), (f.plate_x / 2, -f.plate_z / 2),
                   (f.plate_x / 2, f.plate_z / 2), (-f.plate_x / 2, f.plate_z / 2)])
    s = sw.end_sketch(model)
    sw.extrude(model, s, H / 2.0, both=True)
    _shift(sw, model, 1, (lo + hi) / 2.0)

    dp = f.deck_depth()
    sm = sw.begin_sketch(model, top)
    for span, bolt in f.deck_patterns():
        for sx in (-span / 2, span / 2):
            for sz in (-span / 2, span / 2):
                sw.circle(sm, sw.top_xy(sx, sz), bolt + c.fc_clearance)
    s = sw.end_sketch(model)
    if dp > 1.0:
        _shift(sw, model, 1, -hi)
        sw.cut(model, s, depth=dp, reverse=not sw.cut_up_reverse())
        _shift(sw, model, 1, hi)
    else:
        sw.cut(model, s, through_both=True)

    if c.stack_span > 0 and c.stack_counterbore > 0:
        dp = H * 0.15
        _shift(sw, model, 1, -hi)
        sm = sw.begin_sketch(model, top)
        for sx in (-c.stack_span / 2, c.stack_span / 2):
            for sz in (-c.stack_span / 2, c.stack_span / 2):
                sw.circle(sm, sw.top_xy(sx, sz), c.stack_counterbore)
        s = sw.end_sketch(model)
        sw.cut(model, s, depth=dp, reverse=not sw.cut_up_reverse())
        _shift(sw, model, 1, hi)

    for x, _, _, _ in center_rods(f):
        sm = sw.begin_sketch(model, front)
        _rod_socket(sm, sw, f, x, 0.0)
        s = sw.end_sketch(model)
        sw.cut(model, s, through_both=True)

    from .layout3d import center_cross_bolts
    bolts = center_cross_bolts(f)
    if bolts:
        sm = sw.begin_sketch(model, top)
        for bx, bz in bolts:
            sw.circle(sm, sw.top_xy(bx, bz), c.cross_bolt + 0.4)
        s = sw.end_sketch(model)
        sw.cut(model, s, through_both=True)

    from .layout3d import center_rod_spacing
    half = center_rod_spacing(f) / 2.0 - bd / 2.0 - 2.0

    zr = f.motor_rod_duct_y - f.duct_height * f.rods.center_y_frac
    hub = f.motor_rod_r0
    eng = f.rods.motor_engage or 2.5 * f.motor_rod
    arms = []
    for cx, cz, ang, L, sz, tg in motor_rods(f):
        if tg != "in":
            continue
        tip = hub + L
        delta = 90.0 - ang
        r = math.hypot(cx, cz)
        th = math.radians(math.degrees(math.atan2(cz, cx)) + delta)
        _rotate_by(sw, model, delta)
        _shift(sw, model, 2, -r * math.sin(th))
        sm = sw.begin_sketch(model, front)
        sw.circle(sm, (r * math.cos(th), zr), sz + f.rods.clearance)
        s = sw.end_sketch(model)
        sw.cut(model, s, depth=tip, reverse=sw.cut_front_reverse())
        _shift(sw, model, 2, r * math.sin(th))
        _rotate_by(sw, model, -delta)
        a = math.radians(ang)
        br = motor_arm_bolt_r(f, cx, cz, tip)
        if br is not None:
            arms.append((cx + math.cos(a) * br, cz + math.sin(a) * br))
    if arms and c.cross_bolt > 0:
        sm = sw.begin_sketch(model, top)
        for ax, az in arms:
            sw.circle(sm, sw.top_xy(ax, az), c.cross_bolt + 0.4)
        s = sw.end_sketch(model)
        sw.cut(model, s, through_both=True)

    flr = max(lo, zr + f.mount_bore_dia / 2.0 + 2.0) if arms else lo
    if f.rods.center_count >= 2 and half >= 5.0:
        if flr < -1.0:
            sm = sw.begin_sketch(model, top)
            _poly(sm, sw, [(-half, -f.plate_z / 2 - 1), (half, -f.plate_z / 2 - 1),
                           (half, f.plate_z / 2 + 1), (-half, f.plate_z / 2 + 1)])
            s = sw.end_sketch(model)
            sw.cut(model, s, depth=-flr, reverse=not sw.cut_up_reverse())

    if arms and flr > lo + 1.0:
        rr = min(math.hypot(ax, az) for ax, az in arms) - eng / 2.0             - f.mount_bore_dia / 2.0 - 3.0
        if rr > 6.0:
            _shift(sw, model, 1, -flr)
            sm = sw.begin_sketch(model, top)
            sw.circle(sm, sw.top_xy(0.0, 0.0), 2.0 * rr)
            s = sw.end_sketch(model)
            sw.cut(model, s, depth=flr - lo, reverse=not sw.cut_up_reverse())
            _shift(sw, model, 1, flr)

    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_center_plate")
    paths = [sw.save(model, base + ".SLDPRT"), sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    vol, _ = _mass(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part="center plate", qty=1, files=paths,
                volume_cm3=vol / 1000.0, height_mm=round(H, 2),
                span_mm=(round(lo, 2), round(hi, 2)),
                arms=len(arms), origin="rod-axis")


def build_rod(sw: SolidWorks, f: Frame, size: float, length: float,
              tag: str, outdir: str, keep_open: bool = False):
    model = sw.new_part()
    front, top, right = sw.base_planes(model)
    sm = sw.begin_sketch(model, front)
    if f.rods.shape == "round":
        sw.circle(sm, (0.0, 0.0), size)
    else:
        sw.polygon(sm, [(-size / 2, -size / 2), (size / 2, -size / 2),
                        (size / 2, size / 2), (-size / 2, size / 2)])
    s = sw.end_sketch(model)
    sw.extrude(model, s, length / 2.0, both=True)
    sw.rebuild(model)
    base = os.path.join(outdir, f"{f.name}_rod_{tag}")
    paths = [sw.save(model, base + ".SLDPRT"), sw.save(model, base + ".STEP")]
    vol, _ = _mass(sw, model)
    if not keep_open:
        sw.close(model)
    return dict(part=f"rod {tag}", qty=0, files=paths, volume_cm3=vol / 1000.0,
                length_mm=length, size_mm=size)


def rod_specs(f: Frame):
    out = {}
    for x, z0, z1, sz in center_rods(f):
        out["centre"] = (sz, round(z1 - z0, 2))
    for x0, z0, x1, z1, sz in outer_rods(f):
        out["outer"] = (sz, round(max(abs(x1 - x0), abs(z1 - z0)), 2))
    for _, _, _, L, sz, tg in motor_rods(f):
        out["motor_" + tg] = (sz, round(L, 2))
    return out
