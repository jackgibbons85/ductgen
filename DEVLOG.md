# how this got built

A record of the order things were done in, and the things that went wrong.
Kept because most of the hard parts were undocumented SolidWorks API
behaviour, and re-deriving them a second time would be miserable.

## the order of work

### 1. measure the drone that already exists

Nothing was designed from a blank sheet. The starting point was an STL export
of the hand-built 13" frame, and the first job was getting real numbers out of
it. That meant writing the reading tools first:

* `analysis/stlread.py`, a binary STL reader. Bounding box, signed volume via
  the divergence theorem, surface area.
* `analysis/components.py`, splits one mesh into separate solid bodies. Welds
  vertices onto a tolerance grid, then union-find over shared vertices. This
  is what turned a single 157k-triangle file into 19 labelled bodies.
* `analysis/section.py`, plane-slices a mesh and reports radius and angle
  clusters about a given axis.
* `analysis/holes.py`, finds cylindrical faces by grouping facets whose
  normals are horizontal, then least-squares fits a circle to each group.
* `analysis/span.py`, angular span and radial range of each part about its
  own motor axis.

What came out of that is in `REFERENCE.md`: throat 340.0, OD 380.0, chord
40.0, motor spacing 475.45, inlet lip radius 2.3 mm, half-lap joints at
mid-height with two M3 each, a 30.5 mm FC pattern, 22.3 mm centre rods.

The lip radius is the number that justified the whole project. 2.3 mm on a
330 mm prop is 0.7% of diameter, against 5 to 10% in the static ducted-fan
literature. That one measurement is why the generator derives the section
from ratios instead of letting anyone draw a rectangle.

### 2. parameter model and design rules

`ductgen/params.py`. Dataclasses for prop, motor, duct, mount, joint,
printer, connector, centre plate, rods. Then the derived properties that make
the inputs mean something rather than just resize a sketch:

* prop diameter and tip clearance give the throat, and chord, lip radius and
  prop-plane depth all scale off diameter
* kV times cells times cell voltage gives rpm, which gives tip Mach
* diffuser angle gives the exit area ratio sigma, which gives the ideal
  static thrust gain (2*sigma)^(1/3)
* the section plus the printer settings gives an actual mass estimate

`check()` grades every one of those against a range and returns ok, warn or
fail. Running it on the as-built preset fails three rows by construction,
which is the point.

### 3. the duct section

`ductgen/profile.py`. One definition of the meridian, emitted as lines, arcs
and splines rather than a dense polyline, so SolidWorks gets real geometry.
The preview renderer and the CAD builder both read this same function, so the
PNG is guaranteed to be what gets revolved.

### 4. splitting for the bed

`ductgen/segment.py`. Tests the arc sector at every in-plane rotation, since a
256 mm bed will take a 345 mm part on the diagonal, and picks the smallest
segment count that fits.

### 5. driving SolidWorks

`ductgen/swapi.py` wraps the COM API: unit conversion in one place, plane
lookup by walking the feature tree rather than by hard-coded name, and the
early-binding setup. `ductgen/build_sw.py` and `build_parts.py` do the actual
part building.

### 6. the connector

`ductgen/bridge.py`. The mid part that bridges a duct pair, solved as arcs
tangent to both rings so the ducts blend into it instead of butting against
it. Tangency to a circle from an offset line is a linear equation once
squared, so the edge positions come out closed-form rather than iterated.

### 7. assembly

`ductgen/build_asm.py` places every component with an explicit transform
derived from the same layout functions the cut list and previews use.

### 8. verification

Two harnesses, because unit tests cannot catch a part that is individually
correct but placed wrongly:

* `tests/test_geometry.py`, 15 invariants that need no CAD at all. The
  section never self-intersects, the lip always fits the wall, segments plus
  the connector interface account for exactly 360 degrees, a smaller bed never
  yields fewer segments, every rod either gets a bore or is in the connector
  arc.
