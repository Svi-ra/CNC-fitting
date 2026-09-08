# -*- coding: utf-8 -*-
r"""
gh_brep2mpr.py -- Grasshopper Script component: raw Brep -> woodWOP MPR text.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   B      Brep     access = Tree   one part per branch
    input   ID     str      access = Tree   piece ID, optional
    input   QTY    int      access = Tree   how many of this piece, optional
    output  MPR    -                        one whole program per setup,
                                            line endings already embedded
    output  NAME   -                        the file name for each program
    output  INFO   -                        one report per part

MPR and NAME are parallel trees: item *i* of a branch is the program, item *i*
of the same branch in NAME is what to call it. Write MPR out verbatim -- the
line endings are inside the string (CRLF by default). woodWOP splits a program
on CRLF; an LF-only file is read as one unparseable line and opens silently as
an empty default panel.

Takes raw solids with no attached data: the panel size and every drilling are
recognised from the geometry itself.

**Parts are assumed to arrive lying flat in the world XY plane** -- thickness
along Z. Nothing is rotated out of that plane; a part that is not flat is
reported in INFO rather than corrected.

    - the world bounding box gives the panel size
    - the long side of the part is turned to X (LONG_X)
    - cylindrical faces become drillings, classified by where they break out:
        along Z, open at the top      -> <102 \BohrVert\
        along X or Y, open at an edge -> <103 \BohrHoriz\
        any other angle               -> <104 \BohrUniv\
    - a flat rectangular cavity floor between the two faces becomes a sawn
      groove, <109 \Nuten\
    - an outline that is not the bounding rectangle becomes a contour ]1
      plus <105 \Konturfraesen\

What the machine can actually reach
-----------------------------------
The drilling head cannot do every hole in one clamping, so one part may come
out as more than one program (see MACHINE below):

    - the vertical drill array works from **one side only**, so a hole that
      opens at the underside is reachable only with the piece turned over;
    - the horizontal spindles carry a different bit on each side: the **top
      edge** (Y = BR) drills 8 mm only, the **lower edge** (Y = 0) 4.5 mm
      only, the **left and right edges** (X = 0, X = LA) do both;
    - the grooving saw runs **along X only** and its blade is 4 mm thick, so
      a groove running across the part, or narrower than the blade, cannot be
      cut. <109 \Nuten\ saws from the top face, so a groove in the underside
      needs the piece turned over just as an underside bore does.

The one allowed re-clamping is a **flip about the X axis**: the piece is
turned face for back, which swaps the top and lower edges and brings the
underside up. Left and right carry the same bits, so no other rotation buys
anything.

So a piece with 8 mm *and* 4.5 mm holes in its top edge comes out as two
programs: the first drills the 8 mm with the piece face up, the second is
written for the flipped piece, where those 4.5 mm holes now sit in the lower
edge. Turn the finished part back and every hole is where the model put it.

Anything the machine still cannot reach is reported in INFO and left out of
the program (set STRICT = False to have it written out anyway).

Identical panels
----------------
Solids of the same shape are converted once. A nested sheet where the same
panel appears twenty times gives one program, not twenty: the copies are
recognised before anything is planned, and their quantities are added up, so
the file comes out named for the total. The copies still get a line in INFO
saying which program covers them.

Two solids count as the same shape when they measure the same from the corner
of their own bounding boxes, within DUP_TOL -- so it does not matter where in
the model they sit. Orientation is deliberately not normalised: a copy turned
end for end has its holes at the other end and is a different program. Set
MERGE_IDENTICAL = False to convert every solid separately.

The ID of the first solid of a group names the programs. Where the copies
carried IDs of their own, INFO says so.

File names
----------
    <ID>_<length>x<width>-<F|B>_<quantity>.mpr

`F` = face up, as modelled. `B` = turned over. The quantity is the sum of QTY
over the identical solids folded into this program (1 per solid if nothing
came in on QTY), and is the same on every program of one piece. With no ID
input the branch path is used, so a flat list gives 0, 1, 2 ...
"""

import math

import Rhino
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

SNAP = 0.0          # round drill diameters to this step (0 = leave exact)
MAX_DIA = 60.0      # larger round openings are not treated as drillings
BM_VERT = "LS"      # drill mode for vertical bores: LS SS LSL SSS
THICKNESS = None    # force a thickness in mm, or None to measure it
LONG_X = True       # turn the part so its long side runs along X
CONTOUR = True      # emit a contour when the outline is not a rectangle
SAMPLES = 96        # points sampled per face loop
EXT = ".mpr"        # appended to every NAME ("" for a bare name)

MERGE_IDENTICAL = True  # solids of the same shape share one program
DUP_TOL = 0.01          # two solids count as the same shape within this, mm

# ---------------------------------------------------------------------------
# the machine
# ---------------------------------------------------------------------------
#
# What the drilling head is actually fitted with. A bore whose diameter is not
# on the matching list cannot be drilled in that position; the planner below
# tries the flipped setup, and reports the bore if that fails too.
#
# The vertical array is a bank of fixed spindles working from above only, so
# these two lists are the bits in it -- not depths. A bore that breaks out the
# far side comes off the through list, the rest off the dead-end list.

MACHINE = {
    "vert_blind": (35.0, 20.0, 15.0, 10.0, 8.0, 5.0),   # dead-end, from above
    "vert_thru": (7.0, 5.0),                            # right through
    "YM": (8.0,),                # top edge,   Y = BR, drills towards -Y
    "YP": (4.5,),                # lower edge, Y = 0,  drills towards +Y
    "XM": (8.0, 4.5),            # right edge, X = LA, drills towards -X
    "XP": (8.0, 4.5),            # left edge,  X = 0,  drills towards +X
}

EDGE_NAME = {"YM": "top edge", "YP": "lower edge",
             "XM": "right edge", "XP": "left edge"}

# The grooving saw. It runs along X only -- SAW_ALONG may be "X", "Y" or
# "XY" if the unit ever swivels -- and the blade is SAW_KERF thick, so a
# groove narrower than that cannot be cut at all. A wider one is fine:
# woodWOP makes it in several passes, which is what OP="1" asks for.
#
# A groove is read off the solid as a flat rectangular cavity floor lying
# between the two faces. GROOVE_MAX_WIDTH is where that stops being a groove
# and starts being a pocket, which this tool does not convert.

