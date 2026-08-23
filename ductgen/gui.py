"""Desktop front end.

The point of this window is that the design rules update as you type, so you
find out the lip is too sharp or the ring will not fit the plate before
SolidWorks is involved at all.

    python -m ductgen.gui          (or double-click ductgen-gui.pyw)
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .params import Frame, check
from .segment import plan_ring, plan_other_parts

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS = os.path.join(HERE, "presets")


def load_printers():
    try:
        with open(os.path.join(PRESETS, "printers.json")) as f:
            return json.load(f)
    except Exception:
        return {"Bambu A1": {"bed_x": 256, "bed_y": 256, "bed_z": 256, "nozzle": 0.4}}


# fields: (label, dotted path, kind)  kind: f=float i=int s=str b=bool
FIELDS = [
    ("Propeller", [
        ("diameter (in)",       "prop.diameter_in",          "f"),
        ("pitch (in)",          "prop.pitch_in",             "f"),
        ("blades",              "prop.blades",               "i"),
    ]),
    ("Motor", [
        ("stator code",         "motor.stator",              "s"),
        ("kV",                  "motor.kv",                  "i"),
        ("battery cells (S)",   "motor.cells",               "i"),
        ("body OD (mm)",        "motor.body_od",             "f"),
        ("mount pattern",       "motor.bolt_pattern",        "c:square,circle"),
        ("mount span (mm)",     "motor.bolt_span",           "f"),
        ("mount bolts",         "motor.bolt_count",          "i"),
        ("mount bolt M-size",   "motor.bolt_size",           "f"),
    ]),
    ("Duct", [
        ("tip clearance (% D)", "duct.tip_clearance_pct",    "f"),
        ("chord / D",           "duct.chord_ratio",          "f"),
        ("lip radius / D",      "duct.lip_radius_ratio",     "f"),
        ("lip ellipse ratio",   "duct.lip_ellipse_ratio",    "f"),
        ("diffuser (deg)",      "duct.diffuser_deg",         "f"),
        ("prop plane / chord",  "duct.prop_plane_frac",      "f"),
        ("min wall (mm)",       "duct.wall",                 "f"),
        ("force OD (0 = auto)", "duct.od_override",          "f"),
    ]),
    ("Struts and joints", [
        ("strut count",         "struts.count",              "i"),
        ("strut thickness (mm)", "struts.thickness",         "f"),
        ("strut chord (mm)",    "struts.chord",              "f"),
        ("hub OD (mm)",         "struts.hub_od",             "f"),
        ("joint lap (deg)",     "joint.lap_deg",             "f"),
        ("bolts per joint",     "joint.bolts",               "i"),
        ("joint bolt M-size",   "joint.bolt_size",           "f"),
    ]),
    ("Printer", [
        ("bed X (mm)",          "printer.bed_x",             "f"),
        ("bed Y (mm)",          "printer.bed_y",             "f"),
        ("bed Z (mm)",          "printer.bed_z",             "f"),
        ("edge margin (mm)",    "printer.margin",            "f"),
        ("nozzle (mm)",         "printer.nozzle",            "f"),
        ("rotate on plate",     "printer.allow_diagonal",    "b"),
    ]),
    ("Layout", [
        ("gap between ducts",   "layout.duct_gap",           "f"),
        ("carbon rod size (mm)", "layout.rod_size",          "f"),
        ("design name",         "name",                      "s"),
    ]),
]


def get_path(obj, path):
    for p in path.split("."):
        obj = getattr(obj, p)
    return obj


def set_path(obj, path, value):
    parts = path.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], value)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ductgen - ducted frame generator")
        self.geometry("1080x760")
        self.minsize(900, 640)
        self.frame = Frame()
        self.vars = {}
        self.printers = load_printers()
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Printer").pack(side="left")
        self.printer_cb = ttk.Combobox(top, values=list(self.printers),
                                       state="readonly", width=20)
        self.printer_cb.set(self.frame.printer.name)
        self.printer_cb.pack(side="left", padx=(4, 14))
        self.printer_cb.bind("<<ComboboxSelected>>", self.on_printer)

        for txt, cmd in (("Load preset", self.on_load), ("Save preset", self.on_save),
                         ("Preview PNG", self.on_preview), ("Save report", self.on_report)):
            ttk.Button(top, text=txt, command=cmd).pack(side="left", padx=3)
        self.build_btn = ttk.Button(top, text="Build in SolidWorks",
                                    command=self.on_build)
        self.build_btn.pack(side="right")

        body = ttk.Frame(self, padding=(8, 0))
        body.pack(fill="both", expand=True)

        # ---- left: inputs, scrollable ---------------------------------
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        canvas = tk.Canvas(left, width=430, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-e.delta // 120, "units"))

        for group, rows in FIELDS:
            lf = ttk.LabelFrame(inner, text=group, padding=6)
            lf.pack(fill="x", pady=4, padx=4)
            for i, (label, path, kind) in enumerate(rows):
                ttk.Label(lf, text=label).grid(row=i, column=0, sticky="w", pady=1)
                cur = get_path(self.frame, path)
                if kind == "b":
                    v = tk.BooleanVar(value=bool(cur))
                    w = ttk.Checkbutton(lf, variable=v, command=self.refresh)
                elif kind.startswith("c:"):
                    v = tk.StringVar(value=str(cur))
                    w = ttk.Combobox(lf, textvariable=v, state="readonly",
                                     width=14, values=kind[2:].split(","))
                    w.bind("<<ComboboxSelected>>", lambda e: self.refresh())
                else:
                    v = tk.StringVar(value=str(cur))
                    w = ttk.Entry(lf, textvariable=v, width=16)
                    w.bind("<FocusOut>", lambda e: self.refresh())
                    w.bind("<Return>", lambda e: self.refresh())
                w.grid(row=i, column=1, sticky="e", pady=1)
                lf.columnconfigure(0, weight=1)
                self.vars[path] = (v, kind)

        # ---- right: live results --------------------------------------
        right = ttk.Frame(body, padding=(10, 4))
        right.pack(side="left", fill="both", expand=True)
        self.summary = tk.Text(right, height=9, wrap="word", font=("Consolas", 9),
                               relief="flat", background="#f6f6f6")
        self.summary.pack(fill="x")
        ttk.Label(right, text="Design rules", font=("", 10, "bold")).pack(
            anchor="w", pady=(10, 2))
        self.rules = tk.Text(right, wrap="word", font=("Consolas", 9),
                             relief="flat", background="#ffffff")
        self.rules.pack(fill="both", expand=True)
        for tag, col in (("ok", "#2e7d32"), ("warn", "#ef6c00"),
                         ("fail", "#c62828"), ("dim", "#777777")):
            self.rules.tag_configure(tag, foreground=col)
        self.status = ttk.Label(self, text="", anchor="w", padding=(10, 4))
        self.status.pack(fill="x")

    # ------------------------------------------------------------------
    def collect(self):
        """Pull the widgets into self.frame. Bad numbers are left alone."""
        bad = []
        for path, (v, kind) in self.vars.items():
            raw = v.get()
            try:
                if kind == "b":
                    val = bool(raw)
                elif kind == "i":
                    val = int(float(raw))
                elif kind == "f":
                    val = float(raw)
                else:
                    val = str(raw)
                set_path(self.frame, path, val)
            except (ValueError, TypeError):
                bad.append(path)
        return bad

    def refresh(self, *_):
        bad = self.collect()
        f = self.frame
        try:
            ring = plan_ring(f)
        except Exception as e:
            self.status.config(text=f"cannot plan: {e}")
            return
        from .profile import print_mass
        m = print_mass(f)
        seg = ring.segments[0]

        self.summary.config(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("end",
            f"duct       ID {f.duct_id:7.1f}   OD {f.duct_od:7.1f} inlet / "
            f"{f.duct_od_exit:.1f} exit   chord {f.duct_height:.1f}\n"
            f"lip        R {f.lip_radius:6.1f} mm   "
            f"({f.lip_radius/f.prop.diameter*100:.1f}% of D)\n"
            f"frame      motors {f.motor_spacing:.0f} mm apart, "
            f"{f.motor_diagonal:.0f} diagonal, {f.footprint:.0f} mm square\n"
            f"power      {f.rpm_full:,.0f} rpm full charge, tip Mach {f.tip_mach():.2f}, "
            f"ideal gain x{f.ideal_thrust_gain:.2f}\n"
            f"mass       {m['grams']:.0f} g per ring, {4*m['grams']/1000:.2f} kg "
            f"for four (3 walls / 15%)\n"
            f"\nSPLIT      {ring.count} segments per ring "
            f"({4*ring.count} printed arcs), sweep {seg.sweep_deg:.1f} deg\n"
            f"           {seg.plate_w:.0f} x {seg.plate_h:.0f} x {f.duct_height:.0f} mm, "
            f"rotate {seg.plate_angle:.0f} deg on the plate, "
            f"{seg.utilisation*100:.0f}% of bed  -> "
            f"{'FITS' if ring.fits else 'DOES NOT FIT'}\n")
        self.summary.config(state="disabled")

        self.rules.config(state="normal")
        self.rules.delete("1.0", "end")
        for c in check(f):
            self.rules.insert("end", f"{c.level.upper():5}", c.level)
            self.rules.insert("end", f"{c.label:<24}{c.value:<38}want {c.want}\n")
            if c.note and c.level != "ok":
                self.rules.insert("end", f"     {c.note}\n", "dim")
        for p in plan_other_parts(f, ring):
            if not p.fits:
                self.rules.insert("end",
                    f"FAIL {p.name} is {p.w:.0f} x {p.h:.0f} mm and will not "
                    f"fit this bed\n", "fail")
        self.rules.config(state="disabled")
        self.status.config(text="invalid numbers ignored: " + ", ".join(bad)
                           if bad else "ready")

    # ------------------------------------------------------------------
    def on_printer(self, *_):
        name = self.printer_cb.get()
        spec = self.printers[name]
        self.frame.printer.name = name
        for k, v in spec.items():
            self.vars[f"printer.{k}"][0].set(str(v)) \
                if f"printer.{k}" in self.vars else setattr(self.frame.printer, k, v)
        self.refresh()

    def _sync_widgets(self):
        for path, (v, kind) in self.vars.items():
            v.set(get_path(self.frame, path))
        self.printer_cb.set(self.frame.printer.name)

    def on_load(self):
        p = filedialog.askopenfilename(initialdir=PRESETS, title="Load preset",
                                       filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            self.frame = Frame.from_json(p)
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return
        self._sync_widgets()
        self.refresh()

    def on_save(self):
        self.collect()
        p = filedialog.asksaveasfilename(
            initialdir=PRESETS, initialfile=f"{self.frame.name}.json",
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if p:
            self.frame.to_json(p)
            self.status.config(text=f"saved {p}")

    def _outdir(self):
        d = os.path.join(HERE, "out", self.frame.name)
        os.makedirs(d, exist_ok=True)
        return d

    def on_preview(self):
        self.collect()
        from .preview import render
        p = render(self.frame, os.path.join(self._outdir(), "preview.png"))
        self.status.config(text=f"saved {p}")
        try:
            os.startfile(p)
        except Exception:
            pass

    def on_report(self):
        self.collect()
        from .cli import report
        p = os.path.join(self._outdir(), "report.txt")
        open(p, "w").write(report(self.frame))
        self.status.config(text=f"saved {p}")
        try:
            os.startfile(p)
        except Exception:
            pass

    def on_build(self):
        self.collect()
        self.build_btn.config(state="disabled")
        self.status.config(text="building in SolidWorks, this takes a minute...")

        def work():
            try:
                from .build_sw import build_all, placement_table
                out = self._outdir()
                ring = plan_ring(self.frame)
                made = build_all(self.frame, out, ring=ring)
                json.dump(placement_table(self.frame, ring),
                          open(os.path.join(out, "placement.json"), "w"), indent=2)
                self.frame.to_json(os.path.join(out, "params.json"))
                msg = "  ".join(f"{r['part']} x{r['qty']}" for r in made)
                self.after(0, lambda: self.status.config(
                    text=f"built {msg} -> {out}"))
                self.after(0, lambda: os.startfile(out))
            except Exception as e:
                tb = traceback.format_exc()
                self.after(0, lambda: messagebox.showerror("Build failed", tb))
                self.after(0, lambda: self.status.config(text=f"build failed: {e}"))
            finally:
                self.after(0, lambda: self.build_btn.config(state="normal"))

        threading.Thread(target=work, daemon=True).start()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
