from __future__ import annotations
import math
import os

from build123d import (Align, Axis, Box, Cylinder, Line, Plane, Polyline, Pos,
                       Rot, Spline, ThreePointArc, export_step, export_stl,
                       make_face, revolve, Compound)

from .params import Frame
from .profile import meridian, ring_volume
from .segment import RingPlan, plan_ring
from .layout3d import (center_rods, outer_rods, motor_rods, instances,
                       variant_key, rod_variants, center_rod_spacing,
                       duct_centers)
from .bridge import Bridge


def _cyl(origin, direction, dia, length):
    return (Plane(origin=origin, z_dir=direction)
            * Cylinder(radius=dia / 2.0, height=length))


def _wedge(r0, r1, z0, z1, a0, a1):
    face = make_face(Polyline((r0, z0), (r1, z0), (r1, z1), (r0, z1),
                              close=True))
    return Rot(0, 0, a0) * revolve(Plane.XZ * face, axis=Axis.Z,
                                   revolution_arc=(a1 - a0))


def _meridian_face(f: Frame):
    ents = []
    for e in meridian(f):
        if e[0] == "line":
            ents.append(Line(e[1], e[2]))
        elif e[0] == "arc":
            _, c, p0, p1, ccw = e
            a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
            a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
            if ccw and a1 < a0:
                a1 += 2 * math.pi
            if not ccw and a1 > a0:
                a1 -= 2 * math.pi
            r = math.hypot(p0[0] - c[0], p0[1] - c[1])
            am = (a0 + a1) / 2.0
            ents.append(ThreePointArc(
                p0, (c[0] + r * math.cos(am), c[1] + r * math.sin(am)), p1))
        else:
            ents.append(Spline(*e[1]))
    wire = ents[0]
    for e in ents[1:]:
        wire = wire + e
    return make_face(wire)


def _poly_prism(pts, z0, z1):
    from build123d import extrude
    face = make_face(Polyline(*pts, close=True))
    return Pos(0, 0, z0) * extrude(face, amount=(z1 - z0))


def _save(part, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, name)
    export_step(part, base + ".STEP")
    export_stl(part, base + ".STL")
    return [base + ".STEP", base + ".STL"]


def build_segment(f: Frame, ring: RingPlan, outdir: str, rods=(), tag: str = ""):
    seg = ring.segments[0]
    sweep, lap = seg.sweep_deg, f.joint.lap_deg
    H = f.duct_height
    zm = H * f.joint.lap_height_frac
    rt, ro = f.throat_radius, f.duct_od / 2.0
    rods = tuple(rods or ())

    part = Rot(0, 0, -sweep / 2.0) * revolve(
        Plane.XZ * _meridian_face(f), axis=Axis.Z, revolution_arc=sweep)

    want = ring_volume(f) * sweep / 360.0
    if abs(part.volume - want) / max(want, 1.0) > 0.05:
        raise RuntimeError(f"revolve {part.volume/1000:.1f} cm3 against an "
                           f"analytic {want/1000:.1f}, section is probably "
                           "self-intersecting")

    a_hi, a_lo = sweep / 2.0, -sweep / 2.0
    part -= _wedge(rt - 2, ro + 2, zm, H + 2, a_lo, a_lo + lap)
    part -= _wedge(rt - 2, ro + 2, -2, zm, a_hi - lap, a_hi)

    dp = f.stud_depth
    for r in f.joint_hole_radii():
        for ac, up in ((a_hi - lap / 2.0, True), (a_lo + lap / 2.0, False)):
            a = math.radians(ac)
            x, y = r * math.cos(a), r * math.sin(a)
            if f.joint.stud > 0:
                z = zm + dp / 2.0 if up else zm - dp / 2.0
                part -= _cyl((x, y, z), (0, 0, 1), f.joint.stud + 0.15, dp)
            else:
                part -= _cyl((x, y, H / 2.0), (0, 0, 1),
                             f.joint.bolt_size + f.joint.bolt_clearance, H * 4)

    mains = sorted((x for x in rods if x[3] == "main"), key=lambda x: abs(x[1]))
    main = mains[0] if mains else None

    for kind, phi, rad, _role in rods:
        a = math.radians(phi)
        if kind == "side":
            part -= _cyl((rad * math.cos(a), rad * math.sin(a),
                          f.outer_rod_duct_y),
                         (-math.sin(a), math.cos(a), 0.0),
                         f.outer_rod + f.rods.clearance, 4 * ro)
        else:
            part -= _cyl((0.0, 0.0, f.motor_rod_duct_y),
                         (math.cos(a), math.sin(a), 0.0),
                         f.mount_bore_dia, 4 * ro)

    if main is not None and f.joint.bolt_size > 0:
        kind, phi, rad, _role = main
        a = math.radians(phi)
        cr = rad if kind == "side" else (rt + ro) / 2.0
        d = f.joint.bolt_size + f.joint.bolt_clearance
        part -= _cyl((cr * math.cos(a), cr * math.sin(a), H / 2.0),
                     (0, 0, 1), d, H * 4)

    if main is not None:
        part = Rot(0, 0, -main[1]) * part

    files = _save(part, outdir, f"{f.name}_duct_segment{tag}")
    return dict(part=f"duct segment{tag}", qty=0, files=files,
                volume_cm3=part.volume / 1000.0, sweep_deg=sweep,
                rods=[(k, p) for k, p, _r, _ro in rods], solid=part)


