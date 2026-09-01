from __future__ import annotations
import math

from .params import Frame


def solve_edge(S: float, Ro: float, d: float):
    k = d + Ro
    zc = ((S / 2.0) ** 2 - k * k) / (2.0 * k)
    rho = zc + d
    cx, cz = S / 2.0, 0.0
    dist = math.hypot(cx - 0.0, cz - zc)
    ux, uz = (cx - 0.0) / dist, (cz - zc) / dist
    return zc, rho, (rho * ux, zc + rho * uz)


def tangent_from_point(P, C, Ro: float, prefer_low: bool = True):
    dx, dz = P[0] - C[0], P[1] - C[1]
    d = math.hypot(dx, dz)
    if d <= Ro:
        return None
    beta = math.acos(Ro / d)
    ux, uz = dx / d, dz / d
    out = []
    for sgn in (1.0, -1.0):
        c, sn = math.cos(sgn * beta), math.sin(sgn * beta)
        out.append((C[0] + Ro * (ux * c - uz * sn),
                    C[1] + Ro * (ux * sn + uz * c)))
    out.sort(key=lambda t: t[1])
    return out[0] if prefer_low else out[-1]


def fillet_radius_for_pad(S: float, Ro: float, d: float, pad_half: float):
    A = S / 2.0 - pad_half
    return (A * A - Ro * Ro + d * d) / (2.0 * (Ro + d))


def solve_fillet(S: float, Ro: float, d: float, rf: float):
    disc = (Ro + rf) ** 2 - (rf - d) ** 2
    if disc <= 0 or rf <= 0:
        return None
    cx = S / 2.0 - math.sqrt(disc)
    cz = -d + rf
    rcx = S / 2.0
    dist = math.hypot(cx - rcx, cz)
    if dist <= 1e-9:
        return None
    ux, uz = (cx - rcx) / dist, cz / dist
    return (cx, cz), rf, (cx, -d), (rcx + Ro * ux, Ro * uz)


def _is_simple(poly) -> bool:
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if ((cross(c, d, a) > 0) != (cross(c, d, b) > 0)) and                     ((cross(a, b, c) > 0) != (cross(a, b, d) > 0)):
                return False
    return True


