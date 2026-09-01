from __future__ import annotations
import math

from .params import Frame
from .bridge import Bridge


def duct_centers(f: Frame):
    s = f.motor_spacing / 2.0
    return [(-s, -s), (s, -s), (s, s), (-s, s)]


def ring_offset(f: Frame, cx: float, cz: float, ring) -> float:
    c = ring.interface_center_deg
    if cz >= 0:
        return 0.0 if cx >= 0 else (540.0 - 2.0 * c) % 360.0
    return 180.0 if cx < 0 else (540.0 - 2.0 * c + 180.0) % 360.0


def pairs(f: Frame):
    s = f.motor_spacing / 2.0
    return [(-1, [(-s, -s), (s, -s)]), (+1, [(-s, s), (s, s)])]


def bridge_outline_world(f: Frame, sign: int, n: int = 48):
    br = Bridge(f)
    s = f.motor_spacing / 2.0
    out = []
    for x, z in br.outline(n):
        out.append((x, sign * (s + z)))
    return out


def center_rod_spacing(f: Frame) -> float:
    r = f.rods
    if r.center_spacing > 0:
        return r.center_spacing
    dia = f.center.cross_bolt + 0.4
    off = (f.center_rod + r.clearance) / 2.0 + dia / 2.0 + 2.0
    from .bridge import Bridge
    br = Bridge(f)
    d_in = br.d_in
    z = -d_in * 0.75
    rch = f.duct_od / 2.0
    edge = f.motor_spacing / 2.0 - math.sqrt(max(rch ** 2 - z * z, 0.0))
    x_max = min(edge, br.pad_half) - off - dia / 2.0 - 2.0
    sp = max(2.0 * x_max, 2.0 * (f.center_rod + 4.0))

    need = f.center_bore_dia / 2.0 + (f.center.cross_bolt + 0.4) / 2.0 + 1.0
    bands = [(p - 2.0 * need, p + 2.0 * need) for p, _b in f.deck_patterns()]
    for _ in range(len(bands) + 1):
        hit = [b for b in bands if b[0] < sp < b[1]]
        if not hit:
            break
        sp = min(b[0] for b in hit) - 0.5
    return max(sp, 2.0 * (f.center_rod + 4.0))


def center_rods(f: Frame):
    r = f.rods
    s = f.motor_spacing / 2.0
    half = s - f.connector_inner_offset + f.connector_pad_width * 0.5
    spacing = center_rod_spacing(f)
    xs = [(-(r.center_count - 1) / 2.0 + i) * spacing
          for i in range(r.center_count)]
    return [(x, -half, half, f.center_rod) for x in xs]


def outer_rods(f: Frame):
    r = f.rods
    s = f.motor_spacing / 2.0
    off = s + f.duct_od / 2.0 - r.outer_inset - f.outer_rod / 2.0
    half = s + r.outer_overlap
    out = []
    for sgn in (-1, 1):
        out.append((sgn * off, -half, sgn * off, half, f.outer_rod))
        out.append((-half, sgn * off, half, sgn * off, f.outer_rod))
    return out[:r.outer_count]


def motor_rod_phase(cx: float, cz: float, mode: str = "inboard") -> float:
    a = math.degrees(math.atan2(-cz, -cx)) % 360.0
    return a if mode != "outboard" else (a + 180.0) % 360.0


def motor_rod_angles(f: Frame, cx: float, cz: float):
    n = max(f.rods.motor_count, 1)
    base = motor_rod_phase(cx, cz, f.rods.motor_phase)
    return [(base + 360.0 * i / n) % 360.0 for i in range(n)]


def motor_inboard_len(f: Frame, cx: float, cz: float):
    r = f.rods
    a = math.radians(motor_rod_phase(cx, cz, r.motor_phase))
    d = (math.cos(a), math.sin(a))
    if abs(d[0]) < 1e-9 or abs(d[1]) < 1e-9:
        return None
    tx = (-math.copysign(f.plate_x / 2.0, d[0]) - cx) / d[0]
    tz = (-math.copysign(f.plate_z / 2.0, d[1]) - cz) / d[1]
    t = max(tx, tz)
    if t <= 0:
        return None
    tip = t + (r.motor_engage or 2.5 * f.motor_rod)

    ar = f.motor_rod / 2.0 + r.clearance / 2.0
    sr = f.center_bore_dia / 2.0
    dz = abs(f.motor_rod_duct_y - f.duct_height * r.center_y_frac)
    reach = sr + ar + 1.0
    if dz < reach:
        w = math.sqrt(reach * reach - dz * dz)
        for x, _, _, _ in center_rods(f):
            lim = (x - math.copysign(w, d[0]) - cx) / d[0]
            if lim > 0:
                tip = min(tip, lim)
    return tip if tip > t else None


