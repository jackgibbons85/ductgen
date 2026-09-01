from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
import math

MM_PER_IN = 25.4
SPEED_OF_SOUND = 343000.0

CARBON = (3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 30)
METRIC = (2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)


def snap(v, table=CARBON):
    return min(table, key=lambda t: (abs(t - v), t))


@dataclass
class Prop:
    diameter_in: float = 13.0
    pitch_in: float = 4.4
    blades: int = 3

    @property
    def diameter(self) -> float:
        return self.diameter_in * MM_PER_IN


@dataclass
class Motor:
    stator: str = "5010"
    body_od: float = 56.0
    body_height: float = 15.0
    shaft_dia: float = 5.0
    kv: int = 380
    cells: int = 6
    bolt_pattern: str = "square"
    bolt_span: float = 25.0
    bolt_count: int = 4
    bolt_size: float = 3.0
    bolt_clearance: float = 0.4
    boss_dia: float = 10.0

    @property
    def hole_dia(self) -> float:
        return self.bolt_size + self.bolt_clearance

    def hole_xy(self):
        if self.bolt_pattern == "square":
            h = self.bolt_span / 2.0
            return [(-h, -h), (h, -h), (h, h), (-h, h)]
        r = self.bolt_span / 2.0
        return [(r * math.cos(2 * math.pi * i / self.bolt_count),
                 r * math.sin(2 * math.pi * i / self.bolt_count))
                for i in range(self.bolt_count)]


@dataclass
class Duct:
    tip_clearance_pct: float = 1.5
    wall: float = 6.0
    rim_land: float = 3.0
    chord_ratio: float = 0.30
    lip_radius_ratio: float = 0.06
    lip_ellipse_ratio: float = 1.8
    diffuser_deg: float = 3.0
    prop_plane_frac: float = 0.28
    trailing_edge_r: float = 1.5
    outer_style: str = "straight"
    od_override: float = 0.0


@dataclass
class Mount:
    hub_od: float = 0.0
    height: float = 0.0
    boss_od: float = 0.0
    boss_wall: float = 2.0
    bore_clearance: float = 0.3
    rod_y_frac: float = 0.5333
    clamp_bolt: float = 3.0
    clamp_bolt_clearance: float = 0.3
    clamp_r: float = 0.0
    reach: float = 0.0
    bore_inner_r: float = 0.0


@dataclass
class Struts:
    count: int = 4
    thickness: float = 5.0
    chord: float = 18.0
    hub_od: float = 66.0
    hub_thickness: float = 6.0
    y_frac: float = 0.55
    tenon_depth: float = 0.0


@dataclass
class Joint:
    kind: str = "half_lap"
    lap_deg: float = 8.0
    lap_height_frac: float = 0.5
    bolts: int = 2
    bolt_size: float = 3.0
    bolt_clearance: float = 0.5
    bolt_edge_margin: float = 4.2
    bolt_head_counterbore: bool = False
    stud: float = 2.5
    stud_depth: float = 0.0


@dataclass
class Printer:
    name: str = "Bambu A1"
    bed_x: float = 256.0
    bed_y: float = 256.0
    bed_z: float = 256.0
    margin: float = 6.0
    allow_diagonal: bool = True
    nozzle: float = 0.4
    layer: float = 0.2


@dataclass
class Connector:
    enabled: bool = True
    outer_offset_ratio: float = 0.025
    inner_offset_ratio: float = 0.310
    pad_width_ratio: float = 0.358
    inner_fillet_ratio: float = 0.13
    fit_to_bed: bool = True
    min_inner_offset_ratio: float = 0.10
    pad_rod_wall: float = 6.0
    corner_fillet: float = 0.0
    inlet_clearance: float = 1.0
    blend_overlap: float = 1.5
    fc_span: float = 30.0
    fc_bolt: float = 3.0


@dataclass
class Center:
    plate_x: float = 0.0
    plate_z: float = 0.0
    plate_y: float = 0.0
    fc_span: float = 30.0
    fc_bolt: float = 3.0
    fc_clearance: float = 0.3
    stack_span: float = 65.0
    stack_bolt: float = 3.0
    stack_counterbore: float = 6.0
    cross_bolt: float = 5.0
    cross_bolt_offset: float = 33.0


