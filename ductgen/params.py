"""Parameter model for the ducted-frame generator.

All lengths are millimetres and all angles degrees unless a name says otherwise.

Defaults are the values measured off Drone2 (the reference build) by the
scripts in analysis/ -- see REFERENCE.md for how each number was obtained.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
import math

MM_PER_IN = 25.4
SPEED_OF_SOUND = 343000.0   # mm/s at 20 C, sea level


# --------------------------------------------------------------------------
# input blocks
# --------------------------------------------------------------------------
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
    """stator is the usual 4-digit code, e.g. 5010 = 50 mm dia, 10 mm tall."""
    stator: str = "5010"
    body_od: float = 56.0          # measured: Part10 outer body
    body_height: float = 15.0      # measured
    shaft_dia: float = 5.0
    kv: int = 380
    cells: int = 6                 # LiPo S count
    bolt_pattern: str = "square"   # square | circle
    bolt_span: float = 25.0        # square side, or bolt-circle dia if pattern=circle
    bolt_count: int = 4
    bolt_size: float = 3.0         # M3
    bolt_clearance: float = 0.4    # -> 3.4 hole (measured 3.30-3.40 on Part10)
    boss_dia: float = 10.0         # centre relief for the bell / shaft nut

    @property
    def hole_dia(self) -> float:
        return self.bolt_size + self.bolt_clearance

    def hole_xy(self):
        """Bolt hole centres in the motor's own frame."""
        if self.bolt_pattern == "square":
            h = self.bolt_span / 2.0
            return [(-h, -h), (h, -h), (h, h), (-h, h)]
        r = self.bolt_span / 2.0
        return [(r * math.cos(2 * math.pi * i / self.bolt_count),
                 r * math.sin(2 * math.pi * i / self.bolt_count))
                for i in range(self.bolt_count)]


@dataclass
class Duct:
    """Duct cross-section. Ratios are of prop diameter, so the aerodynamic
    shape scales with the prop instead of being redrawn by hand."""
    tip_clearance_pct: float = 1.5      # per side, % of prop diameter
    wall: float = 6.0                   # MINIMUM wall, measured at the exit lip
    rim_land: float = 3.0               # flat annulus outboard of the lip tangent
    chord_ratio: float = 0.30           # duct height / prop dia. Reference = 0.118
    lip_radius_ratio: float = 0.06      # inlet lip radius / prop dia. Reference = 0.007
    lip_ellipse_ratio: float = 1.8      # major/minor axis of the bellmouth ellipse
    diffuser_deg: float = 3.0           # exit half-angle, 0 = straight duct
    prop_plane_frac: float = 0.28       # prop plane depth below inlet lip, / chord
    trailing_edge_r: float = 1.5        # round on the exit lip
    od_override: float = 0.0            # >0 forces a straight outer skin at
                                        # this OD, for reproducing an existing
                                        # frame rather than deriving one


@dataclass
class Struts:
    """Stators that carry the motor hub off the duct wall."""
    count: int = 4
    thickness: float = 5.0
    chord: float = 18.0
    hub_od: float = 66.0                # measured Part10 mount plate ~66-67
    hub_thickness: float = 6.0
    y_frac: float = 0.55                # strut mid-plane, fraction of chord from inlet
    tenon_depth: float = 0.0            # radial engagement into the duct wall;
                                        # 0 = derive it from the wall available
                                        # at the strut height


@dataclass
class Joint:
    """How a ring goes back together after it is split for the bed."""
    kind: str = "half_lap"              # half_lap | dovetail | butt_pin
    lap_deg: float = 8.0                # measured 8.0 deg of arc overlap
    lap_height_frac: float = 0.5        # measured: split at mid-height
    bolts: int = 2                      # measured 2 per joint
    bolt_size: float = 3.0
    bolt_clearance: float = 0.5         # measured hole 3.50 for M3
    bolt_edge_margin: float = 4.2       # measured 4.4 / 3.9 from the two wall faces
    bolt_head_counterbore: bool = False


@dataclass
class Printer:
    name: str = "Bambu A1"
    bed_x: float = 256.0
    bed_y: float = 256.0
    bed_z: float = 256.0
    margin: float = 6.0                 # keep-out from the bed edge
    allow_diagonal: bool = True         # rotate the part on the plate to fit
    nozzle: float = 0.4
    layer: float = 0.2


@dataclass
class Layout:
    duct_gap: float = 30.0              # clear gap between neighbouring duct ODs (ref build: 99.3)
    config: str = "quad_x"              # quad_x only, for now
    rod_size: float = 10.0              # square carbon rod across flats (measured 10.0)
    rod_socket_clearance: float = 0.25