def motor_arm_bolt_r(f: Frame, cx: float, cz: float, tip: float):
    r = f.rods
    eng = r.motor_engage or 2.5 * f.motor_rod
    a = math.radians(motor_rod_phase(cx, cz, r.motor_phase))
    d = (math.cos(a), math.sin(a))
    br = (f.center.cross_bolt + 0.4) / 2.0
    need = f.center_bore_dia / 2.0 + br + 1.0
    xs = [x for x, _, _, _ in center_rods(f)]
    deck = [(sx, sy, (b + f.center.fc_clearance) / 2.0)
            for sp, b in f.deck_patterns()
            for sx in (-sp / 2, sp / 2) for sy in (-sp / 2, sp / 2)]
    best = None
    for k in range(41):
        rr = tip - eng + eng * k / 40.0
        px = cx + d[0] * rr
        py = cz + d[1] * rr
        m = min((abs(px - x) for x in xs), default=1e9)
        if m < need:
            continue
        if any(math.hypot(px - sx, py - sy) < br + rr2 + 1.0
               for sx, sy, rr2 in deck):
            continue
        pen = abs(rr - (tip - eng / 2.0))
        if best is None or pen < best[1]:
            best = (rr, pen)
    return best[0] if best else None


def motor_rods(f: Frame):
    r = f.rods
    hub = f.motor_rod_r0
    reach = f.duct_od / 2.0 + r.motor_protrude
    out = []
    for cx, cz in duct_centers(f):
        for idx, a in enumerate(motor_rod_angles(f, cx, cz)):
            tip = reach
            tag = "out"
            if idx == 0 and r.motor_inboard:
                far = motor_inboard_len(f, cx, cz)
                if far and far > reach:
                    tip, tag = far, "in"
            out.append((cx, cz, a, tip - hub, f.motor_rod, tag))
    return out


def _section_label(f: Frame, size: float) -> str:
    if f.rods.shape == "round":
        return f"{size:g} mm dia round"
    return f"{size:g} mm square"


def rod_cut_list(f: Frame):
    r = f.rods
    rows = []
    cr = center_rods(f)
    if cr:
        rows.append(dict(name="centre spine", qty=len(cr), size=f.center_rod,
                         section=_section_label(f, f.center_rod),
                         length=round(cr[0][2] - cr[0][1], 1)))
    orr = outer_rods(f)
    if orr:
        x0, z0, x1, z1, _ = orr[0]
        L = max(abs(x1 - x0), abs(z1 - z0))
        rows.append(dict(name="outer cage", qty=len(orr), size=f.outer_rod,
                         section=_section_label(f, f.outer_rod),
                         length=round(L, 1)))
    lens = {}
    for _, _, _, L, _, tg in motor_rods(f):
        k = (round(L, 1), tg)
        lens[k] = lens.get(k, 0) + 1
    for (L, tg), q in sorted(lens.items()):
        rows.append(dict(name="motor arm" + (" (to centre plate)" if tg == "in"
                                             else ""),
                         qty=q, size=f.motor_rod,
                         section=_section_label(f, f.motor_rod), length=L))
    return rows


def placement(f: Frame, ring):
    rows = []
    for di, (cx, cz) in enumerate(duct_centers(f)):
        off = ring_offset(f, cx, cz, ring)
        for seg in ring.segments:
            rows.append(dict(part="duct_segment", duct=di + 1,
                             x=round(cx, 2), z=round(cz, 2), y=0.0,
                             ry=round((seg.mid_deg + off) % 360.0, 2)))
        rows.append(dict(part="motor_hub", duct=di + 1, x=round(cx, 2),
                         z=round(cz, 2), y=0.0, ry=0.0))
    for sign, _ in pairs(f):
        rows.append(dict(part="connector", x=0.0, z=0.0, y=0.0,
                         ry=0.0 if sign > 0 else 180.0))
    rows.append(dict(part="center_plate", x=0.0, z=0.0,
                     y=round(f.duct_height * f.rods.center_y_frac, 2), ry=0.0))
    for x, z0, z1, _ in center_rods(f):
        rows.append(dict(part="rod_centre", x=round(x, 2),
                         z=round((z0 + z1) / 2, 2),
                         y=round(f.duct_height * f.rods.center_y_frac, 2), ry=0.0))
    for x0, z0, x1, z1, _ in outer_rods(f):
        rows.append(dict(part="rod_outer", x=round((x0 + x1) / 2, 2),
                         z=round((z0 + z1) / 2, 2),
                         y=round(f.duct_height * f.rods.outer_y_frac, 2),
                         ry=0.0 if x0 == x1 else 90.0))
    for cx, cz, a, L, _, tg in motor_rods(f):
        rows.append(dict(part="rod_motor_" + tg, x=round(cx, 2),
                         z=round(cz, 2),
                         y=round(f.duct_height * f.rods.motor_y_frac, 2),
                         ry=round(a, 2), length=round(L, 1)))
    return rows