class Bridge:
    def __init__(self, f: Frame):
        self.f = f
        self.S = f.motor_spacing
        self.Ro = f.duct_od / 2.0 - f.connector.blend_overlap
        self.d_out = f.connector_outer_offset
        self.pad_w = f.connector_pad_width
        self.zc_out, self.r_out, self.t_out = solve_edge(self.S, self.Ro, self.d_out)
        self.pad_half = max(self.pad_w, f.rod_pad_min_width) / 2.0

        d0 = f.connector_inner_offset
        dmin = f.connector.min_inner_offset_ratio * f.duct_od
        self._solve_inner(d0)
        self.shrunk_to_fit = False
        if f.connector.fit_to_bed:
            d = d0
            for _ in range(40):
                if self._fits_plate():
                    break
                d *= 0.96
                if d < dmin:
                    d = dmin
                    self._solve_inner(d)
                    break
                self._solve_inner(d)
                self.shrunk_to_fit = True
        self.d_in_full = d0

    def _solve_inner(self, d_in):
        self.d_in = d_in
        self.pad_corner = (self.pad_half, -d_in)
        t = tangent_from_point(self.pad_corner, (self.S / 2.0, 0.0), self.Ro)
        self.tangent_ok = t is not None
        self.t_in = t if t is not None else (self.pad_half, -d_in)

    def _fits_plate(self) -> bool:
        f = self.f
        bx = f.printer.bed_x - 2 * f.printer.margin
        by = f.printer.bed_y - 2 * f.printer.margin
        pts = self.part_points(f.joint.lap_deg)
        xs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        w, h = max(xs) - min(xs), max(zs) - min(zs)
        return (w <= bx and h <= by) or (w <= by and h <= bx)

    def _ring_angle(self, pt):
        return math.degrees(math.atan2(pt[1] - 0.0, pt[0] - self.S / 2.0)) % 360.0

    @property
    def interface_deg(self) -> float:
        a0 = self._ring_angle(self.t_out)
        a1 = self._ring_angle(self.t_in)
        return abs((a1 - a0 + 180) % 360 - 180)

    @property
    def interface_center_deg(self) -> float:
        a0 = self._ring_angle(self.t_out)
        a1 = self._ring_angle(self.t_in)
        d = (a1 - a0 + 180) % 360 - 180
        return (a0 + d / 2.0) % 360.0

    @staticmethod
    def _arc(cx, cz, radius, a0_deg, a1_deg, n):
        return [(cx + radius * math.cos(math.radians(a0_deg + (a1_deg - a0_deg) * i / n)),
                 cz + radius * math.sin(math.radians(a0_deg + (a1_deg - a0_deg) * i / n)))
                for i in range(n + 1)]

    def outline(self, n: int = 48):
        def ang(pt, cz):
            return math.degrees(math.atan2(pt[1] - cz, pt[0]))

        aR = ang(self.t_out, self.zc_out)
        aL = 180.0 - aR
        top = self._arc(0.0, self.zc_out, self.r_out, aL,
                        aR + 360.0 if aR < aL else aR, n)

        bot = [self.t_in,
               self.pad_corner,
               (-self.pad_corner[0], self.pad_corner[1]),
               (-self.t_in[0], self.t_in[1])]

        base = self._weld(self._clear_the_bore(top + bot))
        pts = self._weld(self._clear_the_bore(
            self._round_corners(base, self.f.connector_corner_fillet)))
        self.corners_rounded = _is_simple(pts)
        if not self.corners_rounded:
            pts = base
        out = [pts[0]]
        for q in pts[1:]:
            if math.dist(q, out[-1]) > 1e-9:
                out.append(q)
        while len(out) > 2 and math.dist(out[-1], out[0]) <= 1e-9:
            out.pop()
        return out

    @staticmethod
    def _round_corners(pts, radius: float, min_turn_deg: float = 12.0,
                       n: int = 12):
        if radius <= 0 or len(pts) < 3:
            return pts
        m = len(pts)

        def walk(i, direction):
            acc, j = 0.0, i
            for _ in range(m // 2):
                k = (j + direction) % m
                acc += math.dist(pts[j], pts[k])
                j = k
                if acc >= radius:
                    break
            return pts[j], acc

        tn = []
        for i in range(m):
            a_, _ = walk(i, -1)
            c_, _ = walk(i, +1)
            ux, uz = a_[0] - pts[i][0], a_[1] - pts[i][1]
            vx, vz = c_[0] - pts[i][0], c_[1] - pts[i][1]
            la, lc = math.hypot(ux, uz), math.hypot(vx, vz)
            if la < 1e-9 or lc < 1e-9:
                tn.append(0.0)
                continue
            ca = max(-1.0, min(1.0, (ux * vx + uz * vz) / (la * lc)))
            tn.append(180.0 - math.degrees(math.acos(ca)))

        out = []
        for i in range(m):
            if tn[i] < min_turn_deg or tn[i] >= tn[(i - 1) % m]                     or tn[i] > 175.0:
                if tn[i] < min_turn_deg:
                    out.append(pts[i])
                continue
            out.append(pts[i])
        res = []
        for i in range(m):
            lmax = (tn[i] >= min_turn_deg
                    and tn[i] >= tn[(i - 1) % m]
                    and tn[i] > tn[(i + 1) % m]
                    and tn[i] <= 175.0)
            if not lmax:
                res.append(pts[i])
                continue
            a_, la = walk(i, -1)
            c_, lc = walk(i, +1)
            b_ = pts[i]
            ux, uz = (a_[0] - b_[0]) / la, (a_[1] - b_[1]) / la
            vx, vz = (c_[0] - b_[0]) / lc, (c_[1] - b_[1]) / lc
            ca = max(-1.0, min(1.0, ux * vx + uz * vz))
            half = math.acos(ca) / 2.0
            if half < 1e-6 or half > math.pi / 2 - 1e-6:
                res.append(b_)
                continue
            r = min(radius, 0.45 * min(la, lc) * math.tan(half))
            t = r / math.tan(half)
            if t <= 1e-9 or t > min(la, lc):
                res.append(b_)
                continue
            p0 = (b_[0] + ux * t, b_[1] + uz * t)
            p1 = (b_[0] + vx * t, b_[1] + vz * t)
            bx, bz = ux + vx, uz + vz
            lb = math.hypot(bx, bz)
            if lb < 1e-9:
                res.append(b_)
                continue
            d = r / math.sin(half)
            ctr = (b_[0] + bx / lb * d, b_[1] + bz / lb * d)
            a0 = math.atan2(p0[1] - ctr[1], p0[0] - ctr[0])
            a1 = math.atan2(p1[1] - ctr[1], p1[0] - ctr[0])
            if a1 - a0 > math.pi:
                a1 -= 2 * math.pi
            if a0 - a1 > math.pi:
                a1 += 2 * math.pi
            res += [(ctr[0] + r * math.cos(a0 + (a1 - a0) * q / n),
                     ctr[1] + r * math.sin(a0 + (a1 - a0) * q / n))
                    for q in range(n + 1)]
        return res

    @staticmethod
    def _clip_outside_circle(pts, cx, cz, R, n=28):
        m = len(pts)
        inside = [math.hypot(p[0] - cx, p[1] - cz) < R for p in pts]
        if not any(inside) or all(inside):
            return pts

        def cross_t(p, q):
            dx, dz = q[0] - p[0], q[1] - p[1]
            fx, fz = p[0] - cx, p[1] - cz
            A = dx * dx + dz * dz
            B = 2 * (fx * dx + fz * dz)
            C = fx * fx + fz * fz - R * R
            disc = B * B - 4 * A * C
            if A < 1e-12 or disc < 0:
                return 0.0
            disc = math.sqrt(disc)
            for t in sorted(((-B - disc) / (2 * A), (-B + disc) / (2 * A))):
                if -1e-9 <= t <= 1 + 1e-9:
                    return min(max(t, 0.0), 1.0)
            return 0.0

        k = inside.index(False)
        pts = pts[k:] + pts[:k]
        inside = inside[k:] + inside[:k]

        out = []
        i = 0
        while i < m:
            if not inside[i]:
                out.append(pts[i])
                i += 1
                continue
            p_prev, p_cur = pts[i - 1], pts[i]
            t = cross_t(p_prev, p_cur)
            enter = (p_prev[0] + (p_cur[0] - p_prev[0]) * t,
                     p_prev[1] + (p_cur[1] - p_prev[1]) * t)
            j = i
            while j < m and inside[j]:
                j += 1
            nxt = pts[j % m]
            t = cross_t(pts[j - 1], nxt)
            leave = (pts[j - 1][0] + (nxt[0] - pts[j - 1][0]) * t,
                     pts[j - 1][1] + (nxt[1] - pts[j - 1][1]) * t)
            a0 = math.atan2(enter[1] - cz, enter[0] - cx)
            a1 = math.atan2(leave[1] - cz, leave[0] - cx)
            if a1 - a0 > math.pi:
                a1 -= 2 * math.pi
            if a0 - a1 > math.pi:
                a1 += 2 * math.pi
            out += [(cx + R * math.cos(a0 + (a1 - a0) * q / n),
                     cz + R * math.sin(a0 + (a1 - a0) * q / n))
                    for q in range(n + 1)]
            i = j
        return out

    @staticmethod
    def _weld(pts, tol: float = 0.05):
        out = [pts[0]]
        for q in pts[1:]:
            if math.dist(q, out[-1]) > tol:
                out.append(q)
        while len(out) > 3 and math.dist(out[-1], out[0]) <= tol:
            out.pop()
        return out

    def _clear_the_bore(self, pts):
        R = self.f.max_bore_radius + self.f.connector.inlet_clearance
        for cx, cz in ((self.S / 2.0, 0.0), (-self.S / 2.0, 0.0)):
            pts = self._clip_outside_circle(pts, cx, cz, R)
        return pts

    def contains(self, x: float, z: float, margin: float = 0.0) -> bool:
        poly = self.outline(64)
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, zi = poly[i]
            xj, zj = poly[j]
            if (zi > z) != (zj > z):
                xc = xi + (z - zi) * (xj - xi) / (zj - zi)
                if x < xc:
                    inside = not inside
            j = i
        if not inside or margin <= 0.0:
            return inside
        for i in range(n):
            ax, az = poly[i]
            bx, bz = poly[(i + 1) % n]
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
            if math.hypot(x - (ax + t * dx), z - (az + t * dz)) < margin:
                return False
        return True

    def z_range_at(self, x: float, margin: float = 0.0):
        poly = self.outline(96)
        hits = []
        n = len(poly)
        for i in range(n):
            ax, az = poly[i]
            bx, bz = poly[(i + 1) % n]
            if (ax > x) == (bx > x):
                continue
            t = (x - ax) / (bx - ax)
            hits.append(az + t * (bz - az))
        if len(hits) < 2:
            return None
        return min(hits) + margin, max(hits) - margin

    def rod_cross_bolts(self, dia: float):
        from .layout3d import center_rods
        out = []
        for x, _z0, z1, _sz in center_rods(self.f):
            span = self.z_range_at(x, margin=dia / 2.0 + 3.0)
            if span is None:
                continue
            lo, hi = span
            hi = min(hi, (z1 - self.S / 2.0) - dia / 2.0 - 2.0)
            ns = 60
            ok = [lo + (hi - lo) * i / ns for i in range(ns + 1)
                  if hi > lo] or []
            ok = [z for z in ok if self._bolt_is_clear(x, z, dia)]
            if not ok:
                continue
            zlo, zhi = ok[0], ok[-1]
            if zhi - zlo < 3.0 * dia:
                out.append((x, (zlo + zhi) / 2.0))
                continue
            out.append((x, zlo + (zhi - zlo) * 0.15))
            out.append((x, zlo + (zhi - zlo) * 0.85))
        return out

    def _bolt_is_clear(self, x: float, z: float, dia: float) -> bool:
        if not self.contains(x, z, dia / 2.0 + 2.0):
            return False
        keep = self.f.duct_od / 2.0 + dia / 2.0 + 1.0
        for cx in (self.S / 2.0, -self.S / 2.0):
            if math.hypot(x - cx, z) < keep:
                return False
        return True

    def accessory_holes(self, span: float, dia: float):
        if span <= 0:
            return []
        pad_z = -self.d_in + span * 0.6 + 6.0
        pts = [(sx, pad_z + sz)
               for sx in (-span / 2.0, span / 2.0)
               for sz in (-span / 2.0, span / 2.0)]
        need = dia / 2.0 + 2.5
        return pts if all(self.contains(x, z, need) for x, z in pts) else []

    @property
    def pad_face_z(self) -> float:
        return -self.d_in

    def rod_slots(self):
        r = self.f.rods
        w = self.f.center_rod + r.clearance
        pz = -self.d_in
        from .layout3d import center_rod_spacing
        sp = center_rod_spacing(self.f)
        xs = [(-(r.center_count - 1) / 2.0 + i) * sp
              for i in range(r.center_count)]
        return [(x, pz, w) for x in xs]

    def part_points(self, lap_deg: float = 0.0, n: int = 24):
        pts = list(self.outline(48))
        Rf = self.f.duct_od / 2.0
        for sgn in (1, -1):
            cx = sgn * self.S / 2.0
            lo = self.interface_center_deg - self.interface_deg / 2.0 - lap_deg / 2.0
            hi = self.interface_center_deg + self.interface_deg / 2.0 + lap_deg / 2.0
            if sgn < 0:
                lo, hi = 180.0 - hi, 180.0 - lo
            for r in (self.f.throat_radius, Rf):
                for k in range(n + 1):
                    a = math.radians(lo + (hi - lo) * k / n)
                    pts.append((cx + r * math.cos(a), r * math.sin(a)))
        return pts

    def summary(self) -> dict:
        return dict(
            interface_deg=round(self.interface_deg, 2),
            interface_center_deg=round(self.interface_center_deg, 2),
            outer_arc_r=round(self.r_out, 2),
            inner_d=round(self.d_in, 2),
            tangent_out=tuple(round(v, 2) for v in self.t_out),
            tangent_in=tuple(round(v, 2) for v in self.t_in),
            span_x=round(2 * max(self.t_out[0], self.t_in[0]), 2),
        )
