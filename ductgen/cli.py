from __future__ import annotations
import argparse
import json
import os
import sys
from dataclasses import asdict

from .params import Frame, check
from .profile import print_mass, ring_volume
from .segment import plan_ring, plan_other_parts, print_notes


def load(path) -> Frame:
    return Frame.from_json(path) if path else Frame()


def apply_overrides(f: Frame, kvs):
    for kv in kvs:
        key, _, val = kv.partition("=")
        obj = f
        parts = key.split(".")
        for p in parts[:-1]:
            obj = getattr(obj, p)
        cur = getattr(obj, parts[-1])
        cast = type(cur)
        setattr(obj, parts[-1], cast(val) if cast is not bool
                else val.lower() in ("1", "true", "yes"))
    return f


def report(f: Frame) -> str:
    ring = plan_ring(f)
    L = []
    w = L.append
    w(f"{f.name}   {f.prop.diameter_in}\" x {f.prop.blades} prop   "
      f"{f.motor.stator} {f.motor.kv} kV on {f.motor.cells}S")
    w("=" * 78)
    w("")
    w("GEOMETRY")
    w(f"  prop diameter          {f.prop.diameter:8.1f} mm")
    w(f"  duct throat (ID)       {f.duct_id:8.1f} mm   "
      f"tip gap {(f.duct_id - f.prop.diameter)/2:.2f} mm/side")
    w(f"  duct OD, inlet         {f.duct_od:8.1f} mm")
    w(f"  duct OD, exit          {f.duct_od_exit:8.1f} mm   "
      f"outer skin {f.outer_taper_deg:.1f} deg from vertical")
    w(f"  duct chord (height)    {f.duct_height:8.1f} mm")
    w(f"  inlet lip radius       {f.lip_radius:8.1f} mm   "
      f"({f.lip_radius/f.prop.diameter*100:.1f}% of D)")
    w(f"  prop plane below lip   {f.prop_plane_y:8.1f} mm")
    w(f"  motor spacing          {f.motor_spacing:8.1f} mm   "
      f"diagonal {f.motor_diagonal:.0f} mm")
    w(f"  overall footprint      {f.footprint:8.1f} mm square")
    w("")
    w("PERFORMANCE")
    w(f"  rpm, nominal / full    {f.rpm_nominal:8,.0f} / {f.rpm_full:,.0f}")
    w(f"  tip Mach at full       {f.tip_mach():8.2f}")
    w(f"  expansion ratio sigma  {f.expansion_ratio:8.2f}")
    w(f"  ideal duct gain        {f.ideal_thrust_gain:8.2f} x  "
      "(equal shaft power, attached inlet)")
    m = print_mass(f)
    w(f"  duct mass, 3 walls/15% {m['grams']:8.0f} g per ring, "
      f"{4*m['grams']/1000:.2f} kg for four")
    w("")
    w("DESIGN RULES")
    for c in check(f):
        w(f"  [{c.level.upper():4}] {c.label:<24} {c.value:<34} want {c.want}")
        if c.note and c.level != "ok":
            w(f"         {c.note}")
    w("")
    w("SPLIT FOR THE BED")
    w(f"  printer                {f.printer.name}  "
      f"{f.printer.bed_x:.0f} x {f.printer.bed_y:.0f} x {f.printer.bed_z:.0f} mm"
      f"{'  (diagonal placement allowed)' if f.printer.allow_diagonal else ''}")
    w(f"  segments per ring      {ring.count}   "
      f"sweep {ring.segments[0].sweep_deg:.1f} deg incl. {f.joint.lap_deg:.0f} deg lap")
    w(f"  {ring.note}")
    w("")
    w(f"  {'part':<34}{'w':>8}{'d':>8}{'h':>8}{'qty':>6}  fits")
    for p in plan_other_parts(f, ring):
        w(f"  {p.name:<34}{p.w:8.1f}{p.h:8.1f}{p.z:8.1f}{p.qty:6d}  "
          f"{'yes' if p.fits else 'NO':<4} {p.note}")
    w("")
    w("HARDWARE")
    nj = len(ring.joint_angles)
    nb = nj * f.joint.bolts * 4
    if f.joint.stud > 0:
        w(f"  {f.joint.stud:.1f} mm joint studs   {nb:4d}   "
          f"({f.joint.bolts} per joint, {nj} joints per ring, 4 rings). "
          f"Blind {f.stud_depth:.1f} mm each side, cut your own from rod. "
          "No screws: the carbon wrap is the joint.")
    else:
        w(f"  M{f.joint.bolt_size:.0f} joint bolts       {nb:4d}   "
          f"({f.joint.bolts} per joint, {nj} joints per ring incl. the two "
          "connector ends, 4 rings)")
    w(f"  M{f.motor.bolt_size:.0f} motor bolts       "
      f"{4*f.motor.bolt_count:4d}")
    w("")
    w("PRINT NOTES")
    for note in print_notes(f):
        w(f"  - {note}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ductgen",
                                 description="Parametric ducted quad frame generator")
    ap.add_argument("command", choices=["preview", "section", "layers",
                                        "report", "build", "set", "dump"])
    ap.add_argument("-p", "--params", help="parameter JSON file")
    ap.add_argument("-o", "--out", default="out", help="output directory")
    ap.add_argument("--hidden", action="store_true",
                    help="run SolidWorks without showing the window")
    ap.add_argument("--keep-open", action="store_true",
                    help="leave the generated parts open in SolidWorks")
    ap.add_argument("--opaque", action="store_true",
                    help="layers: dark ground instead of transparent")
    ap.add_argument("--backend", choices=["sw", "b3d"], default="sw",
                    help="build: sw drives SolidWorks over COM, b3d uses "
                         "build123d and needs no CAD seat")
    ap.add_argument("overrides", nargs="*",
                    help="dotted overrides, e.g. prop.diameter_in=5")
    a = ap.parse_args(argv)

    f = apply_overrides(load(a.params), a.overrides)
    os.makedirs(a.out, exist_ok=True)

    if a.command == "dump":
        print(json.dumps(asdict(f), indent=2))
        return 0

    if a.command == "set":
        if not a.params:
            ap.error("set needs -p to say which file to write")
        f.to_json(a.params)
        print(f"wrote {a.params}")
        return 0

    if a.command == "report":
        txt = report(f)
        print(txt)
        p = os.path.join(a.out, f"{f.name}_report.txt")
        open(p, "w").write(txt)
        print(f"\n[saved {p}]")
        return 0

    if a.command == "preview":
        from .preview import render
        sec = os.path.join(a.out, f"{f.name}_section.png")
        p = render(f, os.path.join(a.out, f"{f.name}_preview.png"),
                   section_path=sec)
        print(report(f))
        print(f"\n[saved {p}]")
        print(f"[saved {sec}]")
        return 0

    if a.command == "section":
        from .preview import render_section
        p = render_section(f, os.path.join(a.out, f"{f.name}_section.png"))
        print(f"[saved {p}]")
        return 0

    if a.command == "layers":
        from .preview import render_layers
        d = os.path.join(a.out, f"{f.name}_layers")
        for p in render_layers(f, d, transparent=not a.opaque):
            print(f"[saved {p}]")
        print("\nstack them bottom-up in the editor: 1_ducts, 2_connectors, "
              "3_rods.\n1+2 is the frame without rods; all three is the whole "
              "aircraft.\nEvery plate is 1920x1080 on the same extent, so they "
              "overlay exactly.")
        return 0

    if a.command == "build":
        from .layout3d import placement_table
        ring = plan_ring(f)
        if not ring.fits:
            print("WARNING: no segment count fits this bed; building anyway "
                  "at the smallest overflow.", file=sys.stderr)
        if a.backend == "b3d":
            from .build_b3d import build_all
            made = build_all(f, a.out, ring=ring)
        else:
            from .build_sw import build_all
            made = build_all(f, a.out, visible=not a.hidden, ring=ring,
                             keep_open=a.keep_open)
        for r in made:
            line = f"{r['part']:<14} qty {r['qty']:<3}"
            if "volume_cm3" in r:
                line += f" {r['volume_cm3']:8.1f} cm3"
            if "components" in r:
                line += f" {r['components']} components placed"
                if r.get("missing"):
                    line += f"  MISSING: {', '.join(r['missing'])}"
            print(line)
            for p in r["files"]:
                print(f"   {p}")
        tbl = os.path.join(a.out, f"{f.name}_placement.json")
        json.dump(placement_table(f, ring), open(tbl, "w"), indent=2)
        f.to_json(os.path.join(a.out, f"{f.name}_params.json"))
        open(os.path.join(a.out, f"{f.name}_report.txt"), "w").write(report(f))
        print(f"\nplacement table {tbl}")
        return 0
    return 1
