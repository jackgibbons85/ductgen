from __future__ import annotations
import math
import itertools


class Hole:
    def __init__(self, name, p, d, dia, t0, t1, kind="hole"):
        n = math.dist((0, 0, 0), d)
        self.name = name
        self.p = tuple(p)
        self.d = tuple(x / n for x in d)
        self.r = dia / 2.0
        self.t0, self.t1 = t0, t1
        self.kind = kind

    def ends(self):
        return (tuple(self.p[i] + self.d[i] * self.t0 for i in range(3)),
                tuple(self.p[i] + self.d[i] * self.t1 for i in range(3)))

    def __repr__(self):
        return f"{self.name}(d={self.r*2:.2f})"


def _seg_dist(a0, a1, b0, b1):
    u = [a1[i] - a0[i] for i in range(3)]
    v = [b1[i] - b0[i] for i in range(3)]
    w = [a0[i] - b0[i] for i in range(3)]
    dot = lambda p, q: sum(p[i] * q[i] for i in range(3))       # noqa: E731
    a, b, c = dot(u, u), dot(u, v), dot(v, v)
    d, e = dot(u, w), dot(v, w)
    den = a * c - b * b
    if den < 1e-12:
        s, t = 0.0, (e / c if c > 1e-12 else 0.0)
    else:
        s = max(0.0, min(1.0, (b * e - c * d) / den))
        t = max(0.0, min(1.0, (a * e - b * d) / den))
    t = max(0.0, min(1.0, (b * s + e) / c)) if c > 1e-12 else 0.0
    s = max(0.0, min(1.0, (b * t - d) / a)) if a > 1e-12 else 0.0
    p = [a0[i] + u[i] * s for i in range(3)]
    q = [b0[i] + v[i] * t for i in range(3)]
    return math.dist(p, q)


def overlap(h1: Hole, h2: Hole) -> float:
    a0, a1 = h1.ends()
    b0, b1 = h2.ends()
    return (h1.r + h2.r) - _seg_dist(a0, a1, b0, b1)


def clashes(holes, allow=(), gap=0.0):
    out = []
    for h1, h2 in itertools.combinations(holes, 2):
        if frozenset((h1.name, h2.name)) in allow:
            continue
        ov = overlap(h1, h2) + gap
        if ov > 1e-6:
            out.append((h1.name, h2.name, ov - gap))
    return sorted(out, key=lambda r: -r[2])


def mount_holes(f):
    n = max(f.rods.motor_count, 1)
    H = f.mount_height
    zr = f.mount_rod_y
    out = []
    for i in range(n):
        a = math.radians(360.0 * i / n)
        d = (math.cos(a), math.sin(a), 0.0)
        out.append(Hole(f"bore{i}", (0, 0, zr), d, f.mount_bore_dia,
                        f.mount_bore_inner_r, f.mount_reach, "bore"))
        if f.mount.clamp_bolt > 0:
            r = f.mount_clamp_r
            out.append(Hole(f"clamp{i}", (r * d[0], r * d[1], 0.0), (0, 0, 1),
                            f.mount.clamp_bolt + f.mount.clamp_bolt_clearance,
                            0.0, H, "screw"))
    if f.motor.boss_dia > 0:
        out.append(Hole("shaft", (0, 0, 0), (0, 0, 1), f.motor.boss_dia,
                        0.0, H, "relief"))
    for j, (x, y) in enumerate(f.motor_hole_xy()):
        out.append(Hole(f"motorbolt{j}", (x, y, 0), (0, 0, 1),
                        f.motor.hole_dia, 0.0, H, "screw"))
    return out


def mount_allow(f):
    n = max(f.rods.motor_count, 1)
    a = {frozenset((f"clamp{i}", f"bore{i}")) for i in range(n)}
    a |= {frozenset(("shaft", f"bore{i}")) for i in range(n)}
    return a


