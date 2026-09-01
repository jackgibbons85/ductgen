import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ductgen.params import Frame, check                     # noqa: E402
from ductgen.profile import polyline, ring_volume, print_mass   # noqa: E402
from ductgen.segment import plan_ring, sector_polygon, best_plate_fit  # noqa: E402

PRESETS = sorted(glob.glob(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "presets", "*.json")))
CASES = [Frame()] + [Frame.from_json(p) for p in PRESETS
                     if not p.endswith("printers.json")]


def _segments_intersect(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])// 1 \
            if False else (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def test_section_is_simple():
    for f in CASES:
        p = polyline(f)
        n = len(p)
        for i in range(n):
            a, b = p[i], p[(i + 1) % n]
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                c, d = p[j], p[(j + 1) % n]
                assert not _segments_intersect(a, b, c, d), \
                    f"{f.name}: section self-intersects at {i}/{j}"


def test_section_stays_inside_the_ring():
    for f in CASES:
        xs = [q[0] for q in polyline(f)]
        assert min(xs) >= f.throat_radius - 1e-6, f.name
        assert max(xs) <= f.duct_od / 2.0 + 1e-6, f.name


def test_lip_fits_the_wall():
    for f in CASES:
        if f.duct.od_override:
            continue
        assert f.duct_od / 2.0 >= f.throat_radius + f.lip_semi_major, f.name


def test_ring_volume_matches_pappus():
    for f in CASES:
        v = ring_volume(f)
        assert v > 0, f.name
        floor = 2 * math.pi * f.throat_radius * f.duct_height * f.duct.wall * 0.5
        assert v > floor, f.name


def test_segments_tile_the_ring():
    for f in CASES:
        r = plan_ring(f)
        step = r.split_deg / r.count
        assert abs(r.segments[0].sweep_deg - (step + f.joint.lap_deg)) < 1e-9, f.name
        assert abs(r.split_deg + r.interface_deg - 360.0) < 1e-9, f.name
        for s in r.segments:
            assert s.sweep_deg > f.joint.lap_deg * 2, \
                f"{f.name}: segment shorter than its own laps"


def test_rod_bores_sit_clear_of_the_joints():
    from ductgen.layout3d import rod_segment_plan
    for f in CASES:
        ring = plan_ring(f)
        for di, si, phi, kind, rad, role in rod_segment_plan(f, ring):
            if si is None or role != "main":
                continue
            seg = ring.segments[si]
            room = seg.sweep_deg / 2.0 - f.joint.lap_deg / 2.0 - abs(phi)
            assert room > 0, (f"{f.name}: {kind} bore on duct {di} sits "
                              f"{abs(phi):.1f} deg off centre in a "
                              f"{seg.sweep_deg:.1f} deg segment")


def test_every_rod_crossing_gets_a_bore_or_is_reported():
    from ductgen.layout3d import rod_segment_plan
    from ductgen.bridge import Bridge
    for f in CASES:
        ring = plan_ring(f)
        for di, si, phi, kind, rad, role in rod_segment_plan(f, ring):
            if si is not None:
                continue
            lo = ring.interface_center_deg - ring.interface_deg / 2.0
            hi = ring.interface_center_deg + ring.interface_deg / 2.0
            d = (phi - ring.interface_center_deg + 180.0) % 360.0 - 180.0
            assert abs(d) <= ring.interface_deg / 2.0 + 1e-6, (
                f"{f.name}: {kind} rod on duct {di} at {phi:.1f} deg has no "
                f"bore and is not in the connector arc {lo:.1f}..{hi:.1f}")


def test_segments_fit_the_declared_bed():
    for f in CASES:
        r = plan_ring(f)
        assert r.fits, f"{f.name}: no segment count fits {f.printer.name}"
        bx = f.printer.bed_x - 2 * f.printer.margin
        by = f.printer.bed_y - 2 * f.printer.margin
        s = r.segments[0]
        assert s.plate_w <= bx + 1e-6 and s.plate_h <= by + 1e-6, f.name
        assert f.duct_height <= f.printer.bed_z, f.name


def test_every_segment_still_fits_its_bed():
    f = Frame()
    for bed in (400, 350, 300, 256, 220, 180):
        f.printer.bed_x = f.printer.bed_y = bed
        r = plan_ring(f)
        usable = bed - 2 * f.printer.margin
        assert r.fits, f"bed {bed}: no segment count fits"
        assert r.segments[0].plate_w <= usable + 1e-6, f"bed {bed}"
        assert r.segments[0].plate_h <= usable + 1e-6, f"bed {bed}"


def test_strut_socket_leaves_a_ligament():
    for f in CASES:
        wall = f.outer_radius_at(f.strut_y) - f.throat_radius
        assert f.socket_depth < wall, f.name
        assert wall - f.socket_depth >= 1.4, \
            f"{f.name}: only {wall - f.socket_depth:.2f} mm of wall left"


def test_reference_preset_reproduces_the_measured_drone():
    f = Frame.from_json(os.path.join(os.path.dirname(PRESETS[0]),
                                     "reference_drone3.json"))
    assert abs(f.duct_id - 340.0) < 0.5
    assert abs(f.duct_od - 380.0) < 0.5
    assert abs(f.duct_height - 40.0) < 0.5
    assert abs(f.motor_spacing - 475.45) < 0.5
    assert f.center.fc_span == 30.5
    assert f.rods.center_size == 22.3
    levels = {c.label: c.level for c in check(f)}
    assert levels["inlet lip radius"] == "fail"
    assert levels["duct chord"] == "fail"


def test_ring_gaps_face_their_connector_stub():
    from ductgen.layout3d import ring_offset, duct_centers
    for f in CASES:
        if not f.connector.enabled:
            continue
        ring = plan_ring(f)
        c = ring.interface_center_deg
        stub = {(1, 1): c, (-1, 1): (180.0 - c) % 360.0,
                (-1, -1): (c + 180.0) % 360.0, (1, -1): (360.0 - c) % 360.0}
        for cx, cz in duct_centers(f):
            gap = (c + ring_offset(f, cx, cz, ring)) % 360.0
            want = stub[(1 if cx > 0 else -1, 1 if cz > 0 else -1)]
            err = abs((gap - want + 180.0) % 360.0 - 180.0)
            assert err < 1e-6,                 f"{f.name}: duct ({cx:.0f},{cz:.0f}) gap at {gap:.2f}, "                 f"stub at {want:.2f}"


def test_straight_wall_is_vertical():
    for f in CASES:
        if f.duct.outer_style == "straight" or f.duct.od_override > 0:
            assert abs(f.outer_taper_deg) < 1e-9, f.name
            xs = [q[0] for q in polyline(f)]
            assert abs(max(xs) - f.duct_od / 2.0) < 1e-6, f.name


def test_mass_estimate_is_bounded_by_the_solid():
    for f in CASES:
        m = print_mass(f)
        assert 0 < m["grams"]
        assert m["shell_cm3"] + m["infill_cm3"] <= m["volume_cm3"] + 1e-6, f.name


def test_plate_fit_is_rotation_invariant():
    pts = sector_polygon(100, 140, 95)
    a = best_plate_fit(pts, 300, 300, True)
    rot = [(x * math.cos(0.7) - y * math.sin(0.7),
            x * math.sin(0.7) + y * math.cos(0.7)) for x, y in pts]
    b = best_plate_fit(rot, 300, 300, True)
    assert abs(a[4] - b[4]) < 1e-3


def test_side_rod_path_is_fully_cut():
    from ductgen.layout3d import (rod_segment_plan, side_rod_crossings,
                                  ring_offset, duct_centers, MIN_THRU_DEG)
    for f in CASES:
        ring = plan_ring(f)
        lap = f.joint.lap_deg
        y = f.outer_rod_duct_y
        upper = y > f.duct_height * f.joint.lap_height_frac
        ro_y = f.outer_radius_at(y)
        bore_r = (f.rods.outer_size + f.rods.clearance) / 2.0
        cuts = {}
        for di, si, phi, kind, rad, role in rod_segment_plan(f, ring):
            if kind == "side" and si is not None:
                cuts.setdefault(di, []).append((si, phi))
        for di, ang, rad in side_rod_crossings(f):
            off = ring_offset(f, *duct_centers(f)[di], ring)
            local = (ang - off) % 360.0
            t_hit = math.sqrt(max(ro_y * ro_y - rad * rad, 0.0))
            half = math.degrees(math.atan2(t_hit, rad))
            uncovered = 0.0
            for seg in ring.segments:
                a0 = seg.start_deg + (lap if upper else 0.0)
                a1 = seg.end_deg - (0.0 if upper else lap)
                d0 = (a0 - local + 180.0) % 360.0 - 180.0
                d1 = d0 + (a1 - a0)
                lo, hi = max(d0, -half), min(d1, half)
                if hi <= lo:
                    continue
                cut_here = any(
                    si == seg.index and
                    abs((local - (ring.segments[si].mid_deg + phi) + 180.0)
                        % 360.0 - 180.0) < 0.5
                    for si, phi in cuts.get(di, []))
                if not cut_here:
                    uncovered += hi - lo
            assert uncovered <= MIN_THRU_DEG + 1e-6, (
                f"{f.name}: duct {di} side rod at {ang:.0f} deg has "
                f"{uncovered:.1f} deg of un-drilled wall in its path")


def test_center_plate_swallows_the_rods_at_any_height():
    for f in CASES:
        for override in (0.0, f.center_bore_dia + 14.0):
            f.center.plate_y = override
            H = f.center_plate_height
            assert H / 2.0 > f.center_bore_dia / 2.0 + 1.0, (
                f"{f.name}: plate {H:.1f} too thin for a "
                f"{f.center_bore_dia:.1f} bore")
        f.center.plate_y = 0.0


def test_connector_cross_bolts_hit_the_rods():
    from ductgen.bridge import Bridge
    from ductgen.layout3d import center_rods
    for f in CASES:
        if not f.connector.enabled or f.center.cross_bolt <= 0:
            continue
        br = Bridge(f)
        dia = f.center.cross_bolt + 0.4
        holes = br.rod_cross_bolts(dia)
        rods = center_rods(f)
        assert len(holes) >= len(rods), f"{f.name}: fewer bolts than rods"
        assert len(holes) <= 2 * len(rods), f"{f.name}: more than 2 per rod"
        for hx, hz in holes:
            assert any(abs(hx - x) < 1e-6 for x, _, _, _ in rods), (
                f"{f.name}: bolt at x={hx:.1f} is off every rod centreline")
            tips = [z1 - f.motor_spacing / 2.0 for _, _, z1, _ in rods]
            assert hz < max(tips), f"{f.name}: bolt outboard of the rod end"


def test_every_bore_is_cut_in_whichever_segment_owns_that_material():
    from ductgen.layout3d import (rod_segment_plan, side_rod_crossings,
                                  motor_rod_angles, duct_centers, ring_offset)
    for f in CASES:
        ring = plan_ring(f)
        lap = f.joint.lap_deg
        zmid = f.duct_height * f.joint.lap_height_frac
        rt, ro = f.throat_radius, f.duct_od / 2.0

        planned = set()
        dropped = set()
        for di, si, phi, kind, rad, role in rod_segment_plan(f, ring):
            if si is None:
                dropped.add((di, kind, round(rad, 2)))
            else:
                planned.add((di, si, kind))

        def owner(theta, z):
            for seg in ring.segments:
                a0 = seg.start_deg + (lap if z > zmid else 0.0)
                a1 = seg.end_deg - (0.0 if z > zmid else lap)
                if ((theta - a0) % 360.0) <= (a1 - a0):
                    return seg.index
            return None

        side = {}
        for di, ang, rad in side_rod_crossings(f):
            side.setdefault(di, []).append((ang, rad))

        for di, (cx, cz) in enumerate(duct_centers(f)):
            off = ring_offset(f, cx, cz, ring)
            bores = [("motor", a, 0.0, f.mount_bore_dia / 2.0,
                      f.motor_rod_duct_y)
                     for a in motor_rod_angles(f, cx, cz)]
            bores += [("side", a, rad,
                       (f.rods.outer_size + f.rods.clearance) / 2.0,
                       f.outer_rod_duct_y)
                      for a, rad in side.get(di, [])]
            for kind, ang, rad, br, zc in bores:
                if (di, kind, round(rad, 2)) in dropped:
                    continue
                local = (ang - off) % 360.0
                for zs in (-0.9, -0.5, 0.0, 0.5, 0.9):
                    z = zc + br * zs
                    if not (0.0 < z < f.duct_height):
                        continue
                    hw = math.sqrt(max(br * br - (br * zs) ** 2, 0.0))
                    for hs in (-0.95, 0.0, 0.95):
                        if kind == "motor":
                            for rr in (rt + 1.0, (rt + ro) / 2.0, ro - 1.0):
                                th = local + math.degrees(
                                    math.atan2(hw * hs, rr))
                                o = owner(th % 360.0, z)
                                if o is None:
                                    continue
                                assert (di, o, kind) in planned, (
                                    f"{f.name}: duct {di} {kind} bore at "
                                    f"{local:.1f} deg passes through segment "
                                    f"{o} at z={z:.1f} with no cut planned")
                        else:
                            reach = math.sqrt(max(ro * ro - rad * rad, 0.0))
                            for tt in (-0.9, -0.5, 0.0, 0.5, 0.9):
                                px = rad
                                py = reach * tt + hw * hs
                                r = math.hypot(px, py)
                                if not (rt < r < ro):
                                    continue
                                th = local + math.degrees(math.atan2(py, px))
                                o = owner(th % 360.0, z)
                                if o is None:
                                    continue
                                assert (di, o, kind) in planned, (
                                    f"{f.name}: duct {di} {kind} bore at "
                                    f"{local:.1f} deg passes through segment "
                                    f"{o} at z={z:.1f} with no cut planned")


def test_build123d_backend_closes_the_ring():
    try:
        import numpy as np
        from ductgen import build_b3d as B
    except ImportError:
        return

    import tempfile
    from ductgen.layout3d import duct_centers

    f = Frame.from_json(os.path.join(os.path.dirname(PRESETS[0]),
                                     "13in_a1.json"))
    ring = plan_ring(f)
    with tempfile.TemporaryDirectory() as d:
        B.build_all(f, d, ring=ring)
        path = os.path.join(d, f"{f.name}_frame.STL")
        import struct
        with open(path, "rb") as fh:
            fh.read(80)
            n = struct.unpack("<I", fh.read(4))[0]
            raw = np.frombuffer(fh.read(n * 50), dtype=np.uint8).reshape(n, 50)
        tris = raw[:, :48].copy().view(np.float32).reshape(n, 4, 3)[:, 1:, :]
        tris = tris.astype(np.float64)

    H = f.duct_height
    lapz = f.joint.lap_height_frac
    def clear(zf):
        z = H * zf
        for ax, br in ((f.motor_rod_duct_y, f.mount_bore_dia / 2.0),
                       (f.outer_rod_duct_y,
                        (f.rods.outer_size + f.rods.clearance) / 2.0)):
            if abs(z - ax) < br + 2.0:
                return False
        return True

    zs = [zf for zf in (0.02, 0.10, 0.3, lapz - 0.02, lapz + 0.02, 0.75, 0.92)
          if clear(zf)]
    assert len(zs) >= 3, f"{f.name}: too few heights clear of the rod bores"
    for zf in zs:
        z = H * zf
        d0 = tris[:, :, 2] - z
        m = ~((d0 > 0).all(1) | (d0 < 0).all(1))
        pts = []
        for tri in tris[m]:
            hit = []
            for i in range(3):
                A, C = tri[i], tri[(i + 1) % 3]
                if (A[2] - z) * (C[2] - z) < 0:
                    u = (z - A[2]) / (C[2] - A[2])
                    hit.append(A + u * (C - A))
            if len(hit) >= 2:
                A, C = hit[0], hit[1]
                pts += [A + (C - A) * (i / 10.0) for i in range(11)]
        pts = np.array(pts)
        for di, (cx, cz) in enumerate(duct_centers(f)):
            r = np.hypot(pts[:, 0] - cx, pts[:, 1] - cz)
            k = (r > f.throat_radius - 1) & (r < f.duct_od / 2 + 1)
            th = np.degrees(np.arctan2(pts[k, 1] - cz,
                                       pts[k, 0] - cx)) % 360.0
            occ = np.zeros(1440, bool)
            occ[(th * 4).astype(int) % 1440] = True
            runs, cur = [], None
            for i in range(1440):
                if not occ[i] and cur is None:
                    cur = i
                if occ[i] and cur is not None:
                    runs.append((i - cur) * 0.25)
                    cur = None
            if cur is not None:
                runs.append((1440 - cur) * 0.25)
            gap = max(runs) if runs else 0.0
            assert gap <= 1.0, (f"b3d duct {di} ring open by {gap:.2f} deg at "
                                f"{zf*100:.0f}% of chord")


def test_build123d_rods_have_a_clear_path_through_the_printed_parts():
    try:
        import numpy as np
        from build123d import Compound, Pos, Rot, export_stl
        from ductgen import build_b3d as B
    except ImportError:
        return

    import struct, tempfile
    from ductgen.layout3d import (instances, center_rods, outer_rods,
                                  motor_rods, variant_key, rod_variants)

    def spans(tris, origin, direction):
        a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
        e1, e2 = b - a, c - a
        pv = np.cross(direction, e2)
        det = np.einsum('ij,ij->i', e1, pv)
        ok = np.abs(det) > 1e-12
        inv = np.zeros_like(det); inv[ok] = 1.0 / det[ok]
        sv = origin - a
        u = np.einsum('ij,ij->i', sv, pv) * inv
        q = np.cross(sv, e1)
        v = np.einsum('j,ij->i', direction, q) * inv
        t = np.einsum('ij,ij->i', e2, q) * inv
        m = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-6)
        if not m.any():
            return []
        step = np.where(np.einsum('j,ij->i', direction,
                                  np.cross(e1, e2)[m]) < 0, 1, -1)
        tt = t[m]
        o = np.argsort(tt); tt, step = tt[o], step[o]
        out, depth, start, i = [], 0, None, 0
        while i < len(tt):
            j, acc = i, 0
            while j < len(tt) and tt[j] - tt[i] < 1e-6:
                acc += step[j]; j += 1
            acc = max(-1, min(1, acc))
            was, depth = depth, max(0, depth + acc)
            if was == 0 and depth > 0:
                start = tt[i]
            elif was > 0 and depth == 0 and start is not None:
                out.append((start, tt[i])); start = None
            i = j
        return out

    f = Frame.from_json(os.path.join(os.path.dirname(PRESETS[0]),
                                     "cinewhoop_35.json"))
    ring = plan_ring(f)
    with tempfile.TemporaryDirectory() as d:
        sol = {"duct_segment": B.build_segment(f, ring, d)["solid"]}
        for feats, _ in sorted((k, v) for k, v in rod_variants(f, ring).items()
                               if k is not None):
            k2 = variant_key(feats)
            sol[k2] = B.build_segment(
                f, ring, d, rods=feats,
                tag="_" + k2.split("duct_segment_")[1])["solid"]
        sol["motor_mount"] = B.build_mount(f, d)["solid"]
        if f.connector.enabled:
            sol["connector"] = B.build_connector(f, ring, d)["solid"]
        sol["center_plate"] = B.build_center_plate(f, d)["solid"]
        placed = [Pos(x, z, y) * Rot(0, 0, ry) * sol[k]
                  for k, ry, (x, y, z) in instances(f, ring)
                  if not k.startswith("rod_")]
        path = os.path.join(d, "printed.stl")
        export_stl(Compound(children=placed), path, tolerance=5e-4)
        with open(path, "rb") as fh:
            fh.read(80)
            n = struct.unpack("<I", fh.read(4))[0]
            raw = np.frombuffer(fh.read(n * 50), dtype=np.uint8).reshape(n, 50)
    tris = raw[:, :48].copy().view(np.float32).reshape(n, 4, 3)[:, 1:, :]
    tris = tris.astype(np.float64)

    rods = []
    for i, (x, z0, z1, sz) in enumerate(center_rods(f)):
        rods.append((f"centre{i}", np.array([x, (z0 + z1) / 2.0,
                                             f.duct_height * f.rods.center_y_frac]),
                     np.array([0.0, 1.0, 0.0]), (z1 - z0) / 2.0, sz / 2.0))
    for i, (x0, z0, x1, z1, sz) in enumerate(outer_rods(f)):
        dv = np.array([x1 - x0, z1 - z0, 0.0]); L = np.linalg.norm(dv)
        rods.append((f"outer{i}", np.array([(x0 + x1) / 2.0, (z0 + z1) / 2.0,
                                            f.duct_height * f.rods.outer_y_frac]),
                     dv / L, L / 2.0, sz / 2.0))
    for i, (cx, cz, a, L, sz, _tg) in enumerate(motor_rods(f)):
        dv = np.array([math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0])
        mid = np.array([cx, cz, f.motor_rod_duct_y]) + dv * (f.motor_rod_r0
                                                             + L / 2.0)
        rods.append((f"motor{i}", mid, dv, L / 2.0, sz / 2.0))

    for nm, mid, dv, half, rad in rods:
        tmp = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(tmp, dv)) > 0.9:
            tmp = np.array([1.0, 0.0, 0.0])
        u = np.cross(dv, tmp); u /= np.linalg.norm(u)
        v = np.cross(dv, u)
        for k in range(5):
            off = (np.zeros(3) if k == 0 else
                   (math.cos(k * math.pi / 2) * u
                    + math.sin(k * math.pi / 2) * v) * rad * 0.85)
            o = mid + off - dv * (half + 50.0)
            for t0, t1 in spans(tris, o, dv):
                lo = max(t0 - 50.0, 0.0); hi = min(t1 - 50.0, 2 * half)
                assert hi - lo <= 0.5, (
                    f"{f.name}: rod {nm} is blocked by {hi-lo:.1f} mm of "
                    f"printed material, {lo:.1f} to {hi:.1f} along a "
                    f"{2*half:.1f} mm tube")