* `analysis/verify_assembly.py`, measures the exported assembly STL. Ring
  closure at six heights, connector-to-duct contact, wall verticality, every
  rod bore present, mount arms equally spaced.

---

## things that went wrong

### the ring was open by exactly the lap angle

The worst one, because every part passed inspection on its own.

Slicing the assembly showed a gap of 7.88 degrees, and the lap is 8 degrees,
which was the clue. Slicing at two heights located it exactly: at 25% height
the arc 165.75 to 173.50 was empty, at 75% height the arc 208.12 to 215.88
was empty. Both are lap zones, and each was empty in only one half.

So both mating parts were putting their tab on the same side of the joint.
Measuring the built parts rather than trusting the code:

| junction | connector tab | segment tab | result |
|---|---|---|---|
| low-angle end | upper | upper | lower half empty |
| high-angle end | lower | lower | upper half empty |

The comment in the connector claimed segments present an upper tab at the
low-angle end. The parts said the opposite. Segments mate correctly with each
other, so the connector was the one to flip. After that the largest gap at any
height is 0.12 degrees, which is mesh resolution.

Lesson: the fix was one boolean, and finding it took measuring the actual
exported geometry instead of reading the code.

### the mount arms were not 120 degrees apart

Reported as "the circular pattern of the extruded holes are not equidistant".
Measured: arms at 0, 60 and 120 instead of 0, 120 and 240.

`FeatureCircularPattern5` reads its angle argument as the TOTAL span when
`EqualSpacing` is true, not as the per-instance step. Asking for 120 with
three instances spreads them across the first third of the circle. Passing 360
gives the real thing. Spacing error is now 0.0 degrees.

### the mount bores were drilled backwards into the hub

Same part, found while checking the first fix. The generated mount was 15.64
cm3 against a measured 13.55, that is, too heavy, so material was not being
removed.

Scanning the slice found the bore at x = -14 to -17: it had been cut inward
through the hub instead of outward along the arm. A cut feature's direction
flag is not the same convention as an extrude's, even with the same argument.

Volume could not tell the two cases apart, since boring the hub removes about
as much as boring the arm. Centre of mass could: the arm sits at +x, so boring
it moves the centroid toward -x and boring the hub moves it +x. The build now
probes that and flips if needed. Result 13.4 cm3 against the measured 13.55.

Because all three bores are cut from the axis outward, they also met in the
middle and hollowed the hub, so a solid plug is now added back after
patterning.

### the side rod bores cut nothing at all

Two separate causes stacked.

First, the planner was throwing them away. It refused any bore within a full
lap width of a segment end. At eight segments that window excluded most of
each segment, so every perimeter rod was silently dropped as unplaced. The
right window is the segment's exclusive span, half a lap at each end, shrunk
by the bore's own angular half width. That alone took placement from 8 of 20
to 16 of 20 with zero collisions.

Second, the two vertical sketch planes are not interchangeable, and I had them
swapped. Probed rather than assumed:

| plane | sketch (A,B) maps to | cut runs along |
|---|---|---|
| Front | x=A, y=B | Z |
| Right | z=-A, y=B | X |

A motor rod leaves the hub radially, so its bore runs along X and belongs on
the Right plane. A perimeter rod crosses the wall as a chord, tangentially, so
its bore runs along Z and belongs on the Front plane at the crossing radius. I
had it on Right, which put it at z = -198.71 where the segment has no material,
so it quietly cut nothing. The volumes agreed: the variant was 3 cm3 lighter
instead of the 10.5 a real chord bore removes.

Measured after the fix: bore walls at x = 193.59 and 203.84, that is 10.25
diameter centred on 198.71, exactly outer rod plus clearance.

### the connector web reached into the inlet

The straight run between the two tangency points is a chord of the ring, and a
chord sinks inside the circle it spans by Ro*(1 - cos(interface/2)). On the
short-chord preset that put it 15 mm inside a 170 mm throat, right in the
inlet path.

Fixed by clipping the web outline against a keep-out circle. The subtlety is
which radius: not the throat, but the widest the bore ever gets over the whole
duct height, because the bellmouth opens out to throat plus the lip semi-major
at the inlet face and the web is extruded full height.

