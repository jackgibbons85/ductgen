import os
import sys

import math

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stlread import read_stl, info                          # noqa: E402
from section import slice_y                                 # noqa: E402
from ductgen.params import Frame                            # noqa: E402
from ductgen.bridge import Bridge                           # noqa: E402
from ductgen.layout3d import duct_centers                   # noqa: E402

TOL_GAP_DEG = 1.0
TOL_CONTACT_MM = 2.5


def densify(segs, k=24):
    a, b = segs[:, 0, :], segs[:, 1, :]
    return np.vstack([a + (b - a) * (i / k) for i in range(k + 1)])


def largest_gap(pts, cx, cz, r_lo, r_hi, bins=2880):
    r = np.hypot(pts[:, 0] - cx, pts[:, 2] - cz)
    m = (r > r_lo) & (r < r_hi)
    if m.sum() == 0:
        return 360.0, 0.0
    th = np.degrees(np.arctan2(pts[m, 2] - cz, pts[m, 0] - cx)) % 360.0
    occ = np.zeros(bins, bool)
    occ[np.floor(th * bins / 360.0).astype(int) % bins] = True
    runs, cur = [], None
    for i in range(bins):
        if not occ[i] and cur is None:
            cur = i
        if occ[i] and cur is not None:
            runs.append(((i - cur) * 360.0 / bins, cur * 360.0 / bins))
            cur = None
    if cur is not None:
        runs.append(((bins - cur) * 360.0 / bins, cur * 360.0 / bins))
    return max(runs, default=(0.0, 0.0))