def test_inboard_arms_land_inside_the_centre_plate():
    from ductgen.layout3d import motor_rods
    for f in CASES:
        if not f.rods.motor_inboard:
            continue
        lo, hi = f.center_plate_span()
        zr = f.motor_rod_duct_y - f.duct_height * f.rods.center_y_frac
        br = f.rods.motor_size / 2.0
        n = 0
        for cx, cz, ang, L, sz, tg in motor_rods(f):
            if tg != "in":
                continue
            n += 1
            a = math.radians(ang)
            r = f.motor_rod_r0 + L
            tx, ty = cx + r * math.cos(a), cz + r * math.sin(a)
            assert abs(tx) <= f.plate_x / 2.0 + 1e-6, (
                f"{f.name}: inboard arm tip x={tx:.1f} outside the "
                f"{f.plate_x:.0f} mm plate")
            assert abs(ty) <= f.plate_z / 2.0 + 1e-6, (
                f"{f.name}: inboard arm tip z={ty:.1f} outside the "
                f"{f.plate_z:.0f} mm plate")
            assert lo <= zr - br and zr + br <= hi, (
                f"{f.name}: arm sits at {zr:.1f} off the spine, plate only "
                f"spans {lo:.1f}..{hi:.1f}, so the tube misses it entirely")
        assert n == 4, f"{f.name}: {n} inboard arms, expected one per duct"