First attempt pushed offending points radially outward, which was simpler and
folded any rounded corner it caught, showing up as 180 degree cusps and
self-intersections. Proper clipping, delete the inside run and splice in a
real arc, keeps the polygon a polygon.

### the assembly was rotating parts the wrong way

Every part was correct and the whole frame was subtly wrong. Diagnosed by
fingerprinting: the joint bolt holes give an absolute angular signature, so
comparing their measured angles against the plan showed a constant -4.04
degree offset on all but one.

SolidWorks applies MathTransforms to row vectors, so the rotation block in the
16-double array is the transpose of the usual column-vector matrix. After
transposing, the offset is -0.01 degrees.

### the reference plane that will not exist

The mount needs arms at angles no base plane reaches. The obvious route is a
reference plane at an angle through the vertical axis, and `InsertRefPlane`
returns None for it, in every combination of selection order and constraint
flags tried. Creating the axis works, selecting it works, the plane does not.

Two workarounds, both in use:

* the mount builds one arm along +x and circular-patterns it about a created
  axis
* a duct segment that carries a bore is revolved asymmetrically, which swings
  the part under the fixed plane instead of swinging a plane under the part

### fixed dimensions that did not scale

Two of these. The strut socket had a fixed 10 mm depth, which punched clean
through the wall on the 3.5" preset. The motor mount had absolute sizes, so a
35 mm hub sat inside a 113 mm duct.

Both now derive. The mount rules were fitted to the measured mount and
reproduce it exactly:

| | boss | hub | height | reach | clamp r | bore r |
|---|---|---|---|---|---|---|
| derived, 19 mm bolt pattern | 14.00 | 35.00 | 15.00 | 30.00 | 24.00 | 9.50 |
| measured from the real part | 14.00 | 35.00 | 15.00 | 30.00 | 24.00 | 9.50 |
| derived, 3.5" build | 8.00 | 24.97 | 9.00 | 17.49 | 15.09 | 6.74 |

### undocumented API signatures

Collected here so they cost time once:

* late-bound COM turns SolidWorks methods into properties, `doc.GetTitle`
  returns a string instead of being callable. Everything goes through
  makepy-generated wrappers now, registered on first run.
* the generated wrappers need the underlying PyIDispatch, not the CDispatch
  that win32com hands back, so there is one unwrap helper
* `swDefaultTemplatePart` is 8, not 0
* `FeatureCut4` takes 27 arguments in 2025, not the 24 in most published
  examples. The extra three are T0, StartOffset, FlipStartOffset
* `InsertRefPlane` returns an IRefPlane, and ISketch has no name at all, so
  both names come from `FeatureByPositionReverse(0)`
* `SaveAs3` has Errors and Warnings as in/out parameters, they must be passed
  in as well as read back
* `swSTLDontTranslateToPositive` has to be set or the exporter shifts every
  part into the positive octant and throws away the placement
* `swSTLShowInfoOnSave` has to be off or a modal dialog hangs the whole run

### text encoding, twice

Writing UTF-8 content through Python's default encoding on Windows produced
mojibake in the source. Repairing it in text mode then converted every CRLF
into CRCRLF, which reads back as a blank line between every line of the file,
doubling params.py from 558 to 1115 lines. Fixed by normalising line endings
in binary and keeping source ASCII only.

---

### the chord problem (2026-08-27)

Three related failures, all found by looking at the built frame rather than
the plan:

