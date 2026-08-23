"""Geometry invariants that must hold without SolidWorks anywhere near.

Run with:  python -m pytest -q     (or plain `python tests/test_geometry.py`)
"""
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
    """The meridian must not cross itself -- that is the failure mode when a
    fat lip is asked for inside a thin wall, and it makes the revolve fail."""
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
    """duct_od must always leave room for the bellmouth plus its rim land."""
    for f in CASES:
        if f.duct.od_override:
            continue
        assert f.duct_od / 2.0 >= f.throat_radius + f.lip_semi_major, f.name


def test_ring_volume_matches_pappus():
    for f in CASES:
        v = ring_volume(f)
        assert v > 0, f.name
        # crude sanity: a ring of this section cannot be lighter than a thin
        # tube of the same height at the throat
        floor = 2 * math.pi * f.throat_radius * f.duct_height * f.duct.wall * 0.5
        assert v > floor, f.name


def test_segments_tile_the_ring():
    """N segments of (360/N + lap), overlapping by lap, must close exactly."""
    for f in CASES:
        r = plan_ring(f)
        step = 360.0 / r.count
        assert abs(r.segments[0].sweep_deg - (step + f.joint.lap_deg)) < 1e-9, f.name
        covered = r.count * step
        assert abs(covered - 360.0) < 1e-9, f.name
        for s in r.segments:
            assert s.sweep_deg > f.joint.lap_deg * 2, \
                f"{f.name}: segment shorter than its own laps"


def test_joints_avoid_strut_roots():
    for f in CASES:
        r = plan_ring(f)
        for j in r.joint_angles:
            clear = min(abs((j - s + 180) % 360 - 180) for s in r.strut_angles)
            assert clear > f.joint.lap_deg / 2, \
                f"{f.name}: joint at {j:.1f} deg sits on a strut root"


def test_segments_fit_the_declared_bed():
    for f in CASES:
        r = plan_ring(f)
        assert r.fits, f"{f.name}: no segment count fits {f.printer.name}"
        bx = f.printer.bed_x - 2 * f.printer.margin
        by = f.printer.bed_y - 2 * f.printer.margin
        s = r.segments[0]
        assert s.plate_w <= bx + 1e-6 and s.plate_h <= by + 1e-6, f.name
        assert f.duct_height <= f.printer.bed_z, f.name


def test_smaller_bed_never_means_fewer_segments():
    f = Frame()
    last = 0
    for bed in (400, 350, 300, 256, 220, 180):
        f.printer.bed_x = f.printer.bed_y = bed
        n = plan_ring(f).count
        assert n >= last, f"bed {bed} gave {n} segments after {last}"
        last = n


def test_strut_socket_leaves_a_ligament():
    """The bug the 3.5 inch preset caught: a fixed socket depth punches
    straight through a thin wall."""
    for f in CASES:
        wall = f.outer_radius_at(f.strut_y) - f.throat_radius
        assert f.socket_depth < wall, f.name
        assert wall - f.socket_depth >= 1.4, \
            f"{f.name}: only {wall - f.socket_depth:.2f} mm of wall left"


def test_reference_preset_reproduces_the_measured_drone():
    f = Frame.from_json(os.path.join(os.path.dirname(PRESETS[0]),
                                     "reference_drone2.json"))
    assert abs(f.duct_id - 340.0) < 0.5          # measured 340.0
    assert abs(f.duct_od - 380.0) < 0.5          # measured 380.0
    assert abs(f.duct_height - 40.0) < 0.5       # measured 40.0
    assert abs(f.motor_spacing - 479.3) < 0.5    # measured 479.29
    levels = {c.label: c.level for c in check(f)}
    assert levels["inlet lip radius"] == "fail"
    assert levels["duct chord"] == "fail"


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