def side_rod_crossings(f: Frame):
    out = []
    rt, ro = f.throat_radius, f.duct_od / 2.0
    for x0, z0, x1, z1, _ in outer_rods(f):
        az = abs(x1 - x0) < 1e-6
        for di, (cx, cz) in enumerate(duct_centers(f)):
            if az:
                d, ang = abs(x0 - cx), (0.0 if x0 > cx else 180.0)
            else:
                d, ang = abs(z0 - cz), (90.0 if z0 > cz else 270.0)
            if rt < d < ro:
                out.append((di, ang, d))
    return out


MIN_THRU_DEG = 0.5


def rod_segment_plan(f: Frame, ring):
    from .segment import plan_ring
    ring = ring or plan_ring(f)
    out = []
    side = {}
    for di, ang, rad in side_rod_crossings(f):
        side.setdefault(di, []).append((ang, rad))
    lap = f.joint.lap_deg
    y_mid = f.duct_height * f.joint.lap_height_frac
    for di, (cx, cz) in enumerate(duct_centers(f)):
        off = ring_offset(f, cx, cz, ring)
        want = [("motor", a, 0.0) for a in motor_rod_angles(f, cx, cz)]
        want += [("side", a, rad) for a, rad in side.get(di, [])]
        for kind, a, rad in want:
            local = (a - off) % 360.0
            rb = (f.mount_bore_dia if kind == "motor"
                  else f.outer_rod + f.rods.clearance) / 2.0
            r_at = rad if rad > 0 else (f.throat_radius + f.duct_od / 2.0) / 2.0
            bh = math.degrees(math.asin(min(0.99, rb / r_at)))
            best = None
            for seg in ring.segments:
                d = (local - seg.mid_deg + 180.0) % 360.0 - 180.0
                half = seg.sweep_deg / 2.0 - f.joint.lap_deg / 2.0 - bh
                if abs(d) <= half and (best is None or abs(d) < abs(best[1])):
                    best = (seg.index, d)

            yb = f.outer_rod_duct_y if kind == "side" else f.motor_rod_duct_y
            if kind == "side":
                ro_y = f.outer_radius_at(yb)
                th = math.sqrt(max(ro_y * ro_y - rad * rad, 0.0))
                hf = math.degrees(math.atan2(th + rb, rad))
            else:
                hf = bh

            halves = []
            if yb + rb > y_mid:
                halves.append(True)
            if yb - rb < y_mid:
                halves.append(False)
            if not halves:
                halves = [yb > y_mid]
            hit = False
            span = {}
            for up in halves:
                for seg in ring.segments:
                    a0 = seg.start_deg + (lap if up else 0.0)
                    a1 = seg.end_deg - (0.0 if up else lap)
                    d0 = (a0 - local + 180.0) % 360.0 - 180.0
                    d1 = d0 + (a1 - a0)
                    ov = min(d1, hf) - max(d0, -hf)
                    if ov > MIN_THRU_DEG:
                        span[seg.index] = max(span.get(seg.index, 0.0), ov)
            for si in sorted(span):
                hit = True
                if best is not None and si == best[0]:
                    continue
                phi = (local - ring.segments[si].mid_deg + 180.0) % 360.0 - 180.0
                out.append((di, si, phi, kind, rad, "thru"))

            if best is not None:
                out.append((di, best[0], best[1], kind, rad, "main"))
            elif not hit:
                out.append((di, None, local, kind, rad, "none"))
    return out


def segment_features(f: Frame, ring, tol: float = 0.05):
    o = {}
    for di, si, phi, kind, rad, role in rod_segment_plan(f, ring):
        if si is None:
            continue
        p = round(round(phi / tol) * tol, 3)
        o.setdefault((di, si), set()).add((kind, p, round(rad, 2), role))
    return {k: tuple(sorted(v)) for k, v in o.items()}