* **A perimeter rod crosses the wall as a chord, not a point.** The planner
  gave each side rod one bore in the nearest segment; on the 13" frame the
  chord subtends ±17.8° of ring against a 36° segment, so it nearly always
  continues past a joint into the neighbour, which stayed solid - 258 mm of
  un-drilled wall across the frame, measured by ray-casting the assembly STL
  along the rod lines. `rod_segment_plan` now returns a role per row:
  "main" (bore + clamp + the asymmetric revolve) and "thru" (any other
  segment the chord passes through). A thru cut can sit at an angle the
  revolve cannot reach, so `build_segment` rotates the whole BODY under the
  fixed plane with `InsertMoveCopyBody2`, cuts, and rotates back - the same
  dodge as the asymmetric revolve, one level up. The cut asserts it removed
  material, so a plan/build disagreement fails loudly.
  (`InsertMoveCopyBody2` has a 4th `TransDist` argument the docs bury;
  eleven arguments is a bare "Type mismatch".)
* **The phase nudge never worked.** plan_ring rotated the split a few
  degrees to keep two rods out of one segment - but the connector's gap is
  fixed by tangency, so the rotated ring opened a wedge on one side of the
  gap and double-stacked the other. Any preset that settled on a nonzero
  phase generated a broken ring. Removed: the split always starts at the
  interface edge, and a genuine collision now just costs a variant, since
  the body-rotate path can drill a second rod in the same part.
* **The connector's rod bolts clamped nothing.** Four per rod, straddling
  the tube to spare the carbon - but the pad is one solid piece with a
  closed bore, so all eight passed through plain plastic. Now two per rod ON
  the centreline, drilled through the tube, which is exactly what the
  reference build's plate (bgaw.STL, z = ±33) does. Same for the centre
  plate, which already did it - the same tube was being clamped two
  different ways in one airframe.

And one plain bug: the centre plate was modelled about its mid-height with
the rod measured from there, which only worked because plate_y defaulted to
the full duct chord (a 1.55 litre brick). Any explicit height sketched the
sockets off the part and the cut silently removed nothing. The plate is now
modelled ON the rod axis, sized bore + 2 walls (the reference plate's 40 mm
over a 22 mm tube), with the reference plate's belly channel, and placed at
the rod height in the assembly.

## what is still open

* ~~one motor rod per duct lands inside the connector's arc, so the connector
  has to carry those four bores.~~ Fixed, see below.
* a side-rod crossing whose foot lands in a lap gets pass-through cuts in
  both neighbours but no clamp screw, since neither part owns it.
* the segmentation is driven by bed fit and then checked for rod collisions.
  Driving it from the rod angles instead, putting joints midway between rod
  crossings, would put every rod at a segment centre by construction and
  collapse the variant count to three shapes.

---

## the build123d backend

Added second so the repo runs without a SolidWorks seat. `swapi.py`,
`build_sw.py`, `build_parts.py` and `build_asm.py` were the only files that
imported COM, about 1,540 lines against 2,100 of planning that never touched
CAD, so a second backend was additive rather than a rewrite.

Two things had to move first. `variant_key`, `instances` and
`placement_table` lived in `build_asm.py`, which imports `swapi`, so a
CAD-free backend could not reach them. They are pure planning and now live in
`layout3d.py`, re-exported from their old home. That also makes the claim
"the planning layer needs no CAD" literally true instead of nearly true: it
now emits all 61 assembly components in a venv with no pywin32 installed.

What the new backend does NOT need, which is most of what shaped `build_sw`:

* no asymmetric revolve and no Move Body dance. `Plane(origin, z_dir)`
  reaches any angle, so a bore is one placed cylinder wherever the rod is.
* no runtime sign probes. `revolve()` sweeps from the profile toward
  +revolution_arc and booleans are explicit.

### two bugs volume could not catch

Both were found by comparing against SolidWorks part for part, and neither
would have shown up in a volume check, because volume survives both a mirror
and a rotation.

* **Laps on the wrong ends.** Segment volumes agreed to 0.01 % while the
  combo variant was out by 1.42 cm3. Slicing both meshes at five heights
  showed the theta ranges were exact mirrors: a segment must present a LOWER
  tab at its low-angle end and an UPPER tab at its high-angle end, and mine
  had it backwards. That is the "ring will not close" failure, and the
  connector half-laps had to flip with it.
