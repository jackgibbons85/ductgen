from __future__ import annotations
import math
import os

from .params import Frame
from .segment import RingPlan
from .swapi import SolidWorks, M, _w, _darr, swDefaultTemplateAssembly
from .layout3d import variant_key, instances       # noqa: F401


def _xform(sw, mu, ry_deg, t):
    a = math.radians(ry_deg)
    c, s = math.cos(a), math.sin(a)
    data = [c, 0.0, s,
            0.0, 1.0, 0.0,
            -s, 0.0, c,
            t[0] * M, t[1] * M, t[2] * M,
            1.0, 0.0, 0.0, 0.0]
    return mu.CreateTransform(_darr(data))


def build_assembly(sw: SolidWorks, f: Frame, ring: RingPlan,
                   part_files: dict, outdir: str, keep_open: bool = True):
    tmpl = sw.app.GetUserPreferenceStringValue(swDefaultTemplateAssembly)
    if not tmpl or not os.path.exists(tmpl):
        raise RuntimeError("no default assembly template configured in "
                           "Tools > Options > File Locations")
    for path in sorted(set(part_files.values())):
        if path and os.path.exists(path):
            sw.app.OpenDoc6(path, 1, 1, "", 0, 0)

    doc = sw.app.NewDocument(tmpl, 0, 0, 0)
    model = _w(sw.mod.IModelDoc2, doc)
    asm = _w(sw.mod.IAssemblyDoc, doc)
    mu = _w(sw.mod.IMathUtility, sw.app.GetMathUtility())

    nok, miss = 0, set()
    for key, ry, (x, y, z) in instances(f, ring):
        path = part_files.get(key)
        if not path or not os.path.exists(path):
            miss.add(key)
            continue
        comp = asm.AddComponent5(path, 0, "", False, "", x * M, y * M, z * M)
        if comp is None:
            miss.add(key)
            continue
        comp = _w(sw.mod.IComponent2, comp)
        comp.SetTransformAndSolve2(_xform(sw, mu, ry, (x, y, z)))
        nok += 1

    model.EditRebuild3()
    try:
        model.ViewZoomtofit2()
    except Exception:
        pass

    base = os.path.join(outdir, f"{f.name}_frame")
    paths = [sw.save(model, base + ".SLDASM"), sw.save(model, base + ".STEP"),
             sw.save(model, base + ".STL")]
    if not keep_open:
        sw.close(model)
    return dict(part="ASSEMBLY", qty=1, files=paths, components=nok,
                missing=sorted(miss))
