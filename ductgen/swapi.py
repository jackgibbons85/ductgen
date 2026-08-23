"""Thin, defensive wrapper over the SolidWorks COM API.

Two things this file exists to hide:

1.  Units.  The API is metres and radians; this project is millimetres and
    degrees.  Conversion happens here and nowhere else.
2.  Binding.  Late-bound COM turns SolidWorks methods into properties
    (``doc.GetTitle`` silently returns a string instead of being callable), so
    everything here goes through the makepy-generated wrappers.  The typelib
    is registered on demand the first time the tool runs.

Plane selection walks the feature tree for RefPlane features rather than
hard-coding "Front Plane", so a non-English install still works.
"""
from __future__ import annotations
import glob
import math
import os

import pythoncom
import win32com.client as win32
from win32com.client import VARIANT, gencache, makepy

M = 0.001                       # mm -> m

SW_TYPELIB = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

# swConst values used here
swDocPART = 1
swDefaultTemplatePart = 8       # swUserPreferenceStringValue_e
swDefaultTemplateAssembly = 9
swEndCondBlind = 0
swEndCondThroughAll = 1
swRefPlaneConstraint_Distance = 8

# swUserPreferenceToggle_e / IntegerValue_e for the STL exporter
swSTLBinaryFormat = 69
swSTLShowInfoOnSave = 70
swSTLDontTranslateToPositive = 71
swSTLQuality = 78                # integer pref
swSTLQuality_Fine = 2
swExportStlUnits = 211           # 0 = mm
swUnitsLinear = 47

_MOD = None


def _tlb_paths():
    pats = [r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb",
            r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb",
            r"C:\Program Files*\SOLIDWORKS*\**\sldworks.tlb"]
    out = []
    for p in pats:
        out += glob.glob(p, recursive=True) if "*" in p else ([p] if os.path.exists(p) else [])
    return out


def module():
    """The generated early-binding module for the SolidWorks typelib."""
    global _MOD
    if _MOD is not None:
        return _MOD
    for major in range(40, 18, -1):
        try:
            _MOD = gencache.EnsureModule(SW_TYPELIB, 0, major, 0)
            return _MOD
        except Exception:
            pass
    for tlb in _tlb_paths():
        try:
            makepy.GenerateFromTypeLibSpec(tlb, verboseLevel=0)
        except Exception:
            pass
    for major in range(40, 18, -1):
        try:
            _MOD = gencache.EnsureModule(SW_TYPELIB, 0, major, 0)
            return _MOD
        except Exception:
            pass
    raise RuntimeError(
        "could not build Python wrappers for the SolidWorks typelib. Check "
        "that SolidWorks is installed and sldworks.tlb is readable.")


def _w(cls, obj):
    """Wrap a COM object in a generated interface class.

    win32com hands back late-bound CDispatch objects; the generated classes
    need the underlying PyIDispatch, so unwrap one level when present.
    """
    if obj is None:
        return None
    return cls(getattr(obj, "_oleobj_", obj))


def _darr(values):
    """A VARIANT array of doubles, which is what the sketch API wants."""
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])