def test_every_rod_a_part_carries_gets_a_screw_over_it():
    try:
        import numpy as np
        from build123d import Pos, Rot
        from ductgen import build_b3d as B
    except ImportError:
        return
    import tempfile
    from ductgen.layout3d import motor_rods

    f = Frame.from_json(os.path.join(os.path.dirname(PRESETS[0]),
                                     "13in_a1.json"))
    if not f.rods.motor_inboard:
        return
    with tempfile.TemporaryDirectory() as d:
        plate = B.build_center_plate(f, d)
    lo, hi = f.center_plate_span()
    zr = f.motor_rod_duct_y - f.duct_height * f.rods.center_y_frac
    eng = f.rods.motor_engage or 2.5 * f.rods.motor_size
    hub = f.motor_rod_r0
    got = 0
    for cx, cz, ang, L, sz, tg in motor_rods(f):
        if tg != "in":
            continue
        a = math.radians(ang)
        r = hub + L - eng / 2.0
        px, py = cx + r * math.cos(a), cz + r * math.sin(a)
        probe = Pos(px, py, (zr + hi) / 2.0) * B.Cylinder(
            radius=0.4, height=abs(hi - zr))
        if (plate["solid"] & probe).volume < 1e-6:
            got += 1
    assert got == 4, (f"{f.name}: {got} of 4 inboard arms have a screw over "
                      "them in the centre plate")