* **The part handed over in the wrong frame.** `instances()` places a segment
  at `mid + off + phi`, which is only right if the part carries a `-phi`
  offset itself, the way `build_sw`'s asymmetric revolve leaves it. Building
  mid-on-+X and placing with the shared table rotated every rod-carrying
  segment an extra phi and left a 13.25 deg hole in all four rings, uniform
  at every height.

The acceptance check is ring closure measured off the exported assembly, the
same one `analysis/verify_assembly.py` applies to the SolidWorks output.
Worst gap is now 0.38 deg, which is tessellation against a 1.0 deg tolerance.

### and one in the check itself

The first version of that test reported a *perfectly* closed ring as 360 deg
open. With every angular bin occupied the run-length scan finds no runs at
all, and the fallback said 360. A stray tessellation gap at 2 % of chord hid
it; at 30 %, where the ring was flawless, it fired. Empty runs means zero gap.
A wall with no material still reports 360, because the scan opens a run at
bin 0.

---

## interference hunt

Ring closure says the ring is whole. It says nothing about whether the carbon
can actually get through it, so the next check assembled everything EXCEPT the
rods and fired a ray down each rod axis and around its cross-section. Four
real defects came out, two of them in geometry both backends shared.

### a bore that straddles the lap plane

`rod_segment_plan` decided which segment owns the material a bore passes
through from a single up/down flag taken off the bore's CENTRE. A bore is a
cylinder. The as-built frame puts a motor bore 4 mm under the lap plane with a
5.15 mm radius, so it pokes 1.15 mm above it, and the material above the lap
plane belongs to the NEIGHBOURING segment. That neighbour got no cut, and the
tube drove into 11.4 mm of solid wall.

Fixed by testing the bore's vertical extent against the lap plane and checking
both material spans when it straddles. Shared planning code, so both backends
got it. It also raised the variant count on two presets, which is the honest
cost: cinewhoop 17 -> 18 parts, as-built 19 -> 20.

### the connector drilled no motor bores at all

Two separate consequences, one fix:

* a rod whose angle falls inside the interface arc gets no segment bore
  because there is no segment there. This was the top open item above.
* even a rod the segments do bore keeps going, and the tip protruding past
  the duct OD ran into the web.

Cutting along the rod's own axis removes exactly the space the tube occupies.
In build123d that is one placed cylinder. SolidWorks needed three new pieces:

* `_rotate_by` compared a measurement wrapped into [-180, 180) against an
  unwrapped target, so any |delta| over 180 could never match. Segment bores
  only ever ask for a few degrees; the connector's swing to +/-255 exposed it.
* a cut that removes nothing is an error in SolidWorks, not a no-op, so an
  unconditional loop died on the first rod that misses the part. Only rods
  that actually meet the stub wall or the web are drilled now.
* through-all drilled the line's BACKWARD extension too and punched a
  spurious hole out of the far side. Offsetting a sketch plane needs a sign
  convention nothing documents, so `move_bodies` gained a translation and the
  stub centre is slid onto the Front plane instead; `cut_front_reverse()`
  probes the remaining direction the same way `cut_up_reverse` does.

Both backends now pass rod clearance on every preset.

### four bugs in the measuring, not the model

Worth recording because each one pointed at healthy geometry and cost real
time before being caught:

* the run-length gap scan reported a PERFECTLY closed ring as 360 deg open.
  With every angular bin occupied there are no runs, and the fallback said
  360. A stray tessellation gap hid it at 2 % of chord and it fired at 30 %
  where the ring was flawless.
* sampling exactly on the lap plane finds nothing. The half-lap shelf is a
  horizontal face lying in it, and a slicer that only counts triangles
  strictly straddling the plane sees none of it. Whether it fired came down
  to tessellation, so it looked like a real 12 deg hole on one preset only.
* converting ray parameter to rod-relative distance with an extra `- half`
  dragged the mount's solid hub core into the rod's span.
* enter/exit alternation breaks on a rod ray, which runs down a bore's axis
  of symmetry, strikes the tessellated end caps on their shared edges, and
  gets every crossing back twice. Depth counting on the face normal is immune
  to that and to parts whose surfaces touch.