GROOVE = True             # detect grooves at all
SAW_KERF = 4.0            # blade thickness, mm
SAW_ALONG = "X"           # directions the saw can run: "X", "Y" or "XY"
GROOVE_MAX_WIDTH = 40.0   # wider flat cavities are pockets, not grooves

# woodWOP does not program a groove down its middle: XA/YA..XE/YE is one
# EDGE of the groove and RK offsets the blade a full NB to one side. Checked
# against a woodWOP 9.0.152 export of a known part --
# Examples/WoodWop_export/0_472x420-F_1.mpr against Examples/Meshes/472x420.gltf
# -- where a groove occupying Y 410..414 and running towards +X is written
# XA="75" YA="410" XE="_BSX" YE="410" RK="WRKR". So with RK="WRKR" the groove
# lies on the +Y side of a run towards +X; "WRKL" is the other side, and the
# rotated equivalents apply to a run towards +Y. Set "NoWRK" to go back to
# programming the centre line.
GROOVE_RK = "WRKR"

DIA_TOL = 0.2       # a measured diameter counts as a listed one within this
STRICT = True       # True: leave unreachable bores out and report them
                    # False: write them anyway, still reported

# Line endings. The MPR output carries EOL inside the string already. Set it
# to "\n" only if the export path applies CRLF itself, otherwise the file ends
# up with CR CR LF.
EOL = "\r\n"

FACE_TOL = 0.02     # "breaks out through this face", mm
GEO_TOL = 1e-4

try:
    _doc = Rhino.RhinoDoc.ActiveDoc
    TOL = _doc.ModelAbsoluteTolerance
    UNITS = _doc.ModelUnitSystem
except Exception:
    TOL = 0.001
    UNITS = None
if not TOL or TOL <= 0:
    TOL = 0.001


# ---------------------------------------------------------------------------
# vector helpers -- plain 3-tuples, so no RhinoCommon operator overloading
# ---------------------------------------------------------------------------

def p3(p):
    return (p.X, p.Y, p.Z)


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vlen(a):
    return math.sqrt(vdot(a, a))


def vnorm(a):
    n = vlen(a)
    return (0.0, 0.0, 0.0) if n < 1e-12 else (a[0] / n, a[1] / n, a[2] / n)


def canonical_axis(a):
    """+Z and -Z are the same hole axis; pick one representative direction."""
    a = vnorm(a)
    for c in a:
        if c > 1e-6:
            return a
        if c < -1e-6:
            return vmul(a, -1.0)
    return a


def rot_z90(p):
    """In-plane quarter turn -- keeps the part flat in XY."""
    return (p[1], -p[0], p[2])


# ---------------------------------------------------------------------------
# MPR output
# ---------------------------------------------------------------------------

TWO_PI = 2.0 * math.pi
SEP = " "