@dataclass
class Frame:
    name: str = "cinewhoop"
    prop: Prop = field(default_factory=Prop)
    motor: Motor = field(default_factory=Motor)
    duct: Duct = field(default_factory=Duct)
    struts: Struts = field(default_factory=Struts)
    joint: Joint = field(default_factory=Joint)
    printer: Printer = field(default_factory=Printer)
    layout: Layout = field(default_factory=Layout)

    # ---------------- derived geometry ----------------
    @property
    def duct_id(self) -> float:
        return self.prop.diameter * (1.0 + 2.0 * self.duct.tip_clearance_pct / 100.0)

    @property
    def lip_semi_major(self) -> float:
        """Radial reach of the bellmouth quadrant, inboard face to top face."""
        return self.lip_radius * self.duct.lip_ellipse_ratio

    @property
    def duct_od(self) -> float:
        """Outer diameter at the inlet face -- the widest point of the ring.

        A bellmouth of semi-major axis `a` eats `a` millimetres of wall before
        any structure is left, so the OD is driven by whichever is larger: the
        minimum structural wall, or the lip plus its rim land.  Asking for a
        6%-of-D lip inside a thin wall is the one input that silently produces
        a self-intersecting section, so it is resolved here instead.
        """
        if self.duct.od_override > 0:
            return self.duct.od_override
        rt = self.throat_radius
        return 2.0 * max(rt + self.duct.wall,
                         rt + self.lip_semi_major + self.duct.rim_land)

    @property
    def duct_od_exit(self) -> float:
        """Outer diameter at the exit face. The outer skin tapers between the two."""
        if self.duct.od_override > 0:
            return self.duct.od_override
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
        """Depth of the prop plane below the inlet face."""
        return self.duct.prop_plane_frac * self.duct_height

    @property
    def throat_radius(self) -> float:
        return self.duct_id / 2.0

    @property
    def exit_radius(self) -> float:
        run = self.duct_height - self.prop_plane_y - self.duct.trailing_edge_r
        return self.throat_radius + max(run, 0.0) * math.tan(math.radians(self.duct.diffuser_deg))

    def outer_radius_at(self, y: float) -> float:
        """Outer radius of the duct at height y above the exit face."""
        t = min(max(y / self.duct_height, 0.0), 1.0)
        return (self.duct_od_exit + t * (self.duct_od - self.duct_od_exit)) / 2.0

    @property
    def strut_y(self) -> float:
        """Height of the strut mid-plane above the exit face."""
        return self.duct_height * (1.0 - self.struts.y_frac)

    @property
    def socket_depth(self) -> float:
        """How far the strut tenon reaches into the duct wall.

        Capped so a minimum ligament survives -- a fixed depth punches straight
        through the wall once the prop gets small.
        """
        avail = self.outer_radius_at(self.strut_y) - self.throat_radius
        keep = max(1.5, 0.25 * avail)
        if self.struts.tenon_depth > 0:
            return min(self.struts.tenon_depth, avail - keep)
        return max(1.5, min(12.0, avail - keep))

    @property
    def motor_spacing(self) -> float:
        """Centre-to-centre along one side of the square."""
        return self.duct_od + self.layout.duct_gap

    @property
    def motor_diagonal(self) -> float:
        return self.motor_spacing * math.sqrt(2.0)

    @property
    def footprint(self) -> float:
        return self.motor_spacing + self.duct_od

    # ---------------- derived performance ----------------
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
        """Exit area / disk area. Drives the ideal ducted thrust gain."""
        return (self.exit_radius / (self.prop.diameter / 2.0)) ** 2

    @property
    def ideal_thrust_gain(self) -> float:
        """(2*sigma)^(1/3): static thrust of a shrouded rotor against the same
        rotor open, at equal shaft power. Only realised if the inlet stays
        attached -- a sharp lip collects none of it."""
        return (2.0 * self.expansion_ratio) ** (1.0 / 3.0)

    # ---------------- io ----------------
    def to_json(self, path):
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @staticmethod
    def from_json(path) -> "Frame":
        with open(path) as fh:
            d = json.load(fh)
        return Frame(
            name=d.get("name", "cinewhoop"),
            prop=Prop(**d["prop"]), motor=Motor(**d["motor"]),
            duct=Duct(**d["duct"]), struts=Struts(**d["struts"]),
            joint=Joint(**d["joint"]), printer=Printer(**d["printer"]),
            layout=Layout(**d["layout"]),
        )


# --------------------------------------------------------------------------
# design rules -- this is what makes the inputs mean something
# --------------------------------------------------------------------------
@dataclass
class Check:
    level: str      # ok | warn | fail
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
        f"{f.duct_od:.1f} mm at the inlet, {f.duct_od_exit:.1f} mm at the exit",
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

    from .profile import print_mass          # local: profile imports params
    g = print_mass(f)["grams"]
    add(4 * g <= 900, 4 * g <= 1600, "printed duct mass",
        f"{g:.0f} g/ring, {4*g/1000:.2f} kg for four", "<= 0.9 kg total",
        "3 walls / 15% infill in PLA. A properly rounded lip is a lot of "
        "structure -- this is the number that decides whether the duct is "
        "worth carrying at all at this prop size.")

    return out