def build_mount(f: Frame, outdir: str):
    n = max(f.rods.motor_count, 1)
    Hm = f.mount_height
    part = Pos(0, 0, Hm / 2.0) * Cylinder(radius=f.mount_hub_od / 2.0, height=Hm)

    for i in range(n):
        a = math.radians(360.0 * i / n)
        d = (math.cos(a), math.sin(a), 0.0)
        mid = f.mount_reach / 2.0
        part += _cyl((mid * d[0], mid * d[1], f.mount_rod_y), d,
                     f.mount_boss_od, f.mount_reach)
    for i in range(n):
        a = math.radians(360.0 * i / n)
        d = (math.cos(a), math.sin(a), 0.0)
        mid = f.mount_reach / 2.0
        part -= _cyl((mid * d[0], mid * d[1], f.mount_rod_y), d,
                     f.mount_bore_dia, f.mount_reach)

    if f.mount_bore_inner_r > 0:
        part += Pos(0, 0, Hm / 2.0) * Cylinder(radius=f.mount_bore_inner_r,
                                               height=Hm)

    if f.motor.boss_dia > 0:
        part -= _cyl((0, 0, Hm / 2.0), (0, 0, 1), f.motor.boss_dia, Hm * 4)
    for x, z in f.motor_hole_xy():
        part -= _cyl((x, z, Hm / 2.0), (0, 0, 1), f.motor.hole_dia, Hm * 4)

    if f.mount.clamp_bolt > 0:
        d = f.mount.clamp_bolt + f.mount.clamp_bolt_clearance
        for i in range(n):
            a = math.radians(360.0 * i / n)
            part -= _cyl((f.mount_clamp_r * math.cos(a),
                          f.mount_clamp_r * math.sin(a), Hm / 2.0),
                         (0, 0, 1), d, Hm * 4)

    files = _save(part, outdir, f"{f.name}_motor_mount")
    return dict(part="motor mount", qty=4, files=files,
                volume_cm3=part.volume / 1000.0, arms=n, solid=part)