### also

The split note quoted a "nearest joint-to-strut clearance" for vanes nothing
builds any more. The phase search that used it went when the connector's gap
turned out to be fixed by tangency; the line went too.

---

## the arms that reached nothing

Three bugs and one design change, all from looking at where the carbon
actually goes.

### motor rods placed a hub-radius too far in

`instances()` put each motor rod's midpoint at radius `L/2` from the duct
centre. The rod spans `[hub, hub+L]`, so its midpoint is at `hub + L/2`.
Every motor rod in the assembly sat 17.4 mm too far inboard: its inner end
buried in the mount hub, its tip landing at r=200.3 against a 208.7 duct OD,
so it never protruded at all. The bores were always right, only the tubes
were misplaced, which is why nothing failed until the assembly was looked at.

Fixing it immediately broke the ring-closure check, for a good reason: while
the rods sat too far in, their END CAPS fell inside the wall band and masked
their own bores. With the rods correct the bore reads as what it is, a hole,
so the check now skips heights that run through a rod bore. verify_assembly
has always done exactly that.

### the inboard arm ended in mid air

One arm per hub points at the machine centre. Extended, at its own height it
meets nothing until r=729, well past the far duct: it flies over the centre
plate, because the motor rods sit at 20 % of chord and the spine at 62 %,
34 mm apart on the 13 inch frame. So it was a cantilever off the duct ring
with nothing at the far end.

It now runs into the centre plate and is bolted there. Nothing else could
make the two meet, since a tube is straight and both heights are fixed by
what they pass through at the duct, so the plate reaches DOWN to it and is no
longer symmetric about the spine. `center_plate_height` became
`center_plate_span()` for that reason.

That is not free. On the 13 inch frame the plate goes 40.6 mm to 68.6 mm
tall. Coring out the slab under the belly channel, which exists only to catch
four rods near the edges, brings it back from 844 cm3 to 666 against 438
before. The cheap alternative is to move `motor_y_frac` up so the arms are
already at the spine height, which costs nothing at all, and `motor_inboard:
false` turns the whole thing off.

### the connector drilled bores and gave them no screws

A bore holds a tube in two axes; the screw is what stops it sliding out.
Segments have always fitted one over the rod they own. The connector, once it
started drilling rod bores, fitted none. It does now, wherever the stub is
actually kept.

### the two backends diverged on one nested `if`

The plate's centre core-out sat inside the spine-channel guard in SolidWorks
and outside it in build123d. On a frame whose spine rods sit close together
the guard is false, so SolidWorks kept 6.7 cm3 that build123d removed: 38.04
against 31.49. The core has nothing to do with the channel's width. They now
agree to the digit, 31.492 both.

---

## nothing scaled, and the holes were on top of each other

### nothing scaled

A 3 inch frame and a 16 inch frame both got 22.3 mm centre rods, 10 mm arms,
a 43.4 mm hub and M3 clamps, while the duct OD went 101 to 512. Every rod
size and every plate dimension was a frozen number in the dataclass.

Rods now derive from the prop and snap onto a catalogue of tubes you can
actually order, because a rod derived as 5.3249 mm is useless. They go as
roughly the square root of the prop rather than linearly, since bending
stiffness is what they carry: a linear rule gives a 5 inch frame a 3.8 mm
arm where it wants 6. Anchored on the reference build, so 13 inch lands
exactly on 10 mm arms and a 20 mm spine, and 5 inch on 6 and 12. An explicit
size still wins, so the measured presets stay measured.

The centre plate was worse: a fixed 140 x 120 is WIDER THAN THE AIRCRAFT on a
3 inch frame, where the four rings close to within 39 mm of the centre and
the plate's own half-diagonal is 92. It now scales with that clear room,
holding the reference proportion, and reproduces 140 x 120 at 13 inch. The
65 mm stack pattern is a real product and does not scale, so instead it gets
dropped on frames with no room for it rather than being drawn through a duct.

### ductgen/clash.py