@dataclass
class Rods:
    shape: str = "round"
    center_count: int = 2
    center_size: float = 0.0
    center_spacing: float = 0.0
    center_y_frac: float = 0.625

    motor_count: int = 3
    motor_phase: str = "inboard"
    motor_size: float = 0.0
    motor_protrude: float = 9.0
    motor_y_frac: float = 0.20
    motor_inboard: bool = True
    motor_engage: float = 0.0

    outer_count: int = 4
    outer_size: float = 0.0
    outer_overlap: float = 62.3
    outer_inset: float = 5.0
    outer_y_frac: float = 0.55

    clearance: float = 0.25
    bolt: float = 3.0


@dataclass
class Layout:
    duct_gap: float = 0.0
    duct_gap_ratio: float = 0.251
    config: str = "quad_x"
    rod_size: float = 10.0
    rod_socket_clearance: float = 0.25


@dataclass
class Frame:
    name: str = "cinewhoop"
    prop: Prop = field(default_factory=Prop)
    motor: Motor = field(default_factory=Motor)
    duct: Duct = field(default_factory=Duct)
    struts: Struts = field(default_factory=Struts)
    mount: Mount = field(default_factory=Mount)
    joint: Joint = field(default_factory=Joint)
    printer: Printer = field(default_factory=Printer)
    layout: Layout = field(default_factory=Layout)
    connector: Connector = field(default_factory=Connector)
    center: Center = field(default_factory=Center)
    rods: Rods = field(default_factory=Rods)

    @property
    def duct_id(self) -> float:
        return self.prop.diameter * (1.0 + 2.0 * self.duct.tip_clearance_pct / 100.0)

    @property
    def lip_semi_major(self) -> float:
        return self.lip_radius * self.duct.lip_ellipse_ratio

    @property
    def duct_od(self) -> float:
        if self.duct.od_override > 0:
            return self.duct.od_override
        rt = self.throat_radius
        return 2.0 * max(rt + self.duct.wall,
                         rt + self.lip_semi_major + self.duct.rim_land)

    @property
    def connector_corner_fillet(self) -> float:
        return self.connector.corner_fillet or max(3.0, 0.02 * self.duct_od)

    @property
    def max_bore_radius(self) -> float:
        return max(self.throat_radius + self.lip_semi_major,
                   self.exit_radius + self.duct.trailing_edge_r)

    @property
    def duct_od_exit(self) -> float:
        if self.duct.od_override > 0:
            return self.duct.od_override
        if self.duct.outer_style == "straight":
            return self.duct_od
        return 2.0 * (self.exit_radius + self.duct.trailing_edge_r + self.duct.wall)

    @property
    def outer_taper_deg(self) -> float:
        drop = (self.duct_od - self.duct_od_exit) / 2.0
        return math.degrees(math.atan2(drop, self.duct_height))

    @property
    def duct_height(self) -> float:
        return self.duct.chord_ratio * self.prop.diameter

    @property
    def lip_radius(self) -> float:
        return self.duct.lip_radius_ratio * self.prop.diameter

    @property
    def prop_plane_y(self) -> float:
        return self.duct.prop_plane_frac * self.duct_height

    @property
    def throat_radius(self) -> float:
        return self.duct_id / 2.0

    @property
    def exit_radius(self) -> float:
        run = self.duct_height - self.prop_plane_y - self.duct.trailing_edge_r
        return self.throat_radius + max(run, 0.0) * math.tan(math.radians(self.duct.diffuser_deg))

    def outer_radius_at(self, y: float) -> float:
        t = min(max(y / self.duct_height, 0.0), 1.0)
        return (self.duct_od_exit + t * (self.duct_od - self.duct_od_exit)) / 2.0

    @property
    def strut_y(self) -> float:
        return self.duct_height * (1.0 - self.struts.y_frac)

    @property
    def socket_depth(self) -> float:
        avail = self.outer_radius_at(self.strut_y) - self.throat_radius
        keep = max(1.5, 0.25 * avail)
        if self.struts.tenon_depth > 0:
            return min(self.struts.tenon_depth, avail - keep)
        return max(1.5, min(12.0, avail - keep))

    @property
    def connector_outer_offset(self) -> float:
        return self.connector.outer_offset_ratio * self.duct_od

    @property
    def connector_inner_offset(self) -> float:
        return self.connector.inner_offset_ratio * self.duct_od

    @property
    def connector_pad_width(self) -> float:
        return self.connector.pad_width_ratio * self.duct_od

    @property
    def connector_inner_fillet(self) -> float:
        return self.connector.inner_fillet_ratio * self.duct_od

    @property
    def outer_rod(self) -> float:
        return self.rods.outer_size or snap(0.5503 * math.sqrt(self.prop.diameter))

    @property
    def motor_rod(self) -> float:
        return self.rods.motor_size or self.outer_rod

    @property
    def center_rod(self) -> float:
        return self.rods.center_size or snap(2.0 * self.outer_rod)

    @property
    def center_bore_dia(self) -> float:
        return self.center_rod + self.rods.clearance

    @property
    def plate_x(self) -> float:
        return self._plate_xz()[0]

    @property
    def plate_z(self) -> float:
        return self._plate_xz()[1]

    def _plate_xz(self):
        c = self.center
        k = 0.574 * self.center_room / math.hypot(7.0, 6.0)
        px, pz = 14.0 * k, 12.0 * k
        for span, bolt in self.deck_patterns():
            need = span + 2.0 * (bolt + c.fc_clearance) + 6.0
            px, pz = max(px, need), max(pz, need)
        return (c.plate_x or px, c.plate_z or pz)

    @property
    def center_room(self) -> float:
        return self.motor_spacing / 2.0 * math.sqrt(2.0) - self.duct_od / 2.0

    def deck_patterns(self):
        c = self.center
        out = []
        for span, bolt in ((c.fc_span, c.fc_bolt), (c.stack_span, c.stack_bolt)):
            if span <= 0:
                continue
            need = span + 2.0 * (bolt + c.fc_clearance) + 6.0
            if (c.plate_x and c.plate_z) or                     math.hypot(need / 2.0, need * 6.0 / 7.0 / 2.0) <= self.center_room:
                out.append((span, bolt))
        return out

    @property
    def stud_depth(self) -> float:
        if self.joint.stud_depth:
            return self.joint.stud_depth
        half = self.duct_height * min(self.joint.lap_height_frac,
                                      1.0 - self.joint.lap_height_frac)
        return max(1.5, min(2.5 * self.joint.stud, half - 1.5))

    def joint_hole_radii(self):
        em = self.joint.bolt_edge_margin
        rt, ro = self.throat_radius, self.duct_od / 2.0
        n = max(self.joint.bolts, 1)
        if n == 2:
            return [rt + em, ro - em]
        return [rt + em + (ro - rt - 2 * em) * i / max(n - 1, 1)
                for i in range(n)]

    def deck_depth(self) -> float:
        lo, hi = self.center_plate_span()
        pats = self.deck_patterns()
        if not pats:
            return max(0.0, hi - self.center_bore_dia / 2.0 - 1.5)
        r = max((b + self.center.fc_clearance) / 2.0 for _s, b in pats)
        return max(0.0, hi - self.center_bore_dia / 2.0 - r - 1.0)

    def center_plate_span(self):
        w = max(6.0, 0.40 * self.center_bore_dia)
        lo, hi = -self.center_bore_dia / 2.0 - w, self.center_bore_dia / 2.0 + w
        if self.center.plate_y > 0:
            lo, hi = -self.center.plate_y / 2.0, self.center.plate_y / 2.0
        if self.rods.motor_inboard:
            d = self.motor_rod_duct_y - self.duct_height * self.rods.center_y_frac
            lo = min(lo, d - self.mount_bore_dia / 2.0 - w)
        return lo, hi

    @property
    def center_plate_height(self) -> float:
        lo, hi = self.center_plate_span()
        return hi - lo

    @property
    def rod_pad_min_width(self) -> float:
        r = self.rods
        if r.center_count < 1:
            return 0.0
        span = ((r.center_count - 1) * r.center_spacing
                + self.center_rod + r.clearance)
        return span + 2.0 * self.connector.pad_rod_wall

    @property
    def duct_gap(self) -> float:
        if self.layout.duct_gap > 0:
            return self.layout.duct_gap
        return self.layout.duct_gap_ratio * self.duct_od

    @property
    def mount_boss_od(self) -> float:
        return self.mount.boss_od or (self.motor_rod
                                      + 2.0 * self.mount.boss_wall)

    @property
    def mount_hub_od(self) -> float:
        if self.mount.hub_od:
            return self.mount.hub_od
        return max(self.motor.bolt_span * math.sqrt(2.0) + 8.0,
                   self.mount_boss_od + 8.0)

    @property
    def mount_height(self) -> float:
        return self.mount.height or (self.motor_rod + 5.0)

    @property
    def mount_reach(self) -> float:
        return self.mount.reach or max(self.mount_hub_od / 2.0
                                       + 1.25 * self.motor_rod,
                                       self.mount_bore_inner_r
                                       + 1.6 * self.motor_rod)

    @property
    def mount_clamp_r(self) -> float:
        return self.mount.clamp_r or (self.mount_reach
                                      - 0.6 * self.motor_rod)

    @property
    def motor_bolt_phase(self) -> float:
        n = max(self.rods.motor_count, 1)
        arms = [360.0 * i / n for i in range(n)]
        if self.motor.bolt_pattern == "square":
            step, cnt = 90.0, 4
        else:
            step, cnt = 360.0 / max(self.motor.bolt_count, 1), self.motor.bolt_count
        best = (0.0, -1.0)
        for k in range(int(step * 4)):
            ph = k / 4.0
            m = min(abs((ph + step * i - a + 180) % 360 - 180)
                    for i in range(cnt) for a in arms)
            if m > best[1]:
                best = (ph, m)
        return best[0]

    @property
    def motor_bolt_r(self) -> float:
        if self.motor.bolt_pattern == "square":
            return self.motor.bolt_span / 2.0 * math.sqrt(2.0)
        return self.motor.bolt_span / 2.0

    def motor_hole_xy(self):
        a = math.radians(self.motor_bolt_phase)
        c, s = math.cos(a), math.sin(a)
        return [(x * c - y * s, x * s + y * c) for x, y in self.motor.hole_xy()]

    @property
    def mount_bore_inner_r(self) -> float:
        if self.mount.bore_inner_r:
            return self.mount.bore_inner_r
        clr = self.mount_bore_dia / 2.0 + self.motor.hole_dia / 2.0 + 1.0
        n = max(self.rods.motor_count, 1)
        need = self.mount_hub_od / 2.0 * 0.54
        for x, y in self.motor_hole_xy():
            for i in range(n):
                a = math.radians(360.0 * i / n)
                u = x * math.cos(a) + y * math.sin(a)
                p = abs(-x * math.sin(a) + y * math.cos(a))
                if p >= clr or u <= 0.0:
                    continue
                need = max(need, u + math.sqrt(clr * clr - p * p))
        return need

    @property
    def motor_rod_r0(self) -> float:
        return self.mount_bore_inner_r

    @property
    def mount_rod_y(self) -> float:
        return self.mount_height * self.mount.rod_y_frac

    @property
    def mount_bore_dia(self) -> float:
        return self.motor_rod + self.mount.bore_clearance

    @property
    def outer_rod_duct_y(self) -> float:
        return self.duct_height * self.rods.outer_y_frac

    @property
    def motor_rod_duct_y(self) -> float:
        return self.duct_height * self.rods.motor_y_frac + self.mount_rod_y

    @property
    def motor_spacing(self) -> float:
        return self.duct_od + self.duct_gap

    @property
    def motor_diagonal(self) -> float:
        return self.motor_spacing * math.sqrt(2.0)

    @property
    def footprint(self) -> float:
        return self.motor_spacing + self.duct_od

    @property
    def rpm_nominal(self) -> float:
        return self.motor.kv * self.motor.cells * 3.7

    @property
    def rpm_full(self) -> float:
        return self.motor.kv * self.motor.cells * 4.2

    def tip_mach(self, rpm: float | None = None) -> float:
        rpm = self.rpm_full if rpm is None else rpm
        return math.pi * self.prop.diameter * rpm / 60.0 / SPEED_OF_SOUND

    @property
    def disk_area(self) -> float:
        return math.pi * (self.prop.diameter / 2.0) ** 2

    @property
    def expansion_ratio(self) -> float:
        return (self.exit_radius / (self.prop.diameter / 2.0)) ** 2

    @property
    def ideal_thrust_gain(self) -> float:
        return (2.0 * self.expansion_ratio) ** (1.0 / 3.0)

    def to_json(self, path):
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @staticmethod
    def from_json(path) -> "Frame":
        with open(path) as fh:
            d = json.load(fh)
        return Frame.from_dict(d)

    @staticmethod
    def from_dict(d: dict) -> "Frame":
        def block(cls, key):
            import dataclasses
            known = {fld.name for fld in dataclasses.fields(cls)}
            raw = d.get(key) or {}
            return cls(**{k: v for k, v in raw.items() if k in known})

        return Frame(
            name=d.get("name", "cinewhoop"),
            prop=block(Prop, "prop"), motor=block(Motor, "motor"),
            duct=block(Duct, "duct"), struts=block(Struts, "struts"),
            mount=block(Mount, "mount"), joint=block(Joint, "joint"),
            printer=block(Printer, "printer"), layout=block(Layout, "layout"),
            connector=block(Connector, "connector"),
            center=block(Center, "center"), rods=block(Rods, "rods"),
        )