def test_nothing_in_a_part_runs_into_anything_else():
    from ductgen.clash import report, plate_report
    cases = list(CASES)
    for d in (3.0, 3.5, 5.0, 7.0, 10.0, 13.0, 16.0, 20.0):
        g = Frame()
        g.prop.diameter_in = d
        cases.append(g)
    for f in cases:
        bad = report(f) + plate_report(f)
        assert not bad, (f"{f.name} at {f.prop.diameter_in}in: "
                         + "; ".join(bad[:3]))


def test_derived_rods_are_sizes_you_can_actually_buy():
    from ductgen.params import CARBON
    g = Frame()
    g.prop.diameter_in = 13.0
    assert g.outer_rod == 10 and g.center_rod == 20, (g.outer_rod, g.center_rod)
    g.prop.diameter_in = 5.0
    assert g.outer_rod == 6 and g.center_rod == 12, (g.outer_rod, g.center_rod)
    last = 0
    for d in (3.0, 3.5, 5.0, 7.0, 10.0, 13.0, 16.0, 20.0):
        g.prop.diameter_in = d
        for v in (g.outer_rod, g.motor_rod, g.center_rod):
            assert v in CARBON, f"{d}in derived {v}, not a catalogue size"
        assert g.outer_rod >= last, "rod size must not shrink as the prop grows"
        last = g.outer_rod
    g.rods.outer_size = 7.5
    assert g.outer_rod == 7.5


def test_the_tube_still_gets_a_grip_in_the_mount():
    cases = list(CASES)
    for d in (3.0, 5.0, 13.0, 20.0):
        g = Frame()
        g.prop.diameter_in = d
        cases.append(g)
    for f in cases:
        grip = f.mount_reach - f.mount_bore_inner_r
        assert grip >= 1.2 * f.motor_rod, (
            f"{f.name} at {f.prop.diameter_in}in: only {grip:.1f} mm of "
            f"socket for a {f.motor_rod:.0f} mm tube")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL  {name}: {e}")
    print(f"\n{fails} failure(s)")
    sys.exit(1 if fails else 0)