def mount_escapes(f):
    out = []
    hub = f.mount_hub_od / 2.0
    for j, (x, y) in enumerate(f.motor_hole_xy()):
        r = math.hypot(x, y) + f.motor.hole_dia / 2.0
        if r > hub:
            out.append((f"motorbolt{j}", r - hub))
    if f.mount.clamp_bolt > 0:
        rc = f.mount_clamp_r
        d = f.mount.clamp_bolt + f.mount.clamp_bolt_clearance
        boss = f.mount_boss_od / 2.0
        if rc + d / 2.0 > f.mount_reach:
            out.append(("clamp past the arm tip", rc + d / 2.0 - f.mount_reach))
        if d / 2.0 > boss:
            out.append(("clamp wider than the boss", d / 2.0 - boss))
    return out


def report(f, gap=0.8):
    hs = mount_holes(f)
    rows = clashes(hs, allow=mount_allow(f), gap=gap)
    esc = mount_escapes(f)
    L = []
    for a, b, ov in rows:
        L.append(f"{a} and {b} overlap by {ov:.2f} mm"
                 if ov > 0 else
                 f"{a} and {b} are only {-ov:.2f} mm apart, want {gap:.1f}")
    for nm, d in esc:
        L.append(f"{nm} breaks out by {d:.2f} mm")
    return L

def plate_holes(f):
    from .layout3d import (center_rods, motor_rods, motor_arm_bolt_r,
                           center_cross_bolts)
    c = f.center
    lo, hi = f.center_plate_span()
    out = []
    for i, (x, _, _, _) in enumerate(center_rods(f)):
        out.append(Hole(f"spine{i}", (x, 0, 0), (0, 1, 0), f.center_bore_dia,
                        -f.plate_z, f.plate_z, "bore"))

    for k, (bx, by) in enumerate(center_cross_bolts(f)):
        out.append(Hole(f"spinebolt{k}", (bx, by, lo), (0, 0, 1),
                        c.cross_bolt + 0.4, 0.0, hi - lo, "screw"))
    for nm, (span, bolt) in zip(("fc", "stack"), f.deck_patterns()):
        for k, (sx, sy) in enumerate([(a, b) for a in (-span / 2, span / 2)
                                      for b in (-span / 2, span / 2)]):
            dp = f.deck_depth()
            z0, z1 = (hi - dp, hi) if dp > 1.0 else (lo, hi)
            out.append(Hole(f"{nm}{k}", (sx, sy, z0), (0, 0, 1),
                            bolt + c.fc_clearance, 0.0, z1 - z0, "screw"))
    zr = f.motor_rod_duct_y - f.duct_height * f.rods.center_y_frac
    hub = f.motor_rod_r0
    eng = f.rods.motor_engage or 2.5 * f.motor_rod
    j = 0
    for cx, cz, ang, L, sz, tg in motor_rods(f):
        if tg != "in":
            continue
        a = math.radians(ang)
        d = (math.cos(a), math.sin(a), 0.0)
        tip = hub + L
        out.append(Hole(f"arm{j}", (cx, cz, zr), d, sz + f.rods.clearance,
                        0.0, tip, "bore"))
        r = motor_arm_bolt_r(f, cx, cz, tip) if c.cross_bolt > 0 else None
        if r is not None:
            out.append(Hole(f"armbolt{j}", (cx + d[0] * r, cz + d[1] * r, lo),
                            (0, 0, 1), c.cross_bolt + 0.4, 0.0, hi - lo,
                            "screw"))
        j += 1
    return out


def plate_allow(f):
    from .layout3d import center_rods, center_cross_bolts
    xs = [x for x, _, _, _ in center_rods(f)]
    a = set()
    for k, (bx, _by) in enumerate(center_cross_bolts(f)):
        i = min(range(len(xs)), key=lambda j: abs(xs[j] - bx))
        a.add(frozenset((f"spine{i}", f"spinebolt{k}")))
    a |= {frozenset((f"arm{j}", f"armbolt{j}")) for j in range(4)}
    return a


def plate_report(f, gap=0.8):
    return [f"{x} and {y} overlap by {o:.2f} mm" if o > 0 else
            f"{x} and {y} are only {-o:.2f} mm apart, want {gap:.1f}"
            for x, y, o in clashes(plate_holes(f), allow=plate_allow(f),
                                   gap=gap)]
