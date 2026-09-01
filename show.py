import argparse
import sys
import tempfile

from ocp_vscode import show, set_defaults, Camera

from ductgen.params import Frame
from ductgen.segment import plan_ring
from ductgen.layout3d import instances, rod_variants, variant_key
from ductgen import build_b3d as B


def parts(f, ring, d):
    out = {"segment": B.build_segment(f, ring, d)["solid"]}
    for ft, _ in sorted((k, v) for k, v in rod_variants(f, ring).items()
                        if k is not None):
        k = variant_key(ft)
        out[k.replace("duct_segment_", "seg_")] = B.build_segment(
            f, ring, d, rods=ft, tag="_" + k.split("duct_segment_")[1])["solid"]
    out["mount"] = B.build_mount(f, d)["solid"]
    if f.connector.enabled:
        out["connector"] = B.build_connector(f, ring, d)["solid"]
    out["plate"] = B.build_center_plate(f, d)["solid"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="frame",
                    help="frame, or a part name: segment mount connector plate")
    ap.add_argument("-p", "--params", default="presets/13in_a1.json")
    a = ap.parse_args()

    f = Frame.from_json(a.params) if a.params else Frame()
    ring = plan_ring(f)
    set_defaults(reset_camera=Camera.CENTER, black_edges=True)

    with tempfile.TemporaryDirectory() as d:
        made = parts(f, ring, d)
        if a.what == "frame":
            from build123d import Pos, Rot
            for tag, (sz, L) in B.rod_specs(f).items():
                made["rod_" + tag] = B.build_rod(f, sz, L, tag, d)["solid"]
            keys = {"duct_segment": "segment"}
            placed = []
            for k, ry, (x, y, z) in instances(f, ring):
                nm = keys.get(k, k.replace("duct_segment_", "seg_"))
                nm = {"motor_mount": "mount",
                      "center_plate": "plate"}.get(nm, nm)
                s = made.get(nm)
                if s is not None:
                    placed.append(Pos(x, z, y) * Rot(0, 0, ry) * s)
            print(f"{f.name}: {len(placed)} components, "
                  f"{ring.count} arcs at {ring.segments[0].utilisation*100:.0f}% "
                  "of the plate")
            show(*placed, names=[f"c{i}" for i in range(len(placed))])
        else:
            hits = {k: v for k, v in made.items() if a.what in k}
            if not hits:
                sys.exit(f"no part matching {a.what!r}. have: "
                         + ", ".join(made))
            for k, v in hits.items():
                print(f"  {k:<28} {v.volume/1000:8.2f} cm3")
            show(*hits.values(), names=list(hits))


if __name__ == "__main__":
    main()