class SolidWorks:
    def __init__(self, visible: bool = True, attach: bool = True):
        self.mod = module()
        raw = None
        if attach:
            try:
                raw = win32.GetActiveObject("SldWorks.Application")
            except Exception:
                raw = None
        if raw is None:
            raw = win32.Dispatch("SldWorks.Application")
        # Visible / UserControl are put-properties the generated wrapper does
        # not expose, so set them on the raw dispatch before wrapping.
        try:
            raw.Visible = visible
            raw.UserControl = True
        except Exception:
            pass
        self.raw = raw
        self.app = _w(self.mod.ISldWorks, raw)
        self.configure_export()

    def configure_export(self):
        """STL defaults that matter for a generator.

        Without DontTranslateToPositive the exporter shifts every part into
        the positive octant, which throws away the placement the assembly
        needs; without ShowInfoOnSave=False a modal dialog blocks the save
        and the whole run hangs.
        """
        for pref, val in ((swSTLBinaryFormat, True),
                          (swSTLShowInfoOnSave, False),
                          (swSTLDontTranslateToPositive, True)):
            try:
                self.app.SetUserPreferenceToggle(pref, val)
            except Exception:
                pass
        for pref, val in ((swSTLQuality, swSTLQuality_Fine),
                          (swExportStlUnits, 0)):
            try:
                self.app.SetUserPreferenceIntegerValue(pref, val)
            except Exception:
                pass

    @property
    def version(self):
        return self.app.RevisionNumber()

    # ---------------- documents ----------------
    def new_part(self):
        tmpl = self.app.GetUserPreferenceStringValue(swDefaultTemplatePart)
        if not tmpl or not os.path.exists(tmpl):
            raise RuntimeError(
                "SolidWorks has no default part template configured. Set one "
                "in Tools > Options > File Locations > Document Templates.")
        doc = self.app.NewDocument(tmpl, 0, 0, 0)
        if doc is None:
            raise RuntimeError(f"NewDocument failed for template {tmpl}")
        return _w(self.mod.IModelDoc2, doc)

    def ext(self, model):
        return _w(self.mod.IModelDocExtension, model.Extension)

    def part(self, model):
        return _w(self.mod.IPartDoc, model)

    def close(self, model):
        self.app.CloseDoc(model.GetTitle())

    # ---------------- selection ----------------
    def base_planes(self, model):
        """[front, top, right] in tree order, whatever they are called."""
        names = []
        feat = model.FirstFeature()
        while feat is not None and len(names) < 3:
            feat = _w(self.mod.IFeature, feat)
            try:
                if feat.GetTypeName2() == "RefPlane":
                    names.append(feat.Name)
            except Exception:
                pass
            feat = feat.GetNextFeature()
        if len(names) < 3:
            raise RuntimeError("could not find the three default planes")
        return names

    def select(self, model, name, typ, append=False, mark=0):
        ok = self.ext(model).SelectByID2(name, typ, 0, 0, 0, append, mark, None, 0)
        if not ok:
            raise RuntimeError(f"could not select {typ} '{name}'")
        return ok

    @staticmethod
    def clear(model):
        model.ClearSelection2(True)

    # ---------------- sketching ----------------
    def begin_sketch(self, model, plane_name):
        self.clear(model)
        self.select(model, plane_name, "PLANE")
        sm = _w(self.mod.ISketchManager, model.SketchManager)
        sm.InsertSketch(True)
        model.SetAddToDB(True)
        model.SetDisplayWhenAdded(False)
        return sm

    def end_sketch(self, model):
        model.SetAddToDB(False)
        model.SetDisplayWhenAdded(True)
        sm = _w(self.mod.ISketchManager, model.SketchManager)
        sm.InsertSketch(True)
        self.clear(model)
        # the sketch is now the newest feature in the tree; ISketch carries no
        # name of its own, IFeature does
        return _w(self.mod.IFeature, model.FeatureByPositionReverse(0)).Name

    # -- sketch primitives, mm in, metres out ------------------------------
    @staticmethod
    def line(sm, p0, p1):
        return sm.CreateLine(p0[0] * M, p0[1] * M, 0.0, p1[0] * M, p1[1] * M, 0.0)

    @staticmethod
    def centerline(sm, p0, p1):
        return sm.CreateCenterLine(p0[0] * M, p0[1] * M, 0.0,
                                   p1[0] * M, p1[1] * M, 0.0)

    @staticmethod
    def arc(sm, c, p0, p1, ccw=True):
        return sm.CreateArc(c[0] * M, c[1] * M, 0.0,
                            p0[0] * M, p0[1] * M, 0.0,
                            p1[0] * M, p1[1] * M, 0.0,
                            1 if ccw else -1)

    @staticmethod
    def spline(sm, pts):
        flat = []
        for x, y in pts:
            flat += [x * M, y * M, 0.0]
        return sm.CreateSpline2(_darr(flat), True)

    @staticmethod
    def circle(sm, c, dia):
        return sm.CreateCircleByRadius(c[0] * M, c[1] * M, 0.0, dia * M / 2.0)

    @classmethod
    def polygon(cls, sm, pts, close=True):
        n = len(pts)
        for i in range(n - (0 if close else 1)):
            cls.line(sm, pts[i], pts[(i + 1) % n])

    # ---------------- features ----------------
    def fm(self, model):
        return _w(self.mod.IFeatureManager, model.FeatureManager)

    def revolve(self, model, sketch_name, angle_deg, angle2_deg=None,
                reverse=False, merge=True):
        """Blind revolve. Pass angle2_deg for a symmetric two-direction one."""
        self.clear(model)
        self.select(model, sketch_name, "SKETCH")
        single = angle2_deg is None
        f = self.fm(model).FeatureRevolve2(
            single,                     # SingleDir
            True,                       # IsSolid
            False,                      # IsThin
            False,                      # IsCut
            reverse,                    # ReverseDir
            False,                      # BothDirectionUpToSameEntity
            0, 0,                       # Type1, Type2 (blind)
            math.radians(angle_deg),
            math.radians(angle2_deg or 0.0),
            False, False, 0.0, 0.0,     # offsets
            0, 0.0, 0.0,                # thin
            merge, True, True)
        if f is None:
            raise RuntimeError(f"revolve of '{sketch_name}' failed "
                               f"({angle_deg:.2f} deg)")
        return f

    def cut(self, model, sketch_name, *, through_both=False, depth=None,
            reverse=False, both_dirs=False):
        """Cut-extrude the named sketch: through-all (optionally both
        directions) or blind by `depth` mm (optionally both directions)."""
        self.clear(model)
        self.select(model, sketch_name, "SKETCH")
        if depth is None:
            single = not through_both
            t1 = t2 = swEndCondThroughAll
            d1 = d2 = 0.01
        else:
            single = not both_dirs
            t1 = t2 = swEndCondBlind
            d1 = d2 = depth * M
        f = self.fm(model).FeatureCut4(
            single,                     # Sd, single direction
            False,                      # Flip side to cut
            reverse,                    # Dir, reverse direction
            t1, t2, d1, d2,
            False, False,               # Dchk1, Dchk2 (draft)
            False, False,               # Ddir1, Ddir2
            0.0, 0.0,                   # Dang1, Dang2
            False, False,               # OffsetReverse1/2
            False, False,               # TranslateSurface1/2
            False,                      # NormalCut
            True, True,                 # UseFeatScope, UseAutoSelect
            False, True, False,         # assembly scope args
            0, 0.0, False,              # T0 / StartOffset / FlipStartOffset
            False)                      # OptimizeGeometry
        if f is None:
            raise RuntimeError(f"cut of '{sketch_name}' failed")
        return f

    def extrude(self, model, sketch_name, depth, both=False, merge=True):
        self.clear(model)
        self.select(model, sketch_name, "SKETCH")
        f = self.fm(model).FeatureExtrusion3(
            not both,                   # Sd
            False, False,               # Flip, Dir
            swEndCondBlind, swEndCondBlind,
            depth * M, depth * M,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            merge, True, True,
            0, 0.0, False)
        if f is None:
            raise RuntimeError(f"extrude of '{sketch_name}' failed")
        return f

    def offset_plane(self, model, from_plane, distance):
        self.clear(model)
        self.select(model, from_plane, "PLANE")
        f = self.fm(model).InsertRefPlane(
            swRefPlaneConstraint_Distance, distance * M, 0, 0, 0, 0)
        if f is None:
            raise RuntimeError(f"offset plane {distance} mm from "
                               f"'{from_plane}' failed")
        # InsertRefPlane hands back an IRefPlane, not an IFeature, so take the
        # name off the newest tree node instead
        return _w(self.mod.IFeature, model.FeatureByPositionReverse(0)).Name

    # ---------------- output ----------------
    def close_if_open(self, path):
        """A document already open under the target name makes SaveAs fail
        with a generic error, so evict it first."""
        try:
            self.app.CloseDoc(os.path.basename(path))
        except Exception:
            pass

    def save(self, model, path):
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.close_if_open(path)
        # SaveAs3's Errors/Warnings are in/out params, so they must be passed
        # in as well as read back out
        res = self.ext(model).SaveAs3(path, 0, 1, None, None, 0, 0)
        ok, errs, warns = res if isinstance(res, tuple) else (res, 0, 0)
        if not ok:
            raise RuntimeError(f"save failed: {path} (err {errs}, warn {warns})")
        return path

    def rebuild(self, model):
        model.EditRebuild3()
        model.ViewZoomtofit2()
