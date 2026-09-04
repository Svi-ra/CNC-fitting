# -*- coding: utf-8 -*-
r"""
gh_brep2mpr.py -- Grasshopper Script component: raw Brep -> woodWOP MPR text.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   B      Brep      access = Tree      (one part per branch)
    output  MPR    -                            (one MPR program per branch)
    output  INFO   -                            (one report line per part)

Takes raw solids with no attached data: the panel size and every drilling are
recognised from the geometry itself.

**Parts are assumed to arrive lying flat in the world XY plane** — thickness
along Z. Nothing is rotated out of that plane; a part that is not flat is
reported in INFO rather than corrected.

    - the world bounding box gives the panel size
    - the long side of the part is turned to X (LONG_X)
    - the part is turned over if all the vertical drilling would otherwise
      come from underneath (FLIP)
    - cylindrical faces become drillings, classified by where they break out:
        along Z, open at the top      -> <102 \BohrVert\
        along Z, open at the bottom   -> <131 \UfluBohr\
        along X or Y, open at an edge -> <103 \BohrHoriz\
        any other angle               -> <104 \BohrUniv\
    - an outline that is not the bounding rectangle becomes a contour ]1
      plus <105 \Konturfraesen\

Output is text, not files. Write it out with a File component, or feed it to a
Stream Contents component -- but write with CRLF: woodWOP reads an LF-only
program as one unparseable line and silently opens an empty default panel.
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
FLIP = True         # turn the part over if it would be drilled from below
CONTOUR = True      # emit a contour when the outline is not a rectangle
SAMPLES = 96        # points sampled per face loop

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


# in-plane rotations: both keep the part flat in XY (proper rotations)

def rot_z90(p):
    return (p[1], -p[0], p[2])


def rot_x180(p):
    return (p[0], -p[1], -p[2])


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
        self.contour = None         # [(kind, {param: value}), ...]
        self.notes = []


def render_mpr(part):
    """Build the MPR program text. Newlines are LF here -- convert on write."""
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
    return "\n".join(out) + "\n"


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

    def transform(self, fn):
        self.p0 = fn(self.p0)
        self.p1 = fn(self.p1)
        if self.centre is not None:
            self.centre = fn(self.centre)
            self.mid = fn(self.mid)


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
# orientation
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
    """Long side along X, drilling from above, part on the zero point.

    Both rotations are about Z or about X by 180 degrees, so the part stays
    flat in XY either way.
    """
    if LONG_X:
        x0, y0, _z0, x1, y1, _z1 = _bbox(corners, holes)
        if (x1 - x0) < (y1 - y0) - GEO_TOL:
            corners = _apply(rot_z90, corners, holes, planars)
            notes.append("turned 90 deg so the long side runs along X")

    if FLIP:
        _x0, _y0, z0, _x1, _y1, z1 = _bbox(corners, holes)
        top = bot = 0
        for h in holes:
            if abs(abs(h.axis()[2]) - 1.0) > 1e-3:
                continue
            if abs(max(h.p0[2], h.p1[2]) - z1) <= FACE_TOL:
                top += 1
            elif abs(min(h.p0[2], h.p1[2]) - z0) <= FACE_TOL:
                bot += 1
        if bot and not top:
            corners = _apply(rot_x180, corners, holes, planars)
            notes.append("turned over so the drilling is done from above")

    x0, y0, z0, _x1, _y1, _z1 = _bbox(corners, holes)
    if abs(x0) > GEO_TOL or abs(y0) > GEO_TOL or abs(z0) > GEO_TOL:
        corners = _apply(lambda p: vsub(p, (x0, y0, z0)),
                         corners, holes, planars)
    return corners


# ---------------------------------------------------------------------------
# features -> macros
# ---------------------------------------------------------------------------

def emit_hole(part, hole):
    dia = hole.dia
    if SNAP > 0:
        dia = round(dia / SNAP) * SNAP
    if dia > MAX_DIA:
        part.notes.append("round opening d=%s left as geometry, not drilled "
                          "(over MAX_DIA)" % fnum(dia))
        return

    p0, p1 = hole.p0, hole.p1
    ax, ay, az = hole.axis()

    # ---- vertical --------------------------------------------------------
    if abs(abs(az) - 1.0) < 1e-3:
        zlo, zhi = min(p0[2], p1[2]), max(p0[2], p1[2])
        x, y = p0[0], p0[1]
        open_top = abs(zhi - part.lz) <= FACE_TOL
        open_bot = abs(zlo) <= FACE_TOL
        if open_top:
            depth = part.lz if open_bot else part.lz - zlo
            part.macros.append((102, "BohrVert", [
                ("XA", fnum(x)), ("YA", fnum(y)),
                ("TI", fnum(depth)), ("DU", fnum(dia)),
                ("BM", BM_VERT), ("S_", "2"),
                ("AN", "1"), ("AB", "0"), ("WI", "0")]))
        elif open_bot:
            part.macros.append((131, "UfluBohr", [
                ("XA", fnum(x)), ("YA", fnum(y)),
                ("DU", fnum(dia)), ("WI", "0"),
                ("TI", fnum(zhi)), ("AB", "0"), ("F_", "STANDARD")]))
        else:
            part.notes.append("closed internal bore d=%s at X=%s Y=%s skipped"
                              % (fnum(dia), fnum(x), fnum(y)))
        return

    # ---- horizontal ------------------------------------------------------
    along_x = abs(abs(ax) - 1.0) < 1e-3
    along_y = abs(abs(ay) - 1.0) < 1e-3
    if abs(az) < 1e-3 and (along_x or along_y):
        i = 0 if along_x else 1
        lo, hi = (p0, p1) if p0[i] <= p1[i] else (p1, p0)
        limit = part.lx if along_x else part.ly
        if abs(lo[i]) <= FACE_TOL:
            bm, entry = ("XP" if along_x else "YP"), lo
        elif abs(hi[i] - limit) <= FACE_TOL:
            bm, entry = ("XM" if along_x else "YM"), hi
        else:
            part.notes.append("internal horizontal bore d=%s skipped "
                              "(reaches no edge)" % fnum(dia))
            return
        part.macros.append((103, "BohrHoriz", [
            ("XA", fnum(entry[0])), ("YA", fnum(entry[1])),
            ("ZA", fnum(entry[2])), ("DU", fnum(dia)),
            ("TI", fnum(hi[i] - lo[i])), ("BM", bm),
            ("AN", "1"), ("AB", "0"), ("F_", "STANDARD")]))
        return

    # ---- any other angle -------------------------------------------------
    d = vnorm(vsub(p0, p1))
    entry = p1
    if d[2] > 0:
        d = vmul(d, -1.0)
        entry = p0
    wi = math.degrees(math.acos(max(-1.0, min(1.0, -d[2]))))
    ca = math.degrees(math.atan2(d[1], d[0])) % 360.0
    part.macros.append((104, "BohrUniv", [
        ("XA", fnum(entry[0])), ("YA", fnum(entry[1])),
        ("ZA", fnum(entry[2])), ("CA", fnum(ca)), ("WI", fnum(wi)),
        ("DU", fnum(dia)), ("TI", fnum(vlen(vsub(p1, p0)))),
        ("AN", "1"), ("AB", "0"), ("F_", "STANDARD")]))
    part.notes.append("slanted bore as <104 BohrUniv> (CA=%s WI=%s) - needs a "
                      "swivel drilling unit" % (fnum(ca), fnum(wi)))


def outline(planars, part):
    """Contour elements for the top face, when it is not just the rectangle."""
    best = None
    best_z = None
    for normal, segs in planars:
        if abs(normal[2] - 1.0) > 1e-3 or not segs:
            continue
        z = max(s.p0[2] for s in segs)
        if best_z is None or z > best_z + GEO_TOL:
            best_z, best = z, segs
    if not best or abs(best_z - part.lz) > 0.5:
        return None

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

    if len(elems) == 5 and all(k == "KL" for k, _v in elems[1:]):
        corners = set()
        for _k, vals in elems:
            d = dict(vals)
            corners.add((round(float(d["X"]), 2), round(float(d["Y"]), 2)))
        rect = {(0.0, 0.0), (round(part.lx, 2), 0.0),
                (round(part.lx, 2), round(part.ly, 2)),
                (0.0, round(part.ly, 2))}
        if corners == rect:
            return None                 # plain rectangle: WerkStck covers it
    return elems


def check_flat(part):
    """The script assumes the part already lies flat: thickness along Z.

    Nothing is rotated out of plane to fix it -- that would contradict the
    layout the definition produced -- but a part fed in on edge would quietly
    yield a program with the wrong size and the wrong drilling, so say so.
    """
    dims = (part.lx, part.ly, part.lz)
    thin = min(range(3), key=lambda i: dims[i])
    if thin != 2 and dims[thin] < 0.6 * sorted(dims)[1]:
        part.notes.append(
            "WARNING: this part is not lying flat in XY - its thinnest "
            "direction is %s (%s mm), so DI reads %s mm. Size and drilling "
            "below are almost certainly wrong."
            % ("XYZ"[thin], fnum(dims[thin]), fnum(part.lz)))


def brep_to_part(brep):
    part = Part()
    if brep is None or not brep.IsValid:
        raise ValueError("invalid Brep")

    corners, holes, planars = read_brep(brep, part.notes)
    corners = place(corners, holes, planars, part.notes)

    x0, y0, z0, x1, y1, z1 = _bbox(corners, holes)
    part.lx, part.ly = x1 - x0, y1 - y0
    part.lz = (z1 - z0) if THICKNESS is None else THICKNESS
    if part.lx < 1.0 or part.ly < 1.0 or part.lz < 0.5:
        raise ValueError("implausible part size %s x %s x %s mm"
                         % (fnum(part.lx), fnum(part.ly), fnum(part.lz)))
    check_flat(part)

    for hole in holes:
        emit_hole(part, hole)
    part.macros.sort(key=lambda m: (m[0],
                                    float(dict(m[2]).get("XA", 0)),
                                    float(dict(m[2]).get("YA", 0))))
    if CONTOUR:
        part.contour = outline(planars, part)
    return part


def describe(part):
    counts = {}
    for _mid, name, _p in part.macros:
        counts[name] = counts.get(name, 0) + 1
    detail = ", ".join("%d x %s" % (v, k) for k, v in sorted(counts.items()))
    if part.contour:
        detail += (", " if detail else "") + "contour"
    text = "%s x %s x %s mm   %s" % (fnum(part.lx), fnum(part.ly),
                                     fnum(part.lz), detail or "no machining")
    for note in dict.fromkeys(part.notes):
        text += "\n  note: %s" % note
    return text


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


MPR = DataTree[object]()
INFO = DataTree[object]()

if UNITS is not None and UNITS != Rhino.UnitSystem.Millimeters:
    INFO.Add("WARNING: the document is not in millimetres (%s). woodWOP "
             "expects mm - every size below is wrong." % UNITS, GH_Path(0))

for path, items in branches_of(B):
    for brep in items:
        if brep is None:
            continue
        try:
            part = brep_to_part(brep)
            MPR.Add(render_mpr(part), path)
            INFO.Add(describe(part), path)
        except Exception as exc:
            MPR.Add(None, path)
            INFO.Add("ERROR: %s" % exc, path)