Every hole here comes from a different rule: the tube bore from the rod, the
bolt pattern from the motor, the clamp screw from the arm reach, the spine
from the connector pad. Nothing forced them to agree and nothing checked.

So: segment-to-segment distance between hole axes against the sum of the
radii, with a whitelist for the pairs meant to intersect (a clamp screw and
the tube it pins). It treats a hole as a capsule, which is conservative at
the ends, so clearances are sized to satisfy it rather than to argue with it.
Wired into check() as a design rule, so a clash shows up in the report.

What it found, on EVERY preset and every prop size from 3 to 20 inch:

* **motor bolts breaking into the tube sockets**, 3.4 mm of overlap at 13
  inch. No rotation fixes this: a 19 mm bolt span needs 31 deg of clearance
  from a 10.3 mm bore and three arms at 120 can only ever give 15. The bolt
  circle would have to be 26.5 mm where the motor has 13.4. The socket now
  starts OUTSIDE the bolt circle, solved per bolt per arm, which is where a
  real mount seats the tube anyway. The pattern still takes the best phase
  going free, and `mount_reach` grew so the tube keeps its grip.
* **flight-controller bolts drilled straight through the spine tubes.** No
  spine spacing fixes it either: a 65 mm pattern needs the tubes outside 95
  mm and the connector pad only reaches 85.7. They are blind into the top
  deck now, which is how a real plate takes an FC.
* **the inboard arm's clamp screw landing on a spine tube**, and on the deck
  pattern. It walks the engaged length for a spot that clears both.
* **the spine cross bolts landing on the FC pattern and on the arms.**

### and one more misplacement

Once the socket moved outside the bolt circle, the tube still started at the
hub edge, so its first 3.9 mm was buried in the solid core. `motor_rod_r0`
is now the one place that answers "where does a motor tube start".

---

## studs instead of bolts, and half the plate was being wasted

### the segment count was throwing away the bed

The 13 inch frame was coming out as 9 arcs at 52 % of the plate when 4 fit at
85 %. The planner walked up from a floor of one segment per rod crossing and
then REJECTED any count where two rods wanted the same segment.

Both rules were dead. The floor existed because a bore had to sit on the
part's own front plane, and the rejection existed for the same reason; the
builder has drilled extra rods by rotating the body under the cut plane since
the pass-through work, and the comment in plan_ring even said so while the
code kept rejecting. Fewest arcs that fit is also the biggest arc, so it now
walks up from 1 and takes the first that fits.

    13 inch    9 arcs, 52 %  ->  4 arcs, 85 %   (36 printed arcs -> 16)
    as-built   9 arcs, 52 %  ->  3 arcs, 92 %
    cinewhoop  8 arcs, 46 %  ->  1 arc,  25 %   the ring prints whole

### which immediately broke the ring, and that was a real bug

Letting several rods share a segment exposed a disagreement that the old
rejection had been hiding. build_segment revolves the part around the main
cut NEAREST the segment mid; instances() placed it using the FIRST main in
tuple order. While there was only ever one main they could not differ. With
four, the part was drilled at one angle and placed at another, opening the
ring by a whole connector arc, 72 deg on the cinewhoop.

One rule in one place now, layout3d.main_phi, used by the placement table and
both builders.

### studs

Joints were two M3 through the lap, 40 bolts and 80 nuts per aircraft. They
are now blind pockets for a short locating pin, drilled into whichever tab
survives at each end so it goes down at one end and up at the other. The
carbon wrap is the joint; the pin only stops the halves sliding while it goes
on. `joint.stud = 0` puts the through bolts back.

The SolidWorks side got the direction backwards first time, and said so
loudly: `rev` is the flag that removes the material ABOVE the lap plane, so
at the end where the lap has already taken that half the surviving tab is the
lower one and the pocket has to go the other way. Drilling into the space the
lap cut away is a cut that removes nothing, which SolidWorks treats as an
error rather than a no-op.

Both backends agree on the result to 0.006 cm3 per segment.
