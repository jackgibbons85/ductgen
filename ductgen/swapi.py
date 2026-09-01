from __future__ import annotations
import glob
import math
import os

import pythoncom
import win32com.client as win32
from win32com.client import VARIANT, gencache, makepy

M = 0.001

SW_TYPELIB = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

swDocPART = 1
swDefaultTemplatePart = 8
swDefaultTemplateAssembly = 9
swEndCondBlind = 0
swEndCondThroughAll = 1
swRefPlaneConstraint_Distance = 8

swSTLBinaryFormat = 69
swSTLShowInfoOnSave = 70
swSTLDontTranslateToPositive = 71
swSTLQuality = 78
swSTLQuality_Fine = 2
swExportStlUnits = 211
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
    if obj is None:
        return None
    return cls(getattr(obj, "_oleobj_", obj))


def _darr(values):
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
        try:
            raw.Visible = visible
            raw.UserControl = True
        except Exception:
            pass
        self.raw = raw
        self.app = _w(self.mod.ISldWorks, raw)
        self.configure_export()

    def configure_export(self):
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

    def close_all(self):
        try:
            self.app.CloseAllDocuments(True)
        except Exception:
            pass

    def base_planes(self, model):
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
        model.EditRebuild3()
        self.clear(model)
        return _w(self.mod.IFeature, model.FeatureByPositionReverse(0)).Name

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

    def fm(self, model):
        return _w(self.mod.IFeatureManager, model.FeatureManager)

    def revolve(self, model, sketch_name, angle_deg, angle2_deg=None,
                reverse=False, merge=True):
        self.clear(model)
        self.select(model, sketch_name, "SKETCH")
        single = angle2_deg is None
        f = self.fm(model).FeatureRevolve2(
            single,
            True,
            False,
            False,
            reverse,
            False,
            0, 0,
            math.radians(angle_deg),
            math.radians(angle2_deg or 0.0),
            False, False, 0.0, 0.0,
            0, 0.0, 0.0,
            merge, True, True)
        if f is None:
            raise RuntimeError(f"revolve of '{sketch_name}' failed "
                               f"({angle_deg:.2f} deg)")
        return f

    def cut(self, model, sketch_name, *, through_both=False, depth=None,
            reverse=False, both_dirs=False, feat_scope=True):
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
            single,
            False,
            reverse,
            t1, t2, d1, d2,
            False, False,
            False, False,
            0.0, 0.0,
            False, False,
            False, False,
            False,
            feat_scope, True,
            False, True, False,
            0, 0.0, False,
            False)
        if f is None:
            raise RuntimeError(f"cut of '{sketch_name}' failed")
        return f

    def extrude(self, model, sketch_name, depth, both=False, merge=True,
                feat_scope=True):
        self.clear(model)
        self.select(model, sketch_name, "SKETCH")
        f = self.fm(model).FeatureExtrusion3(
            not both,
            False, False,
            swEndCondBlind, swEndCondBlind,
            depth * M, depth * M,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            merge, feat_scope, True,
            0, 0.0, False)
        if f is None:
            raise RuntimeError(f"extrude of '{sketch_name}' failed")
        return f

    def axis_from_planes(self, model, plane_a, plane_b):
        self.clear(model)
        self.select(model, plane_a, "PLANE")
        self.select(model, plane_b, "PLANE", append=True)
        if not model.InsertAxis2(True):
            raise RuntimeError(f"axis from '{plane_a}' x '{plane_b}' failed")
        self.clear(model)
        return _w(self.mod.IFeature, model.FeatureByPositionReverse(0)).Name

    def circular_pattern(self, model, features, axis_name, count, angle_deg,
                         equal=True):
        self.clear(model)
        ext = self.ext(model)
        for i, name in enumerate(features):
            if not ext.SelectByID2(name, "BODYFEATURE", 0, 0, 0, i > 0, 4,
                                   None, 0):
                raise RuntimeError(f"could not select feature '{name}'")
        if not ext.SelectByID2(axis_name, "AXIS", 0, 0, 0, True, 1, None, 0):
            raise RuntimeError(f"could not select axis '{axis_name}'")
        p = self.fm(model).FeatureCircularPattern5(
            count, math.radians(angle_deg), False, "NULL", False, equal,
            False, False, False, False, 1, 0.0, "NULL", False)
        if p is None:
            raise RuntimeError(f"circular pattern of {features} failed")
        self.clear(model)
        return p

    def last_feature_name(self, model):
        return _w(self.mod.IFeature, model.FeatureByPositionReverse(0)).Name

    def move_bodies(self, model, dx=0.0, dy=0.0, dz=0.0, angle_deg=0.0):
        return self._move(model, dx, dy, dz, angle_deg)

    def rotate_bodies_y(self, model, angle_deg):
        self.clear(model)
        b = self.part(model).GetBodies2(0, True)
        if b is None:
            raise RuntimeError("no solid body to rotate")
        b = list(b) if isinstance(b, (list, tuple)) else [b]
        ext = self.ext(model)
        np = 0
        for i, body in enumerate(b):
            name = _w(self.mod.IBody2, body).Name
            if ext.SelectByID2(name, "SOLIDBODY", 0, 0, 0, np > 0, 1,
                               None, 0):
                np += 1
        if not np:
            raise RuntimeError("could not select any body for the rotate")
        return self._move(model, 0.0, 0.0, 0.0, angle_deg)

    def _move(self, model, dx, dy, dz, angle_deg):
        self.clear(model)
        b = self.part(model).GetBodies2(0, True)
        if b is None:
            raise RuntimeError("no solid body to move")
        b = list(b) if isinstance(b, (list, tuple)) else [b]
        ext = self.ext(model)
        np_ = 0
        for body in b:
            name = _w(self.mod.IBody2, body).Name
            if ext.SelectByID2(name, "SOLIDBODY", 0, 0, 0, np_ > 0, 1, None, 0):
                np_ += 1
        if not np_:
            raise RuntimeError("could not select any body to move")
        f = self.fm(model).InsertMoveCopyBody2(
            dx * M, dy * M, dz * M, 0.0,
            0.0, 0.0, 0.0,
            0.0, math.radians(angle_deg), 0.0,
            False, 1)
        if f is None:
            raise RuntimeError(f"body move ({dx:.2f},{dy:.2f},{dz:.2f}) "
                               f"rot {angle_deg:.2f} failed")
        self.clear(model)
        return f

    def offset_plane(self, model, from_plane, distance):
        self.clear(model)
        self.select(model, from_plane, "PLANE")
        f = self.fm(model).InsertRefPlane(
            swRefPlaneConstraint_Distance, distance * M, 0, 0, 0, 0)
        if f is None:
            raise RuntimeError(f"offset plane {distance} mm from "
                               f"'{from_plane}' failed")
        return _w(self.mod.IFeature, model.FeatureByPositionReverse(0)).Name

    def close_if_open(self, path):
        try:
            self.app.CloseDoc(os.path.basename(path))
        except Exception:
            pass

    def save(self, model, path):
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.close_if_open(path)
        res = self.ext(model).SaveAs3(path, 0, 1, None, None, 0, 0)
        ok, errs, warns = res if isinstance(res, tuple) else (res, 0, 0)
        if not ok:
            raise RuntimeError(f"save failed: {path} (err {errs}, warn {warns})")
        return path

    _top_sign = None

    def top_sketch_z_sign(self):
        if SolidWorks._top_sign is not None:
            return SolidWorks._top_sign
        model = self.new_part()
        front, top, right = self.base_planes(model)
        sm = self.begin_sketch(model, top)
        self.circle(sm, (0.0, 50.0), 20.0)
        name = self.end_sketch(model)
        self.extrude(model, name, 5.0)
        body = self.part(model).GetBodies2(0, True)
        body = body[0] if isinstance(body, (list, tuple)) else body
        com = _w(self.mod.IBody2, body).GetMassProperties(1000.0)
        sign = 1.0 if com[2] > 0 else -1.0
        self.app.CloseDoc(model.GetTitle())
        SolidWorks._top_sign = sign
        return sign

    _cut_front_reverse = None

    def cut_front_reverse(self):
        if SolidWorks._cut_front_reverse is not None:
            return SolidWorks._cut_front_reverse
        model = self.new_part()
        front, top, right = self.base_planes(model)
        sm = self.begin_sketch(model, front)
        self.circle(sm, (0.0, 0.0), 60.0)
        self.extrude(model, self.end_sketch(model), 10.0, both=True)
        sm = self.begin_sketch(model, front)
        self.circle(sm, (0.0, 0.0), 30.0)
        self.cut(model, self.end_sketch(model), depth=8.0, reverse=False)
        body = self.part(model).GetBodies2(0, True)
        body = body[0] if isinstance(body, (list, tuple)) else body
        com = _w(self.mod.IBody2, body).GetMassProperties(1000.0)
        rev = com[2] > 0
        self.app.CloseDoc(model.GetTitle())
        SolidWorks._cut_front_reverse = rev
        return rev

    _cut_up_reverse = None

    def cut_up_reverse(self):
        if SolidWorks._cut_up_reverse is not None:
            return SolidWorks._cut_up_reverse
        model = self.new_part()
        front, top, right = self.base_planes(model)
        sm = self.begin_sketch(model, top)
        self.circle(sm, (0.0, 0.0), 60.0)
        self.extrude(model, self.end_sketch(model), 10.0, both=True)
        sm = self.begin_sketch(model, top)
        self.circle(sm, (0.0, 0.0), 30.0)
        self.cut(model, self.end_sketch(model), depth=8.0, reverse=False)
        body = self.part(model).GetBodies2(0, True)
        body = body[0] if isinstance(body, (list, tuple)) else body
        com = _w(self.mod.IBody2, body).GetMassProperties(1000.0)
        rev = com[1] > 0
        self.app.CloseDoc(model.GetTitle())
        SolidWorks._cut_up_reverse = rev
        return rev

    def prime(self):
        self.top_sketch_z_sign()
        self.cut_up_reverse()
        self.cut_front_reverse()

    def body_box(self, model):
        b = self.part(model).GetBodies2(0, True)
        b = b[0] if isinstance(b, (list, tuple)) else b
        box = _w(self.mod.IBody2, b).GetBodyBox()
        return tuple(v * 1000.0 for v in box)

    def top_xy(self, x, z):
        return (x, z * self.top_sketch_z_sign())

    def rebuild(self, model):
        model.EditRebuild3()
        model.ViewZoomtofit2()