def rod_variants(f: Frame, ring, tol: float = 0.05):
    groups = {}
    for pos, feats in segment_features(f, ring, tol).items():
        groups.setdefault(feats, []).append(pos)
    dropped = [r for r in rod_segment_plan(f, ring) if r[1] is None]
    if dropped:
        groups[None] = dropped
    return groups


def main_phi(feats):
    mains = sorted((p for _k, p, _r, role in feats if role == "main"), key=abs)
    return mains[0] if mains else 0.0


def variant_key(feats) -> str:
    toks = ["%s%s%03d" % (kind[0], "p" if phi >= 0 else "m",
                          round(abs(phi) * 10))
            for kind, phi, _rad, _role in feats]
    return "duct_segment_" + "_".join(toks)


def instances(f: Frame, ring):
    from .layout3d import segment_features
    H = f.duct_height
    out = []
    kmap, pmap = {}, {}
    for pos, feats in segment_features(f, ring).items():
        kmap[pos] = variant_key(feats)
        pmap[pos] = main_phi(feats)

    for di, (cx, cz) in enumerate(duct_centers(f)):
        off = ring_offset(f, cx, cz, ring)
        for seg in ring.segments:
            key = kmap.get((di, seg.index), "duct_segment")
            out.append((key, seg.mid_deg + off + pmap.get((di, seg.index), 0.0),
                        (cx, 0.0, cz)))
        out.append(("motor_mount", motor_rod_phase(cx, cz),
                    (cx, H * f.rods.motor_y_frac, cz)))
    for sign, _ in pairs(f):
        out.append(("connector", 0.0 if sign > 0 else 180.0,
                    (0.0, H / 2.0, sign * f.motor_spacing / 2.0)))
    out.append(("center_plate", 0.0, (0.0, H * f.rods.center_y_frac, 0.0)))
    for x, z0, z1, _ in center_rods(f):
        out.append(("rod_centre", 0.0,
                    (x, H * f.rods.center_y_frac, (z0 + z1) / 2.0)))
    for x0, z0, x1, z1, _ in outer_rods(f):
        ry = 0.0 if x0 == x1 else 90.0
        out.append(("rod_outer", ry, ((x0 + x1) / 2.0,
                                      H * f.rods.outer_y_frac,
                                      (z0 + z1) / 2.0)))
    for cx, cz, a, L, _, tg in motor_rods(f):
        key = "rod_motor_" + tg
        off = f.motor_rod_r0 + L / 2.0
        mx = cx + off * math.cos(math.radians(a))
        mz = cz + off * math.sin(math.radians(a))
        out.append((key, a - 90.0, (mx, f.motor_rod_duct_y, mz)))
    return out


def placement_table(f: Frame, ring):
    return [dict(part=k, ry_deg=round(ry, 2), x=round(p[0], 2),
                 y=round(p[1], 2), z=round(p[2], 2))
            for k, ry, p in instances(f, ring)]

def center_cross_bolts(f: Frame):
    c = f.center
    if c.cross_bolt <= 0:
        return []
    br = (c.cross_bolt + 0.4) / 2.0
    lim = f.plate_z / 2.0 - br - 2.0
    keep = []
    for span, bolt in f.deck_patterns():
        rr = (bolt + c.fc_clearance) / 2.0
        keep += [(sx, sy, rr) for sx in (-span / 2, span / 2)
                 for sy in (-span / 2, span / 2)]
    arms = []
    hub = f.motor_rod_r0
    for cx, cz, ang, L, sz, tg in motor_rods(f):
        if tg == "in":
            a = math.radians(ang)
            arms.append((cx, cz, math.cos(a), math.sin(a), hub + L,
                         (sz + f.rods.clearance) / 2.0))

    def ok(x, y):
        for sx, sy, rr in keep:
            if math.hypot(x - sx, y - sy) < br + rr + 1.0:
                return False
        for cx, cz, dx, dy, tip, ar in arms:
            t = max(0.0, min(tip, (x - cx) * dx + (y - cz) * dy))
            if math.hypot(x - (cx + dx * t), y - (cz + dy * t)) < br + ar + 1.0:
                return False
        return True

    out = []
    for x, _, _, _ in center_rods(f):
        for sgn in (-1.0, 1.0):
            want = sgn * min(c.cross_bolt_offset, lim)
            best = None
            for k in range(81):
                y = sgn * lim * (1.0 - k / 80.0)
                if ok(x, y) and (best is None or abs(y - want) < abs(best - want)):
                    best = y
            if best is not None:
                out.append((x, best))
    return out