@dataclass
class Check:
    level: str
    label: str
    value: str
    want: str
    note: str = ""


def check(f: Frame) -> list[Check]:
    D = f.prop.diameter
    out: list[Check] = []

    def add(ok, warn, label, value, want, note=""):
        out.append(Check("ok" if ok else ("warn" if warn else "fail"),
                         label, value, want, note))

    lr = f.lip_radius / D * 100
    add(lr >= 5.0, lr >= 3.0, "inlet lip radius",
        f"{f.lip_radius:.1f} mm ({lr:.1f}% of D)", "5-8% of D",
        "A sharp lip separates at the throat and throws away the duct benefit.")

    cr = f.duct.chord_ratio * 100
    add(30 <= cr <= 55, 20 <= cr <= 70, "duct chord",
        f"{f.duct_height:.1f} mm ({cr:.0f}% of D)", "30-50% of D",
        "Too short and the duct cannot turn the flow; too long is weight and drag.")

    pp = f.duct.prop_plane_frac * 100
    add(22 <= pp <= 35, 15 <= pp <= 45, "prop plane depth",
        f"{f.prop_plane_y:.1f} mm ({pp:.0f}% of chord)", "25-30% of chord")

    tc = f.duct.tip_clearance_pct
    add(0.5 <= tc <= 1.5, tc <= 2.5, "tip clearance",
        f"{(f.duct_id - D) / 2:.2f} mm/side ({tc:.2f}% of D)", "0.5-1.5% of D",
        "Tip leakage is the second-biggest loss after the lip.")

    m = f.tip_mach()
    add(m <= 0.60, m <= 0.70, "tip Mach at full charge",
        f"{m:.2f} ({f.rpm_full:,.0f} rpm)", "<= 0.60",
        f"{f.motor.kv} kV x {f.motor.cells}S x 4.2 V.")

    da = f.duct.diffuser_deg
    add(0 <= da <= 5, da <= 8, "diffuser half-angle",
        f"{da:.1f} deg (sigma = {f.expansion_ratio:.2f})", "0-5 deg",
        "Past about 5 deg the diffuser stalls and the expansion is lost.")

    add(f.duct.wall >= 8 * f.printer.nozzle, f.duct.wall >= 4 * f.printer.nozzle,
        "exit wall thickness", f"{f.duct.wall:.1f} mm",
        f">= {8 * f.printer.nozzle:.1f} mm for a {f.printer.nozzle} nozzle")

    lip_driven = f.lip_semi_major + f.duct.rim_land > f.duct.wall
    out.append(Check(
        "ok", "duct OD",
        f"{f.duct_od:.1f} inlet / {f.duct_od_exit:.1f} exit",
        "derived",
        (f"driven by the lip: the bellmouth alone eats {f.lip_semi_major:.1f} mm "
         f"of radius, so the ring is {f.duct_od - (D + 2*f.duct.wall + 2*(f.duct_id-D)/2):.0f} mm "
         "wider than a plain-wall duct would be. That is the price of the inlet."
         if lip_driven else "set by the minimum wall, the lip fits inside it")))

    tp = f.outer_taper_deg
    add(tp <= 45, tp <= 60, "outer skin taper",
        f"{tp:.1f} deg from vertical", "<= 45 deg printed inlet-up",
        "Past 45 deg the outer skin needs support even in the good orientation.")

    edge = f.joint.bolt_edge_margin - (f.joint.bolt_size + f.joint.bolt_clearance) / 2
    add(edge >= 2.0, edge >= 1.2, "joint bolt edge distance",
        f"{edge:.2f} mm of material left", ">= 2.0 mm")

    from .clash import report as _mrep, plate_report as _prep
    bad = _mrep(f) + _prep(f)
    add(not bad, False, "hole clashes",
        "none" if not bad else f"{len(bad)}: {bad[0]}",
        "no two holes overlap",
        "" if not bad else "Two features derived from different rules have "
        "landed on top of each other. ductgen.clash lists them all.")

    from .profile import print_mass
    g = print_mass(f)["grams"]
    add(4 * g <= 900, 4 * g <= 1600, "printed duct mass",
        f"{g:.0f} g/ring, {4*g/1000:.2f} kg for four", "<= 0.9 kg total",
        "3 walls / 10% infill in PLA. A properly rounded lip is a lot of "
        "structure, this is the number that decides whether the duct is "
        "worth carrying at all at this prop size.")

    return out