def main(stl, preset=None):
    f = Frame.from_json(preset) if preset else Frame()
    br = Bridge(f) if f.connector.enabled else None
    tris, _ = read_stl(stl)
    d = info(stl)
    H = f.duct_height
    fails = []

    print(f"{os.path.basename(stl)}")
    print(f"  {d['tris']} triangles, "
          f"{d['size'][0]:.1f} x {d['size'][1]:.1f} x {d['size'][2]:.1f} mm")
    print(f"  expected footprint {f.footprint:.1f} mm, chord {H:.1f} mm")
    print()

    rod_y = f.motor_rod_duct_y
    keep_out = f.mount_bore_dia * 0.75
    fracs = tuple(v for v in (0.03, 0.15, 0.25, 0.5, 0.75, 0.9)
                  if abs(H * v - rod_y) > keep_out)
    slices = {}
    for yf in fracs:
        sg = slice_y(tris, H * yf)
        slices[yf] = densify(sg) if len(sg) else np.zeros((0, 3))

    print("1. ring closure")
    for yf in fracs:
        P = slices[yf]
        worst, at, which = 0.0, 0.0, None
        for i, (cx, cz) in enumerate(duct_centers(f)):
            g, a = largest_gap(P, cx, cz, f.throat_radius - 7.0,
                               f.throat_radius + 16.0)
            if g > worst:
                worst, at, which = g, a, i
        ok = worst <= TOL_GAP_DEG
        if not ok:
            fails.append(f"ring gap {worst:.2f} deg at y={H*yf:.1f}, "
                         f"duct {which}, angle {at:.1f}")
        print(f"   y={H*yf:6.1f} ({yf*100:2.0f}%)  largest gap {worst:5.2f} deg"
              f"   {'ok' if ok else 'OPEN at %.1f deg on duct %d' % (at, which)}")

    if br is not None:
        print("\n2. connector meets duct")
        s = f.motor_spacing / 2.0
        for yf in fracs:
            P = slices[yf]
            row = []
            for nm, tp in (("outer", br.t_out), ("inner", br.t_in)):
                tx, tz = tp[0], s + tp[1]
                dist = np.hypot(P[:, 0] - tx, P[:, 2] - tz).min() if len(P) else 999
                row.append((nm, dist))
                if dist > TOL_CONTACT_MM:
                    fails.append(f"{nm} tangency {dist:.2f} mm clear "
                                 f"at y={H*yf:.1f}")
            print(f"   y={H*yf:6.1f}  " +
                  "  ".join(f"{nm} {v:5.2f} mm" for nm, v in row))

    print("\n3. outer wall vertical")
    s = f.motor_spacing / 2.0
    rads = []
    for yf in [v for v in (0.03, 0.5, 0.9) if v in slices]:
        P = slices[yf]
        r = np.hypot(P[:, 0] - s, P[:, 2] - s)
        th = np.degrees(np.arctan2(P[:, 2] - s, P[:, 0] - s)) % 360.0
        m = (th > 300) | (th < 60)
        bins = []
        for a in range(-60, 60):
            sel = m & (((th - a) % 360.0) < 1.0)
            if sel.sum():
                bins.append(r[sel].max())
        rmax = float(np.median(bins)) if bins else 0.0
        rads.append(rmax)
        print(f"   y={H*yf:6.1f}  median wall radius {rmax:7.2f} "
              f"(OD/2 = {f.duct_od/2:.2f})")
    if max(rads) - min(rads) > 0.5:
        fails.append(f"outer wall not vertical: radius varies "
                     f"{min(rads):.2f}..{max(rads):.2f}")

    print("\n4b. side (perimeter) rod bores")
    from ductgen.layout3d import side_rod_crossings
    sg_s = slice_y(tris, f.outer_rod_duct_y)
    S = densify(sg_s) if len(sg_s) else np.zeros((0, 3))
    by_duct = {}
    for di, ang, rad in side_rod_crossings(f):
        by_duct.setdefault(di, []).append((ang, rad))
    for i, (cx, cz) in enumerate(duct_centers(f)):
        row = []
        for ang, rad in by_duct.get(i, []):
            ux, uz = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            dd = (S[:, 0] - cx) * ux + (S[:, 2] - cz) * uz
            oo = -(S[:, 0] - cx) * uz + (S[:, 2] - cz) * ux
            near = (np.abs(dd - rad) < 6.5) & (np.abs(oo) < 40.0)
            row.append((ang, bool(near.sum() >= 6)))
        if row and not all(ok for _, ok in row):
            fails.append("duct %d: no side-rod bore at %s"
                         % (i, [a for a, ok in row if not ok]))
        if row:
            print("   duct %d: " % i + ", ".join(
                "%.0f deg %s" % (a, "yes" if ok else "MISSING")
                for a, ok in row))

    print("\n4. motor rod bores present")
    from ductgen.layout3d import motor_rod_angles
    sg = slice_y(tris, rod_y)
    Q = densify(sg) if len(sg) else np.zeros((0, 3))
    r_lo = f.throat_radius + 0.25 * (f.duct_od / 2.0 - f.throat_radius)
    r_hi = f.throat_radius + 0.75 * (f.duct_od / 2.0 - f.throat_radius)
    for i, (cx, cz) in enumerate(duct_centers(f)):
        want = motor_rod_angles(f, cx, cz)
        r = np.hypot(Q[:, 0] - cx, Q[:, 2] - cz)
        m = (r > r_lo) & (r < r_hi)
        th = np.degrees(np.arctan2(Q[m, 2] - cz, Q[m, 0] - cx)) % 360.0
        found = []
        for a in want:
            near = np.abs((th - a + 180.0) % 360.0 - 180.0) < 3.0
            found.append(bool(near.sum() >= 4))
        ok = all(found)
        if not ok:
            fails.append(f"duct {i}: no rod bore at "
                         f"{[round(a,1) for a, h in zip(want, found) if not h]}")
        print(f"   duct {i}: bores at "
              f"{', '.join('%.0f deg %s' % (a, 'yes' if h else 'MISSING') for a, h in zip(want, found))}")

    mount_stl = stl.replace("_frame.STL", "_motor_mount.STL")
    if os.path.exists(mount_stl):
        print("\n5. motor mount arms")
        mt, _ = read_stl(mount_stl)
        sg = slice_y(mt, f.mount_rod_y + 0.78 * f.mount_boss_od / 2.0)
        MP = densify(sg) if len(sg) else np.zeros((0, 3))
        rr = np.hypot(MP[:, 0], MP[:, 2])
        sel = rr > f.mount_hub_od / 2.0 + 4.0
        tt = np.degrees(np.arctan2(MP[sel, 2], MP[sel, 0])) % 360.0
        occ = np.zeros(360, bool)
        occ[np.floor(tt).astype(int) % 360] = True
        n_arm = max(f.rods.motor_count, 1)
        for _ in range(2):
            occ |= np.roll(occ, 1) | np.roll(occ, -1)
        runs, cur = [], None
        for i in range(360):
            if occ[i] and cur is None:
                cur = i
            if not occ[i] and cur is not None:
                runs.append((cur, i - 1))
                cur = None
        if cur is not None:
            runs.append((cur, 359))
        if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == 359:
            runs[0] = (runs[-1][0] - 360, runs[0][1])
            runs.pop()
        mids = sorted(((a + b) / 2.0) % 360.0 for a, b in runs)
        n = n_arm
        print(f"   arms found at {[round(v) for v in mids]} "
              f"(want {n} at {360.0/n:.0f} deg spacing)")
        if len(mids) != n:
            fails.append(f"mount has {len(mids)} arms, expected {n}")
        else:
            gaps = [(mids[(i + 1) % n] - mids[i]) % 360.0 for i in range(n)]
            worst = max(abs(g - 360.0 / n) for g in gaps)
            print(f"   spacing {[round(g) for g in gaps]} deg, "
                  f"worst error {worst:.1f} deg")
            if worst > 6.0:
                fails.append(f"mount arms not equally spaced: {gaps}")

    print()
    if fails:
        print(f"FAILED ({len(fails)}):")
        for x in fails:
            print("  -", x)
        return 1
    print("PASSED: rings closed, connector in contact, wall vertical")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