def fnum(v, nd=3):
    """Macro parameter value: trimmed, e.g. 9.5 / 18 / 0."""
    try:
        v = round(float(v), nd)
    except (TypeError, ValueError):
        return "0"
    if abs(v) < 10 ** (-nd):
        v = 0.0
    s = ("%.*f" % (nd, v)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


def cnum(v, nd=4):
    """Contour element coordinate: woodWOP writes these with four decimals."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0.0000"
    if abs(v) < 10 ** -(nd + 1):
        v = 0.0
    return "%.*f" % (nd, v)


def ds_code(ccw, sweep):
    """MPR parser constants: _cc=0 _cw=1 _CC=2 _CW=3 (section 4 of the spec)."""
    big = sweep > math.pi + 1e-9
    if ccw:
        return 2 if big else 0
    return 3 if big else 1


def arc_ds(p0, p1, centre, mid):
    """Direction code, using a point known to lie inside the arc."""
    def ang(p):
        return math.atan2(p[1] - centre[1], p[0] - centre[0])

    a0 = ang(p0)
    d1 = (ang(p1) - a0) % TWO_PI
    if mid is not None:
        dm = (ang(mid) - a0) % TWO_PI
        if 1e-9 < dm < d1:
            return ds_code(True, d1)
        return ds_code(False, TWO_PI - d1)
    return ds_code(True, d1) if d1 <= math.pi else ds_code(False, TWO_PI - d1)


class Part(object):
    def __init__(self):
        self.lx = self.ly = self.lz = 0.0
        self.macros = []            # (id, name, [(key, value), ...])
        self.contour = None         # [(kind, [(param, value), ...]), ...]
        self.notes = []


def mpr_lines(part):
    """The MPR program as a list of lines, with no line endings attached.

    The single-space entries are the block separators the format requires --
    every production woodWOP file has them. Do not let an export path strip
    trailing whitespace.
    """
    out = []
    a = out.append
    a("[H")
    a('VERSION="4.0 Alpha"')
    a('INCH="0"')
    a('OP="0"')
    a('FM="1"')
    a('FW="700"')
    a('VIEW="NOMIRROR"')
    a("_BSX=%.6f" % part.lx)
    a("_BSY=%.6f" % part.ly)
    a("_BSZ=%.6f" % part.lz)
    a(SEP)

    if part.contour:
        a("]1")
        for i, (kind, vals) in enumerate(part.contour):
            a("$E%d" % i)
            a(kind)
            for k, v in vals:
                a("%s=%s" % (k, v))
            a(SEP)

    a("<100 \\WerkStck\\")
    a('LA="%s"' % fnum(part.lx))
    a('BR="%s"' % fnum(part.ly))
    a('DI="%s"' % fnum(part.lz))
    a('FNX="0"')
    a('FNY="0"')
    a('AX="0"')
    a('AY="0"')
    a(SEP)

    if part.contour:
        a("<105 \\Konturfraesen\\")
        a('EA="1:0"')
        a('MDA="TAN"')
        a('RK="NoWRK"')
        a('EE="1:%d"' % (len(part.contour) - 1))
        a('MDE="TAN_AB"')
        a('EM="0"')
        a('RI="1"')
        a('TNO=""')
        a('S_="STANDARD"')
        a('F_="0"')
        a('AB=""')
        a('ZA="@0"')
        a('STUFEN="0"')
        a('ZSTART="0"')
        a('ANZZST="1"')
        a(SEP)

    for mid, name, params in part.macros:
        a("<%d \\%s\\" % (mid, name))
        for k, v in params:
            a('%s="%s"' % (k, v))
        a(SEP)

    while out and out[-1] == SEP:
        out.pop()               # '!' follows the last block directly
    a("!")
    a("")                       # so a join reproduces the trailing line end
    return out


def render_mpr(part):
    """The MPR program as one string, line endings already embedded."""
    return EOL.join(mpr_lines(part))


# ---------------------------------------------------------------------------
# reading the Brep
# ---------------------------------------------------------------------------

class Hole(object):
    """A bore, as the two ends of its axis plus a diameter."""

    def __init__(self, p0, p1, dia):
        self.p0 = p0
        self.p1 = p1
        self.dia = dia

    def axis(self):
        return canonical_axis(vsub(self.p1, self.p0))

    def moved(self, fn):
        """A copy in another frame; the original is left alone."""
        return Hole(fn(self.p0), fn(self.p1), self.dia)

    def transform(self, fn):
        self.p0 = fn(self.p0)
        self.p1 = fn(self.p1)


class Seg(object):
    """One outline segment: a line, or an arc with centre and interior point."""

    def __init__(self, p0, p1, centre=None, radius=None, mid=None):
        self.p0 = p0
        self.p1 = p1
        self.centre = centre
        self.radius = radius
        self.mid = mid

    def moved(self, fn):
        return Seg(fn(self.p0), fn(self.p1),
                   None if self.centre is None else fn(self.centre),
                   self.radius,
                   None if self.mid is None else fn(self.mid))

    def reversed_(self):
        """The same segment walked the other way round."""
        return Seg(self.p1, self.p0, self.centre, self.radius, self.mid)

    def transform(self, fn):
        self.p0 = fn(self.p0)
        self.p1 = fn(self.p1)
        if self.centre is not None:
            self.centre = fn(self.centre)
            self.mid = fn(self.mid)


class Groove(object):
    """A slot sawn into a face, held as the rectangle of its floor.

    `lo` and `hi` are the two opposite corners of that rectangle, both at the
    floor height; `normal` is which way the floor looks, and so which face the
    slot was cut into.
    """

    def __init__(self, lo, hi, normal):
        self.lo = lo
        self.hi = hi
        self.normal = normal

    def moved(self, pt, vec):
        """A copy in another setup frame. Both maps keep the floor flat and
        axis aligned, so re-sorting the corners is all it takes."""
        a, b = pt(self.lo), pt(self.hi)
        return Groove((min(a[0], b[0]), min(a[1], b[1]), a[2]),
                      (max(a[0], b[0]), max(a[1], b[1]), b[2]),
                      vec(self.normal))


def face_normal(face):
    """Outward normal of a face, honouring the face's orientation flag.

    Only ever called on planar faces, where the normal is the same everywhere,
    so evaluating at the middle of the domain is safe even when the face is
    trimmed.
    """
    n = p3(face.NormalAt(face.Domain(0).Mid, face.Domain(1).Mid))
    return vmul(n, -1.0) if face.OrientationIsReversed else n


def loop_points(face, count=SAMPLES):
    """Points sampled along the outer loop of a face."""
    crv = face.OuterLoop.To3dCurve()
    if crv is None:
        return []
    pts = []
    ts = crv.DivideByCount(count, True)
    if ts:
        pts = [p3(crv.PointAt(t)) for t in ts]
    if not pts:
        pts = [p3(crv.PointAtStart), p3(crv.PointAtEnd)]
    return pts


def loop_segments(face, notes):
    """Outer loop of a face as line / arc segments, in curve order."""
    crv = face.OuterLoop.To3dCurve()
    if crv is None:
        return []
    parts = crv.DuplicateSegments()
    if not parts:
        parts = [crv]
    segs = []
    for s in parts:
        p0, p1 = p3(s.PointAtStart), p3(s.PointAtEnd)
        if s.IsLinear(TOL):
            segs.append(Seg(p0, p1))
            continue
        ok, arc = s.TryGetArc(TOL)
        if ok:
            segs.append(Seg(p0, p1, p3(arc.Center), arc.Radius,
                            p3(arc.MidPoint)))
            continue
        notes.append("outline segment is neither line nor arc - "
                     "replaced by a straight chord")
        segs.append(Seg(p0, p1))
    return segs


def read_brep(brep, notes):
    """Everything we machine, in world coordinates.

    The part is taken to be lying flat already: thickness along Z. A part that
    clearly is not flat is reported rather than rotated, because turning it
    would silently contradict the layout the definition produced.
    """
    box = brep.GetBoundingBox(True)          # accurate, world aligned
    corners = [(x, y, z)
               for x in (box.Min.X, box.Max.X)
               for y in (box.Min.Y, box.Max.Y)
               for z in (box.Min.Z, box.Max.Z)]

    cylinders = []
    planars = []
    for face in brep.Faces:
        ok, cyl = face.UnderlyingSurface().TryGetCylinder(TOL)
        if ok:
            pts = loop_points(face)
            if not pts:
                continue
            axis = canonical_axis(p3(cyl.Axis))
            centre = p3(cyl.Center)
            base = vsub(centre, vmul(axis, vdot(centre, axis)))
            ts = [vdot(p, axis) for p in pts]
            cylinders.append((axis, base, cyl.Radius, min(ts), max(ts)))
            continue
        ok, _pl = face.TryGetPlane(TOL)
        if ok:
            planars.append((face_normal(face), loop_segments(face, notes)))

    holes = []
    for axis, base, radius, tmin, tmax in _merge(cylinders):
        if tmax - tmin < 0.05:
            continue
        holes.append(Hole(vadd(base, vmul(axis, tmin)),
                          vadd(base, vmul(axis, tmax)), 2.0 * radius))

    return corners, holes, planars


def _merge(cylinders):
    """Fold the half-cylinder patches of one bore back into a single hole."""
    groups = {}
    for axis, base, radius, tmin, tmax in cylinders:
        key = (tuple(round(c, 3) for c in axis),
               tuple(round(c, 3) for c in base),
               round(radius, 3))
        if key in groups:
            a, b, r, lo, hi = groups[key]
            groups[key] = (a, b, r, min(lo, tmin), max(hi, tmax))
        else:
            groups[key] = (axis, base, radius, tmin, tmax)
    return list(groups.values())


# ---------------------------------------------------------------------------
# placement
# ---------------------------------------------------------------------------

def _bbox(corners, holes):
    pts = list(corners)
    for h in holes:
        pts.append(h.p0)
        pts.append(h.p1)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _apply(fn, corners, holes, planars):
    corners = [fn(c) for c in corners]
    for h in holes:
        h.transform(fn)
    for n, segs in planars:
        for s in segs:
            s.transform(fn)
    planars[:] = [(fn(n), segs) for n, segs in planars]
    return corners


def place(corners, holes, planars, notes):
    """Long side along X, part sitting on the zero point, face up as modelled.

    Which face ends up on top -- and so which edge is the top edge -- is left
    to the setup planner below. That is a machining decision, not a property
    of the model.
    """
    if LONG_X:
        x0, y0, _z0, x1, y1, _z1 = _bbox(corners, holes)
        if (x1 - x0) < (y1 - y0) - GEO_TOL:
            corners = _apply(rot_z90, corners, holes, planars)
            notes.append("turned 90 deg so the long side runs along X - the "
                         "top and lower edges follow the turn")

    x0, y0, z0, _x1, _y1, _z1 = _bbox(corners, holes)
    if abs(x0) > GEO_TOL or abs(y0) > GEO_TOL or abs(z0) > GEO_TOL:
        corners = _apply(lambda p: vsub(p, (x0, y0, z0)),
                         corners, holes, planars)
    return corners


# ---------------------------------------------------------------------------
# setups: F = face up as modelled, B = turned over about the X axis
# ---------------------------------------------------------------------------

SETUPS = ("F", "B")


def setup_maps(mark, lx, ly, lz):
    """(point map, direction map) taking base coordinates into a setup.

    B is a 180 deg turn about the X axis followed by the shift that puts the
    part back on the zero point. The placed part spans 0..lx, 0..ly, 0..lz,
    so that shift is exactly (0, ly, lz). X is untouched, so a bore in the
    left edge stays in the left edge; the top and lower edges swap, and the
    two faces swap.
    """
    if mark == "B":
        return (lambda p: (p[0], ly - p[1], lz - p[2]),
                lambda v: (v[0], -v[1], -v[2]))
    ident = lambda v: v
    return (ident, ident)


# ---------------------------------------------------------------------------
# features -> macros
# ---------------------------------------------------------------------------

def nominal(dia, allowed):
    """The listed diameter this bore is, or None if the head has no such bit."""
    best = None
    for d in allowed:
        if abs(d - dia) <= DIA_TOL and (best is None
                                        or abs(d - dia) < abs(best - dia)):
            best = d
    return best


def feature(hole, lx, ly, lz):
    """What this bore is, in the setup frame it is handed in.

    Returns a dict keyed on 't': 'vert', 'horiz', 'univ' or 'none'.
    """
    p0, p1 = hole.p0, hole.p1
    ax, ay, az = hole.axis()

    if abs(abs(az) - 1.0) < 1e-3:
        zlo, zhi = min(p0[2], p1[2]), max(p0[2], p1[2])
        top = abs(zhi - lz) <= FACE_TOL
        bot = abs(zlo) <= FACE_TOL
        if not top and not bot:
            return {"t": "none",
                    "why": "closed internal bore at X=%s - it reaches neither "
                           "face" % fnum(p0[0])}
        return {"t": "vert", "x": p0[0], "y": p0[1],
                "zlo": zlo, "zhi": zhi, "top": top, "bot": bot,
                "thru": top and bot}

    along_x = abs(abs(ax) - 1.0) < 1e-3
    along_y = abs(abs(ay) - 1.0) < 1e-3
    if abs(az) < 1e-3 and (along_x or along_y):
        i = 0 if along_x else 1
        lo, hi = (p0, p1) if p0[i] <= p1[i] else (p1, p0)
        limit = lx if along_x else ly
        if abs(lo[i]) <= FACE_TOL:
            bm, entry = ("XP" if along_x else "YP"), lo
        elif abs(hi[i] - limit) <= FACE_TOL:
            bm, entry = ("XM" if along_x else "YM"), hi
        else:
            return {"t": "none",
                    "why": "internal horizontal bore at X=%s - it reaches no "
                           "edge" % fnum(p0[0])}
        return {"t": "horiz", "bm": bm, "entry": entry, "len": hi[i] - lo[i]}

    d = vnorm(vsub(p0, p1))
    entry = p1
    if d[2] > 0:
        d = vmul(d, -1.0)
        entry = p0
    return {"t": "univ", "entry": entry,
            "wi": math.degrees(math.acos(max(-1.0, min(1.0, -d[2])))),
            "ca": math.degrees(math.atan2(d[1], d[0])) % 360.0,
            "len": vlen(vsub(p1, p0))}


def find_grooves(planars, lz, notes):
    """Slots read off the solid: a flat rectangular floor between the faces.

    A face whose normal is +/-Z and whose height is neither 0 nor the panel
    thickness is the bottom of something cut into the part. If it is a plain
    axis-aligned rectangle of straight edges it is a sawn slot; anything else
    -- a round-ended pocket, a free-form cavity, a floor split over several
    faces -- is reported and left alone, as pockets always have been.
    """
    out = []
    for normal, segs in planars:
        if abs(abs(normal[2]) - 1.0) > 1e-3 or not segs:
            continue
        z = segs[0].p0[2]
        if z <= FACE_TOL or z >= lz - FACE_TOL:
            continue                    # the part's own top or bottom face

        if len(segs) < 3 or all(sg.radius for sg in segs):
            continue                    # the flat bottom of a blind bore

        flat = all(abs(p[2] - z) <= GEO_TOL
                   for sg in segs for p in (sg.p0, sg.p1))
        if len(segs) != 4 or not flat or any(sg.radius for sg in segs):
            notes.append("flat cavity floor at Z=%s is not a plain rectangle "
                         "- round-ended slots and pockets are not converted"
                         % fnum(z))
            continue

        xs = [sg.p0[0] for sg in segs]
        ys = [sg.p0[1] for sg in segs]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        got = set((round(x, 3), round(y, 3)) for x, y in zip(xs, ys))
        want = set((round(a, 3), round(b, 3))
                   for a in (x0, x1) for b in (y0, y1))
        if got != want or x1 - x0 < GEO_TOL or y1 - y0 < GEO_TOL:
            notes.append("flat cavity floor at Z=%s is not square to X and Y "
                         "- not converted" % fnum(z))
            continue

        out.append(Groove((x0, y0, z), (x1, y1, z), normal))
    return out


def groove_feature(g, lx, ly, lz):
    """What this slot is, in the setup frame it is handed in."""
    z = g.lo[2]
    up = g.normal[2] > 0
    w = g.hi[0] - g.lo[0]
    h = g.hi[1] - g.lo[1]
    if abs(w - h) <= GEO_TOL:
        return {"t": "none",
                "why": "square flat cavity %s x %s mm at X=%s - that is a "
                       "pocket, not a groove"
                       % (fnum(w), fnum(h), fnum(g.lo[0]))}

    # The run is always written towards +X or +Y, so which edge to programme
    # follows straight from RK: see the note on GROOVE_RK above.
    if h < w:
        dirn, nb, run = "X", h, w
        if GROOVE_RK == "NoWRK":
            edge = 0.5 * (g.lo[1] + g.hi[1])
        else:
            edge = g.lo[1] if GROOVE_RK == "WRKR" else g.hi[1]
        xa, ya, xe, ye = g.lo[0], edge, g.hi[0], edge
        full = g.lo[0] <= FACE_TOL and g.hi[0] >= lx - FACE_TOL
    else:
        dirn, nb, run = "Y", w, h
        if GROOVE_RK == "NoWRK":
            edge = 0.5 * (g.lo[0] + g.hi[0])
        else:
            edge = g.hi[0] if GROOVE_RK == "WRKR" else g.lo[0]
        xa, ya, xe, ye = edge, g.lo[1], edge, g.hi[1]
        full = g.lo[1] <= FACE_TOL and g.hi[1] >= ly - FACE_TOL

    return {"t": "groove", "up": up, "dirn": dirn, "nb": nb, "run": run,
            "ti": (lz - z) if up else z, "full": full,
            "xa": xa, "ya": ya, "xe": xe, "ye": ye}


def diameters(key):
    return ", ".join(fnum(d) for d in MACHINE[key])


def reachable(feat, dia):
    """Can the head do this bore in this setup? -> (ok, nominal dia, why not)."""
    if feat["t"] == "none":
        return False, dia, feat["why"]

    if feat["t"] == "vert":
        key = "vert_thru" if feat["thru"] else "vert_blind"
        nom = nominal(dia, MACHINE[key])
        if nom is None:
            return False, dia, (
                "%s mm %s vertical bore - the array carries %s"
                % (fnum(dia), "through" if feat["thru"] else "dead-end",
                   diameters(key)))
        if not feat["top"]:
            return False, dia, (
                "%s mm vertical bore opens at the underside - the array only "
                "drills from above" % fnum(dia))
        return True, nom, None

    if feat["t"] == "groove":
        nb = feat["nb"]
        if feat["dirn"] not in SAW_ALONG:
            return False, nb, (
                "%s mm groove runs along %s - the saw runs along %s"
                % (fnum(nb), feat["dirn"], " and ".join(SAW_ALONG)))
        if nb < SAW_KERF - GEO_TOL:
            return False, nb, (
                "%s mm groove - the blade is %s mm thick and will not fit"
                % (fnum(nb), fnum(SAW_KERF)))
        if nb > GROOVE_MAX_WIDTH:
            return False, nb, (
                "%s mm wide flat cavity - over GROOVE_MAX_WIDTH, so it is "
                "read as a pocket rather than a groove" % fnum(nb))
        if not feat["up"]:
            return False, nb, (
                "%s mm groove in the underside - <109 Nuten> saws from the "
                "top face only, so the piece has to be turned over"
                % fnum(nb))
        return True, nb, None

    if feat["t"] == "horiz":
        bm = feat["bm"]
        nom = nominal(dia, MACHINE[bm])
        if nom is None:
            return False, dia, (
                "%s mm bore in the %s - that side drills %s"
                % (fnum(dia), EDGE_NAME[bm], diameters(bm)))
        return True, nom, None

    return False, dia, ("bore %s deg off vertical - the head does not swivel"
                        % fnum(feat["wi"]))


def macro(feat, dia, lz):
    """The MPR macro for a bore, or None if there is nothing to write."""
    if feat["t"] == "vert":
        depth = lz if feat["thru"] else lz - feat["zlo"]
        return (102, "BohrVert", [
            ("XA", fnum(feat["x"])), ("YA", fnum(feat["y"])),
            ("TI", fnum(depth)), ("DU", fnum(dia)),
            ("BM", BM_VERT), ("S_", "2"),
            ("AN", "1"), ("AB", "0"), ("WI", "0")])

    if feat["t"] == "horiz":
        e = feat["entry"]
        return (103, "BohrHoriz", [
            ("XA", fnum(e[0])), ("YA", fnum(e[1])), ("ZA", fnum(e[2])),
            ("DU", fnum(dia)), ("TI", fnum(feat["len"])),
            ("BM", feat["bm"]),
            ("AN", "1"), ("AB", "0"), ("F_", "STANDARD")])

    if feat["t"] == "groove":
        # Parameters and their order follow woodWOP's own export of this
        # macro; TV="0" leaves the scoring pass off, and MOD2 lets the blade
        # run in and out clear of a groove that reaches both edges.
        return (109, "Nuten", [
            ("XA", fnum(feat["xa"])), ("YA", fnum(feat["ya"])), ("WI", "0"),
            ("XE", fnum(feat["xe"])), ("YE", fnum(feat["ye"])),
            ("NB", fnum(dia)),
            ("RK", GROOVE_RK),
            ("EM", "MOD2" if feat["full"] else "MOD0"),
            ("AD", "0"),
            ("TI", fnum(feat["ti"])),
            ("TV", "0"), ("VT", "0"), ("MV", "GL"),
            ("XY", "80"), ("MN", "GL"), ("BL", "0"),
            ("OP", "0"), ("AN", "0"),
            ("S_", "STANDARD"), ("F_", "STANDARD")])

    if feat["t"] == "univ":
        e = feat["entry"]
        return (104, "BohrUniv", [
            ("XA", fnum(e[0])), ("YA", fnum(e[1])), ("ZA", fnum(e[2])),
            ("CA", fnum(feat["ca"])), ("WI", fnum(feat["wi"])),
            ("DU", fnum(dia)), ("TI", fnum(feat["len"])),
            ("AN", "1"), ("AB", "0"), ("F_", "STANDARD")])

    return None


def loop_area(segs):
    """Twice the signed area of the polygon through the segment ends.

    Only the sign is wanted -- counter-clockwise from clockwise -- so the
    chord across each arc is close enough.
    """
    total = 0.0
    for s in segs:
        total += s.p0[0] * s.p1[1] - s.p1[0] * s.p0[1]
    return total


def is_rectangle(segs, lx, ly):
    """Does this loop go round the panel's bounding rectangle and nothing else?"""
    if len(segs) != 4 or any(s.radius for s in segs):
        return False
    corners = set((round(s.p0[0], 2), round(s.p0[1], 2)) for s in segs)
    return corners == {(0.0, 0.0), (round(lx, 2), 0.0),
                       (round(lx, 2), round(ly, 2)), (0.0, round(ly, 2))}


def outline(planars, part):
    """Contour elements for the panel outline, when it is not the rectangle.

    Both faces are looked at, not only the top one. A groove that runs out to
    an edge cuts a notch in the face it was sawn into, and that notch belongs
    to the groove, not to the outline -- following it would rout the panel to
    the shape of its own grooving. So if either face still goes round the
    plain rectangle the part is a rectangle and there is nothing to rout; if
    neither does, the less interrupted of the two is the outline.
    """
    faces = []
    for normal, segs in planars:
        if not segs or abs(abs(normal[2]) - 1.0) > 1e-3:
            continue
        z = segs[0].p0[2]
        if normal[2] > 0 and abs(z - part.lz) <= 0.5:
            faces.append(segs)
        elif normal[2] < 0 and abs(z) <= 0.5:
            faces.append(segs)
    if not faces:
        return None
    for segs in faces:
        if is_rectangle(segs, part.lx, part.ly):
            return None                 # plain rectangle: WerkStck covers it
    best = max(faces, key=lambda sg: abs(loop_area(sg)))

    if loop_area(best) < 0:
        # Turning the part over mirrors the outline. Walk it the other way so
        # the contour stays counter-clockwise and RI="1" keeps its meaning.
        best = [s.reversed_() for s in reversed(best)]

    elems = [("KP", [("X", cnum(best[0].p0[0])), ("Y", cnum(best[0].p0[1])),
                     ("Z", "0"), ("KO", "0")])]
    for s in best:
        if s.radius:
            elems.append(("KA", [("X", cnum(s.p1[0])), ("Y", cnum(s.p1[1])),
                                 ("R", cnum(s.radius)),
                                 ("DS", str(arc_ds(s.p0, s.p1, s.centre,
                                                   s.mid)))]))
        else:
            elems.append(("KL", [("X", cnum(s.p1[0])), ("Y", cnum(s.p1[1]))]))

    return elems


def check_flat(lx, ly, lz, notes):
    """The script assumes the part already lies flat: thickness along Z.

    Nothing is rotated out of plane to fix it -- that would contradict the
    layout the definition produced -- but a part fed in on edge would quietly
    yield a program with the wrong size and the wrong drilling, so say so.
    """
    dims = (lx, ly, lz)
    thin = min(range(3), key=lambda i: dims[i])
    if thin != 2 and dims[thin] < 0.6 * sorted(dims)[1]:
        notes.append(
            "WARNING: this part is not lying flat in XY - its thinnest "
            "direction is %s (%s mm), so DI reads %s mm. Size and drilling "
            "below are almost certainly wrong."
            % ("XYZ"[thin], fnum(dims[thin]), fnum(lz)))


# ---------------------------------------------------------------------------
# planning the setups
# ---------------------------------------------------------------------------

def plan(holes, grooves, lx, ly, lz, notes):
    """Split the drilling over as few setups as the machine allows.

    Every bore is tried face up and turned over. One that works only one way
    forces that setup; one that works either way rides along with the first
    setup already needed, so a part that fits in one clamping stays one file.
    Whatever works neither way is reported and, under STRICT, left out.

    Grooves go through the same mill: the saw cuts from the top face only,
    so a slot in the underside needs the piece turned over exactly as an
    underside bore does, and rides along with that setup when there is one.

    Returns [(mark, [(feature, size), ...]), ...], first setup first, where
    size is the nominal diameter of a bore or the width of a groove.
    """
    jobs = []
    for hole in holes:
        dia = hole.dia
        if SNAP > 0:
            dia = round(dia / SNAP) * SNAP
        if dia > MAX_DIA:
            notes.append("round opening %s mm left as geometry, not drilled "
                         "(over MAX_DIA)" % fnum(dia))
            continue
        jobs.append(("hole", Hole(hole.p0, hole.p1, dia), dia))
    for groove in grooves:
        jobs.append(("groove", groove, 0.0))

    tried = []
    for kind, item, size in jobs:
        opts = {}
        why = {}
        for mark in SETUPS:
            pt, vec = setup_maps(mark, lx, ly, lz)
            if kind == "hole":
                feat = feature(item.moved(pt), lx, ly, lz)
                want = size
            else:
                feat = groove_feature(item.moved(pt, vec), lx, ly, lz)
                want = feat.get("nb", 0.0)
            ok, nom, reason = reachable(feat, want)
            if ok:
                opts[mark] = (feat, nom)
                if kind == "hole" and abs(nom - want) > 0.001:
                    notes.append("%s mm bore taken as the %s mm bit"
                                 % (fnum(want), fnum(nom)))
            else:
                why[mark] = reason
        tried.append((kind, item, size, opts, why))

    needed = [mark for mark in SETUPS
              if any(len(o) == 1 and mark in o for _k, _i, _s, o, _w in tried)]
    if not needed:
        needed = ["F"]

    work = dict((mark, []) for mark in needed)
    for kind, item, size, opts, why in tried:
        here = [m for m in needed if m in opts]
        if here:
            feat, nom = opts[here[0]]
            work[here[0]].append((feat, nom))
            continue
        # Reachable in neither setup. Say so; under STRICT the bore is simply
        # not in the program, otherwise it is written face up so that at
        # least it shows in woodWOP and someone has to look at it.
        face_up, over = why.get("F"), why.get("B")
        reason = face_up or over or "not reachable"
        if face_up and over and over != face_up:
            reason = "%s (turned over: %s)" % (face_up, over)
        notes.append(reason + (" - left out of the program" if STRICT
                               else " - WRITTEN ANYWAY (STRICT is off)"))
        if not STRICT:
            pt, vec = setup_maps(needed[0], lx, ly, lz)
            feat = (feature(item.moved(pt), lx, ly, lz) if kind == "hole"
                    else groove_feature(item.moved(pt, vec), lx, ly, lz))
            if feat["t"] != "none":
                work[needed[0]].append(
                    (feat, size if kind == "hole" else feat["nb"]))

    if len(needed) > 1:
        notes.append("two setups: %s does everything reachable face up, then "
                     "the piece is turned over about its long axis for %s"
                     % (needed[0], needed[1]))
    elif needed[0] == "B":
        notes.append("one setup, but with the piece turned over - the "
                     "machining is all on the underside as modelled")
    return [(mark, work[mark]) for mark in needed]


def brep_to_setups(brep):
    """One Brep -> [(mark, Part), ...]. Every Part carries the same notes."""
    notes = []
    if brep is None or not brep.IsValid:
        raise ValueError("invalid Brep")

    corners, holes, planars = read_brep(brep, notes)
    corners = place(corners, holes, planars, notes)

    x0, y0, z0, x1, y1, z1 = _bbox(corners, holes)
    lx, ly = x1 - x0, y1 - y0
    lz = (z1 - z0) if THICKNESS is None else THICKNESS
    if lx < 1.0 or ly < 1.0 or lz < 0.5:
        raise ValueError("implausible part size %s x %s x %s mm"
                         % (fnum(lx), fnum(ly), fnum(lz)))
    check_flat(lx, ly, lz, notes)

    grooves = find_grooves(planars, lz, notes) if GROOVE else []

    out = []
    planned = plan(holes, grooves, lx, ly, lz, notes)
    for i, (mark, work) in enumerate(planned):
        part = Part()
        part.lx, part.ly, part.lz = lx, ly, lz
        part.notes = notes
        for feat, dia in work:
            m = macro(feat, dia, lz)
            if m is not None:
                part.macros.append(m)
        part.macros.sort(key=lambda m: (m[0],
                                        float(dict(m[2]).get("XA", 0)),
                                        float(dict(m[2]).get("YA", 0))))
        if CONTOUR and i == 0:
            # The outline is cut once, in the first setup. After that the
            # piece is no longer the rectangle the blank started as, so
            # repeating the contour in the second file would cut air.
            pt, vec = setup_maps(mark, lx, ly, lz)
            moved = [(vec(n), [s.moved(pt) for s in segs])
                     for n, segs in planars]
            part.contour = outline(moved, part)
            if part.contour and len(planned) > 1:
                notes.append("the outline is cut in the first setup only - "
                             "check the piece is still held well enough for "
                             "the second, or cut the contour last")
        out.append((mark, part))
    return out


# ---------------------------------------------------------------------------
# identical panels
# ---------------------------------------------------------------------------

def geometry_key(brep):
    """A shape fingerprint, so the same panel is only converted once.

    Two solids match when they are the same shape in the same orientation,
    wherever they sit in the model: everything is measured from the corner of
    the part's own bounding box, so a nested sheet of copies folds into one
    program. Orientation is deliberately *not* normalised -- a copy turned end
    for end carries its holes at the other end and is a different program.

    Nothing here calls the converter, so a duplicate costs a bounding box and
    a walk over the vertices instead of a full conversion.
    """
    box = brep.GetBoundingBox(True)
    org = (box.Min.X, box.Min.Y, box.Min.Z)

    def q(p):
        """A point relative to the bounding box corner, in DUP_TOL steps."""
        return (int(round((p[0] - org[0]) / DUP_TOL)),
                int(round((p[1] - org[1]) / DUP_TOL)),
                int(round((p[2] - org[2]) / DUP_TOL)))

    size = q((box.Max.X, box.Max.Y, box.Max.Z))

    # Vertex positions alone already separate two different panels; the face
    # list adds the radius and axis of every bore, which vertices do not carry.
    verts = sorted(q(p3(v.Location)) for v in brep.Vertices)

    faces = []
    for face in brep.Faces:
        ok, cyl = face.UnderlyingSurface().TryGetCylinder(TOL)
        if ok:
            tag = ("cyl", int(round(cyl.Radius / DUP_TOL)),
                   tuple(int(round(c / DUP_TOL))
                         for c in canonical_axis(p3(cyl.Axis))))
        else:
            ok, _pl = face.TryGetPlane(TOL)
            tag = ("pln" if ok else "srf", 0, (0, 0, 0))
        fb = face.GetBoundingBox(True)
        faces.append(tag + q(p3(fb.Min)) + q(p3(fb.Max)))
    faces.sort()

    return (size, tuple(verts), tuple(faces))


# ---------------------------------------------------------------------------
# naming and reporting
# ---------------------------------------------------------------------------

def file_name(ident, part, mark, qty):
    """<ID>_<length>x<width>-<F|B>_<quantity>.mpr"""
    return "%s_%sx%s-%s_%s%s" % (ident, fnum(part.lx), fnum(part.ly),
                                 mark, qty, EXT)


def describe(ident, qty, setups, copies=()):
    _mark, first = setups[0]
    lines = ["%s   %s x %s x %s mm   x%s   %d file%s"
             % (ident, fnum(first.lx), fnum(first.ly), fnum(first.lz), qty,
                len(setups), "" if len(setups) == 1 else "s")]
    if copies:
        names = [c[2] for c in copies]
        shown = ", ".join(names[:8]) + (", ..." if len(names) > 8 else "")
        lines.append("  %d identical solid%s folded in (%s) - converted once, "
                     "their quantities are in the x%s above"
                     % (len(copies), "" if len(copies) == 1 else "s",
                        shown, qty))
        if any(name != ident for name in names):
            lines.append("  note: the copies did not all carry the same ID - "
                         "the programs are named after %s" % ident)
    for mark, part in setups:
        counts = {}
        for _mid, name, _p in part.macros:
            counts[name] = counts.get(name, 0) + 1
        detail = ", ".join("%d x %s" % (v, k)
                           for k, v in sorted(counts.items()))
        if part.contour:
            detail += (", " if detail else "") + "contour"
        lines.append("  %s  %-11s %s"
                     % (mark, "face up" if mark == "F" else "turned over",
                        detail or "no machining"))
    for note in dict.fromkeys(first.notes):
        lines.append("  note: %s" % note)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Grasshopper plumbing
# ---------------------------------------------------------------------------

def branches_of(tree):
    """Work whether the input access is Tree, List or Item."""
    if tree is None:
        return []
    if hasattr(tree, "Branches") and hasattr(tree, "Paths"):
        return list(zip(list(tree.Paths), [list(b) for b in tree.Branches]))
    if isinstance(tree, (list, tuple)):
        return [(GH_Path(0), list(tree))]
    return [(GH_Path(0), [tree])]


class SideInput(object):
    """ID / QTY looked up by branch first, then by running part number.

    So the inputs can be wired either way: a tree matching B branch for
    branch, or one flat list in the same order as the parts.
    """

    def __init__(self, tree):
        self.by_path = {}
        self.flat = []
        for path, items in branches_of(tree):
            items = [v for v in items if v is not None]
            self.by_path[str(path)] = items
            self.flat.extend(items)

    def get(self, path, j, n):
        items = self.by_path.get(str(path))
        if items:
            return items[j] if j < len(items) else items[-1]
        if n < len(self.flat):
            return self.flat[n]
        return None


def clean(text):
    """Keep a piece ID usable as a file name."""
    out = []
    for ch in str(text).strip():
        out.append(ch if (ch.isalnum() or ch in "-+.") else "_")
    return "".join(out).strip("_") or "part"


def default_id(path, j, count):
    """No ID wired: fall back on the branch path, so a flat list gives 0,1,2."""
    base = str(path).strip("{}").replace(";", "-").strip()
    return "%s-%d" % (base, j) if count > 1 else base


# ID and QTY are optional: the component still runs with only B wired.
try:
    ID
except NameError:
    ID = None
try:
    QTY
except NameError:
    QTY = None

MPR = DataTree[object]()
NAME = DataTree[object]()
INFO = DataTree[object]()

if UNITS is not None and UNITS != Rhino.UnitSystem.Millimeters:
    INFO.Add("WARNING: the document is not in millimetres (%s). woodWOP "
             "expects mm - every size below is wrong." % UNITS, GH_Path(0))

ids = SideInput(ID)
qtys = SideInput(QTY)
taken = {}
n = 0

# Read the whole input first: identical solids have to be found before any of
# them is converted, so the shape is only put through the planner once.
entries = []                        # (path, brep, ident, qty), in input order
for path, items in branches_of(B):
    for j, brep in enumerate(items):
        if brep is None:
            continue
        try:
            given = ids.get(path, j, n)
            ident = (clean(given) if given is not None
                     else default_id(path, j, len(items)))
        except Exception:
            ident = "part-%d" % n

        try:
            qty = max(1, int(round(float(qtys.get(path, j, n)))))
        except Exception:
            qty = 1

        entries.append((path, brep, ident, qty))
        n += 1

# Group by shape, keeping the order the parts came in. The first solid of a
# group is the one converted; the rest only add to its quantity.
groups = []                         # lists of indices into entries
first_seen = {}
for i, entry in enumerate(entries):
    key = None
    if MERGE_IDENTICAL:
        try:
            key = geometry_key(entry[1])
        except Exception:
            key = None              # unreadable shape: leave it on its own
    if key is not None and key in first_seen:
        groups[first_seen[key]].append(i)
        continue
    if key is not None:
        first_seen[key] = len(groups)
    groups.append([i])

for members in groups:
    path, brep, ident, _qty = entries[members[0]]
    copies = [entries[i] for i in members[1:]]
    qty = sum(entries[i][3] for i in members)
    try:
        setups = brep_to_setups(brep)
        for mark, part in setups:
            name = file_name(ident, part, mark, qty)
            if name in taken:
                taken[name] += 1
                stem = name[:-len(EXT)] if EXT else name
                name = "%s(%d)%s" % (stem, taken[name], EXT)
                INFO.Add("WARNING: two pieces asked for the same file "
                         "name - the second is now %s. Give them "
                         "distinct IDs." % name, path)
            else:
                taken[name] = 1
            MPR.Add(render_mpr(part), path)
            NAME.Add(name, path)
        INFO.Add(describe(ident, qty, setups, copies), path)
    except Exception as exc:
        MPR.Add(None, path)
        NAME.Add(None, path)
        INFO.Add("ERROR: %s" % exc, path)
    for cpath, _cbrep, cident, cqty in copies:
        INFO.Add("%s   identical to %s - no program of its own, its x%s is in "
                 "that one" % (cident, ident, cqty), cpath)