def build_connector(f: Frame, ring: RingPlan, outdir: str):
    br = Bridge(f)
    S, H = f.motor_spacing, f.duct_height
    Ro = f.duct_od / 2.0
    lap = f.joint.lap_deg
    a_lo = (br.interface_center_deg - br.interface_deg / 2.0) % 360.0
    a_hi = (br.interface_center_deg + br.interface_deg / 2.0) % 360.0

    part = None
    for sgn in (+1, -1):
        stub = Pos(sgn * S / 2.0, 0, -H / 2.0) * revolve(
            Plane.XZ * _meridian_face(f), axis=Axis.Z, revolution_arc=360.0)
        part = stub if part is None else part + stub

    part += _poly_prism(br.outline(64), -H / 2.0, H / 2.0)

    ends = []
    for sgn in (+1, -1):
        cx = sgn * S / 2.0
        lo, hi = (a_lo, a_hi) if sgn > 0 else (180.0 - a_hi, 180.0 - a_lo)
        lo, hi = lo - lap / 2.0, hi + lap / 2.0
        ends.append((cx, lo, hi))
        gap = 360.0 - (hi - lo) % 360.0
        for k in range(2):
            g0 = hi + k * gap / 2.0
            part -= Pos(cx, 0, 0) * _wedge(f.throat_radius * 0.5, Ro + 0.05,
                                           -H, H, g0, g0 + gap / 2.0)

    for cx, lo, hi in ends:
        part -= Pos(cx, 0, 0) * _wedge(f.throat_radius - 2.0, Ro + 0.05,
                                       -H, 0.0, hi - lap, hi)
        part -= Pos(cx, 0, 0) * _wedge(f.throat_radius - 2.0, Ro + 0.05,
                                       0.0, H, lo, lo + lap)

    em = f.joint.bolt_edge_margin
    dia = f.joint.bolt_size + f.joint.bolt_clearance
    for cx, lo, hi in ends:
        for ac in (hi - lap / 2.0, lo + lap / 2.0):
            for rr in (f.throat_radius + em, Ro - em):
                a = math.radians(ac)
                part -= _cyl((cx + rr * math.cos(a), rr * math.sin(a), 0.0),
                             (0, 0, 1), dia, H * 4)

    z_rod = H * (f.rods.center_y_frac - 0.5)
    bore = f.center_bore_dia
    for x, _, _, _ in center_rods(f):
        if f.rods.shape == "round":
            part -= _cyl((x, 0.0, z_rod), (0, 1, 0), bore, 4 * S)
        else:
            part -= Pos(x, 0, z_rod) * Box(bore, 4 * S, bore)

    d = f.center.cross_bolt + 0.4
    holes = br.rod_cross_bolts(d) if f.center.cross_bolt > 0 else []
    for hx, hy in holes:
        part -= _cyl((hx, hy, 0.0), (0, 0, 1), d, H * 4)

    from .layout3d import motor_rod_angles
    reach = f.duct_od / 2.0 + f.rods.motor_protrude
    z_rod = f.motor_rod_duct_y - H / 2.0
    cent = duct_centers(f)
    rw = (f.throat_radius + Ro) / 2.0
    for (cx, lo, hi), di in zip(ends, (2, 3)):
        span = (hi - lo) % 360.0
        for ang in motor_rod_angles(f, *cent[di]):
            a = math.radians(ang)
            dv = (math.cos(a), math.sin(a), 0.0)
            part -= _cyl((cx + dv[0] * reach / 2.0, dv[1] * reach / 2.0, z_rod),
                         dv, f.mount_bore_dia, reach)
            if f.joint.bolt_size > 0 and ((ang - lo) % 360.0) <= span:
                part -= _cyl((cx + dv[0] * rw, dv[1] * rw, 0.0), (0, 0, 1),
                             f.joint.bolt_size + f.joint.bolt_clearance, H * 4)

    files = _save(part, outdir, f"{f.name}_connector")
    return dict(part="connector", qty=2, files=files,
                volume_cm3=part.volume / 1000.0,
                interface_deg=round(br.interface_deg, 2), origin="mid-plane",
                rod_bolts=len(holes), solid=part)


def build_center_plate(f: Frame, outdir: str):
    c = f.center
    lo, hi = f.center_plate_span()
    Hp = hi - lo
    bore = f.center_bore_dia

    part = Pos(0, 0, (lo + hi) / 2.0) * Box(f.plate_x, f.plate_z, Hp)

    dp = f.deck_depth()
    for span, bolt in f.deck_patterns():
        for sx in (-span / 2, span / 2):
            for sy in (-span / 2, span / 2):
                if dp > 1.0:
                    part -= _cyl((sx, sy, hi - dp / 2.0), (0, 0, 1),
                                 bolt + c.fc_clearance, dp)
                else:
                    part -= _cyl((sx, sy, 0), (0, 0, 1),
                                 bolt + c.fc_clearance, Hp * 4)

    if c.stack_span > 0 and c.stack_counterbore > 0:
        dp = Hp * 0.15
        for sx in (-c.stack_span / 2, c.stack_span / 2):
            for sy in (-c.stack_span / 2, c.stack_span / 2):
                part -= _cyl((sx, sy, hi - dp / 2.0), (0, 0, 1),
                             c.stack_counterbore, dp)

    for x, _, _, _ in center_rods(f):
        if f.rods.shape == "round":
            part -= _cyl((x, 0, 0), (0, 1, 0), bore, f.plate_z * 4)
        else:
            part -= Pos(x, 0, 0) * Box(bore, f.plate_z * 4, bore)

    from .layout3d import center_cross_bolts
    for bx, by in center_cross_bolts(f):
        part -= _cyl((bx, by, 0), (0, 0, 1), c.cross_bolt + 0.4, Hp * 4)

    zr = f.motor_rod_duct_y - f.duct_height * f.rods.center_y_frac
    hub = f.motor_rod_r0
    eng = f.rods.motor_engage or 2.5 * f.motor_rod
    from .layout3d import motor_arm_bolt_r
    arms = []
    for cx, cz, ang, L, sz, tg in motor_rods(f):
        if tg != "in":
            continue
        a = math.radians(ang)
        dv = (math.cos(a), math.sin(a), 0.0)
        tip = hub + L
        part -= _cyl((cx + dv[0] * tip / 2.0, cz + dv[1] * tip / 2.0, zr),
                     dv, sz + f.rods.clearance, tip)
        br = motor_arm_bolt_r(f, cx, cz, tip)
        if br is not None:
            arms.append((cx + dv[0] * br, cz + dv[1] * br))
    if f.center.cross_bolt > 0:
        for ax, ay in arms:
            part -= _cyl((ax, ay, 0), (0, 0, 1), f.center.cross_bolt + 0.4,
                         Hp * 4)

    half = center_rod_spacing(f) / 2.0 - bore / 2.0 - 2.0
    flr = lo
    if arms:
        flr = max(lo, zr + f.mount_bore_dia / 2.0 + 2.0)
    if f.rods.center_count >= 2 and half >= 5.0 and flr < -1.0:
        part -= Pos(0, 0, flr / 2.0) * Box(2 * half, f.plate_z * 2, -flr)

    if arms and flr > lo + 1.0:
        rr = min(math.hypot(ax, ay) for ax, ay in arms) - eng / 2.0             - f.mount_bore_dia / 2.0 - 3.0
        if rr > 6.0:
            part -= Pos(0, 0, (lo + flr) / 2.0) * Cylinder(
                radius=rr, height=flr - lo)

    files = _save(part, outdir, f"{f.name}_center_plate")
    return dict(part="center plate", qty=1, files=files,
                volume_cm3=part.volume / 1000.0, height_mm=round(Hp, 2),
                span_mm=(round(lo, 2), round(hi, 2)),
                arms=len(arms), origin="rod-axis", solid=part)


def build_rod(f: Frame, size: float, length: float, tag: str, outdir: str):
    if f.rods.shape == "round":
        part = _cyl((0, 0, 0), (0, 1, 0), size, length)
    else:
        part = Box(size, length, size)
    files = _save(part, outdir, f"{f.name}_rod_{tag}")
    return dict(part=f"rod {tag}", qty=0, files=files,
                volume_cm3=part.volume / 1000.0, length_mm=length,
                size_mm=size, solid=part)


def rod_specs(f: Frame):
    out = {}
    for x, z0, z1, sz in center_rods(f):
        out["centre"] = (sz, round(z1 - z0, 2))
    for x0, z0, x1, z1, sz in outer_rods(f):
        out["outer"] = (sz, round(max(abs(x1 - x0), abs(z1 - z0)), 2))
    for _, _, _, L, sz, tg in motor_rods(f):
        out["motor_" + tg] = (sz, round(L, 2))
    return out


def build_assembly(f: Frame, ring: RingPlan, solids: dict, outdir: str):
    placed, missing = [], set()
    for key, ry, (x, y, z) in instances(f, ring):
        s = solids.get(key)
        if s is None:
            missing.add(key)
            continue
        placed.append(Pos(x, z, y) * Rot(0, 0, ry) * s)

    asm = Compound(children=placed)
    files = _save(asm, outdir, f"{f.name}_frame")
    return dict(part="ASSEMBLY", qty=1, files=files, components=len(placed),
                missing=sorted(missing), solid=asm)


def build_all(f: Frame, outdir: str, ring=None, assembly: bool = True):
    import collections
    ring = ring or plan_ring(f)
    os.makedirs(outdir, exist_ok=True)
    used = collections.Counter(k for k, _, _ in instances(f, ring))

    made, solids = [], {}

    plain = build_segment(f, ring, outdir)
    plain["qty"] = used.get("duct_segment", 0)
    made.append(plain)
    solids["duct_segment"] = plain["solid"]

    for feats, _members in sorted(
            (k, v) for k, v in rod_variants(f, ring).items() if k is not None):
        key = variant_key(feats)
        r = build_segment(f, ring, outdir, rods=feats,
                          tag="_" + key.split("duct_segment_")[1])
        r["qty"] = used.get(key, 0)
        made.append(r)
        solids[key] = r["solid"]

    r = build_mount(f, outdir)
    made.append(r)
    solids["motor_mount"] = r["solid"]

    if f.connector.enabled:
        r = build_connector(f, ring, outdir)
        made.append(r)
        solids["connector"] = r["solid"]

    r = build_center_plate(f, outdir)
    made.append(r)
    solids["center_plate"] = r["solid"]

    for tag, (size, length) in rod_specs(f).items():
        r = build_rod(f, size, length, tag, outdir)
        r["qty"] = used.get("rod_" + tag, 0)
        made.append(r)
        solids["rod_" + tag] = r["solid"]

    if assembly:
        made.append(build_assembly(f, ring, solids, outdir))
    return made
