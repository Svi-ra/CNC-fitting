# -*- coding: utf-8 -*-
r"""
gh_brep2holes.py -- Grasshopper Script component: raw Brep -> cut outlines.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   B      Brep     access = Tree   one part per branch
    output  C      -                        one curve per cut
    output  D      -                        depth per cut, float, mm

C and D are parallel trees: item *i* of a branch is the curve, item *i* of
the same branch in D is that cut's depth. The branch paths are the ones that
came in on B, so a part's curves come back on the part's own branch. Should a
branch hold more than one solid, their curves are appended in input order --
the trees stay parallel, but there is then nothing to say where one part's
curves end and the next one's begin.

Takes raw solids with no attached data: everything is read off the geometry.
Nothing here knows about the machine: no bit lists, no reachability, no
setups, no MPR.

**Sizes are read as millimetres**: the Rhino document is never consulted, so
its units are not checked either.

Nothing is moved. The curves come back where the solid is, so they lie over
the model as it stands.

What comes out
--------------
Everything cut into the part, and nothing else. Every hole, groove, pocket,
slot and cut-out is handed back as the curve of its own outline, projected
onto the face it was cut from, with how deep it goes alongside it on D.

    - a round hole comes out as its circle, at the hole's own diameter
    - a groove or a slot comes out as its outline, round ends and all
    - a pocket comes out as its outline, whatever shape it is

The only thing left out is the boundary: the outlines of the faces that make
up the outside of the part -- its two plane faces, its edges, any chamfer.
A planar face is taken for part of the outside when the whole solid lies on
one side of its plane. Every other planar face is the floor of something cut
into the part, and the outline of that floor is a curve we hand back.

Depth is measured from the face the cut was made from -- the outside face the
cut opens to, found by looking along the floor's own normal -- down to the
deepest the cut reaches: a dead-end hole gives its own depth, a hole that
goes right through gives the panel thickness, a groove gives the depth of its
floor. Where a cut has steps, each step is a curve of its own with its own
depth, so a counterbore comes back as two circles: the wide one at the
counterbore depth, the narrow one at the full depth of the bore.

Both ends of a cut that goes right through are the same cut, so it comes out
once, at the face it would be cut from -- of the two, the one looking most
towards +Z. Set BOTH_ENDS to have the far end as well.

A cut that goes right through *and* runs out to the edge of the part is part
of the part's own outline -- it is a notch in the boundary, not a loop of its
own -- so it does not come out as a curve. A groove or pocket that runs out
to an edge without going through does come out: its floor is still a face of
its own.

Anything read but not handed back is said on the component's `out` parameter
rather than in a stream of its own, so C and D carry geometry only.
"""

import math

import Rhino
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

MIN_DEPTH = 0.05    # shallower cuts are not cuts, mm
MIN_LENGTH = 0.5    # shorter outlines are seams and slivers, not cuts, mm

BOTH_ENDS = False   # True: a cut right through comes out at both faces

LIFT = 0.0          # raise each curve off the face by this much, mm, so it
                    # is not exactly coincident with the face (0 = in it)

SAMPLES = 96        # points sampled along an outline
REACH_SAMPLES = 24  # points sampled along a wall, to see how deep it goes

UP = (0.0, 0.0, 1.0)  # which way "the face it would be cut from" looks

FACE_TOL = 0.02     # "this face is on the outside of the part", mm

# Model tolerance for recognising planes, mm. Set here rather than read off
# the Rhino document, which ShapeDiver forbids -- so the model has to be in
# millimetres.
TOL = 0.001


# ---------------------------------------------------------------------------
# vector helpers -- plain 3-tuples, so no RhinoCommon operator overloading
# ---------------------------------------------------------------------------

def p3(p):
    return (p.X, p.Y, p.Z)


def vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def fnum(v, nd=3):
    """A size in a note: trimmed, e.g. 9.5 / 18 / 0."""
    try:
        v = round(float(v), nd)
    except (TypeError, ValueError):
        return "0"
    if abs(v) < 10 ** (-nd):
        v = 0.0
    s = ("%.*f" % (nd, v)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


# ---------------------------------------------------------------------------
# reading the Brep
# ---------------------------------------------------------------------------

INNER = Rhino.Geometry.BrepLoopType.Inner


def face_normal(face):
    """Outward normal of a face.

    BrepFace.NormalAt already honours the face's orientation flag -- it is
    the face's normal, not its underlying surface's -- so it is used as it
    is. Reversing it again for OrientationIsReversed points every reversed
    face into the material: a groove floor sawn from the underside then
    reads as one sawn from the top, and the groove lands in the other
    setup from the bores beside it (checked in Rhino 8: on a reversed floor
    BrepFace.NormalAt gives the outward -Z, the surface +Z).

    Only ever called on planar faces, where the normal is the same everywhere,
    so evaluating at the middle of the domain is safe even when the face is
    trimmed.
    """
    return p3(face.NormalAt(face.Domain(0).Mid, face.Domain(1).Mid))


def curve_points(crv, count=SAMPLES):
    """Points sampled along a curve."""
    if crv is None:
        return []
    pts = []
    ts = crv.DivideByCount(count, True)
    if ts:
        pts = [p3(crv.PointAt(t)) for t in ts]
    if not pts:
        pts = [p3(crv.PointAtStart), p3(crv.PointAtEnd)]
    return pts


def loop_edges(loop):
    """The edge indices one loop runs along."""
    out = []
    for trim in loop.Trims:
        edge = trim.Edge
        if edge is not None:
            out.append(edge.EdgeIndex)
    return out


def face_edges(face):
    """The edge indices round the whole of one face."""
    out = []
    for loop in face.Loops:
        out.extend(loop_edges(loop))
    return out


def face_reach(face, direction, count=REACH_SAMPLES):
    """How far along `direction` the near side of this face reaches.

    Sampled round the face's loops rather than taken off its bounding box,
    which is square to the world and would over-reach on a part lying at an
    angle. The loops carry the far end of a wall and the tip of a conical
    drill bottom, which is all we are after.
    """
    best = None
    for loop in face.Loops:
        for p in curve_points(loop.To3dCurve(), count):
            d = vdot(p, direction)
            if best is None or d < best:
                best = d
    return best


class Planar(object):
    """A planar face, and what the part looks like along its normal.

    `extent` is how far the part reaches that way. A face that sits at the
    extent has the whole solid behind it and is part of the outside of the
    part; any other planar face is the floor of something cut into it, and
    `extent` is then the plane of the outside face that cut opens to.
    """

    def __init__(self, index, face, normal, offset, extent):
        self.index = index
        self.face = face
        self.normal = normal
        self.offset = offset
        self.extent = extent
        self.outside = offset >= extent - FACE_TOL

    def shift(self):
        """How far to move a curve in this plane out onto the entry face."""
        return self.extent - self.offset


def planar_faces(brep):
    """Every planar face of the solid, told outside from floor."""
    pts = [p3(v.Location) for v in brep.Vertices]
    if not pts:
        raise ValueError("the solid has no vertices")
    out = []
    for i, face in enumerate(brep.Faces):
        ok, plane = face.TryGetPlane(TOL)
        if not ok:
            continue
        normal = face_normal(face)
        out.append(Planar(i, face, normal, vdot(p3(plane.Origin), normal),
                          max(vdot(p, normal) for p in pts)))
    if not out:
        raise ValueError("the solid has no planar faces - not a flat part")
    return out


def is_floor(face, direction):
    """Is this face square across `direction` -- the bottom of a cut?"""
    ok, _plane = face.TryGetPlane(TOL)
    if not ok:
        return False
    return abs(abs(vdot(face_normal(face), direction)) - 1.0) <= 1e-3


def cavity(brep, loop, direction, outside):
    """The faces of the cut that opens at one loop.

    Walks out of the loop and on through whatever it meets, stopping at -- but
    taking in -- any face square across `direction`, which is the bottom of
    the cut, and any face of the outside of the part, which the walk must
    never cross. Stopping at the bottom is what keeps the steps of a cut
    apart: the walk out of a counterbore mouth gets as far as the counterbore
    floor and no further, so that step is measured on its own.

    Comes back as (walls, bottoms): the faces walked through, and the floors
    square across `direction` that it stopped at.
    """
    walls, bottoms, seen = set(), set(), set()
    queue = []
    for e in loop_edges(loop):
        queue.extend(brep.Edges[e].AdjacentFaces())
    while queue:
        fi = queue.pop()
        if fi in seen:
            continue
        seen.add(fi)
        face = brep.Faces[fi]
        if is_floor(face, direction):
            bottoms.add(fi)
            continue
        if fi in outside:
            continue            # the skin of the part: never walk through it
        walls.add(fi)
        for e in face_edges(face):
            queue.extend(brep.Edges[e].AdjacentFaces())
    return walls, bottoms


def flatten(crv, direction, shift):
    """A copy of the outline, moved out onto the face the cut was made from."""
    out = crv.DuplicateCurve()
    move = vmul(direction, shift + LIFT)
    out.Translate(Rhino.Geometry.Vector3d(move[0], move[1], move[2]))
    return out


def brep_to_cuts(brep, notes):
    """One Brep -> [(curve, depth), ...], in a settled order."""
    if brep is None or not brep.IsValid:
        raise ValueError("invalid Brep")

    levels = planar_faces(brep)
    outside = set(lv.index for lv in levels if lv.outside)

    # The outside of the part first, so a cut right through is measured from
    # the face it would be made from rather than from inside some pocket, and
    # of the two faces of a through cut, the one looking most towards +Z.
    levels.sort(key=lambda lv: (0 if lv.outside else 1,
                                -round(vdot(lv.normal, UP), 6),
                                -round(lv.offset, 6), lv.index))

    found = []
    covered = set()             # floors already spoken for by a mouth above
    spent = set()               # edges already walked, so the far end of a
                                # cut right through is not read a second time

    # Every loop cut into a face is the mouth of something: a hole, a groove,
    # a pocket, a cut-out. The outer loop of a face is never one -- on the
    # outside of the part it is the boundary, and on a floor it is the cut's
    # own outline, which comes out below.
    for lv in levels:
        for loop in lv.face.Loops:
            if loop.LoopType != INNER:
                continue
            crv = loop.To3dCurve()
            if crv is None:
                continue
            edges = loop_edges(loop)
            if not BOTH_ENDS and any(e in spent for e in edges):
                continue        # the far end of a cut already handed back
            walls, bottoms = cavity(brep, loop, lv.normal, outside)
            reach = None
            for fi in walls:
                d = face_reach(brep.Faces[fi], lv.normal)
                if d is not None and (reach is None or d < reach):
                    reach = d
            for fi in bottoms:
                d = vdot(p3(brep.Faces[fi].PointAt(
                    brep.Faces[fi].Domain(0).Mid,
                    brep.Faces[fi].Domain(1).Mid)), lv.normal)
                if reach is None or d < reach:
                    reach = d
            if reach is None:
                notes.append("a loop in the face at %s mm leads nowhere - "
                             "left out" % fnum(lv.offset))
                continue
            depth = lv.extent - reach
            if depth < MIN_DEPTH or crv.GetLength() < MIN_LENGTH:
                continue
            for fi in walls:
                spent.update(face_edges(brep.Faces[fi]))
            covered.update(fi for fi in bottoms if fi not in outside)
            found.append((flatten(crv, lv.normal, lv.shift()), depth))

    # The floors themselves. One under a mouth we have just handed back is
    # that same cut seen from below, so it is already covered; one that is
    # not is a cut with no mouth of its own -- a groove or a pocket running
    # out to the edge of the part, where the opening is a notch in the
    # boundary rather than a loop.
    for lv in levels:
        if lv.outside or lv.index in covered:
            continue
        crv = lv.face.OuterLoop.To3dCurve()
        if crv is None:
            continue
        depth = lv.shift()
        if depth < MIN_DEPTH or crv.GetLength() < MIN_LENGTH:
            continue
        found.append((flatten(crv, lv.normal, depth), depth))

    # The same solid in gives the same order out, wherever in the face list
    # its cuts happened to turn up.
    def where(item):
        box = item[0].GetBoundingBox(True)
        return (round(box.Min.X, 3), round(box.Min.Y, 3), round(box.Min.Z, 3),
                round(item[1], 3))

    found.sort(key=where)
    return [(crv, round(depth, 3)) for crv, depth in found]


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


C = DataTree[object]()
D = DataTree[object]()

for path, items in branches_of(B):
    for brep in items:
        if brep is None:
            continue
        notes = []
        try:
            for curve, depth in brep_to_cuts(brep, notes):
                C.Add(curve, path)
                D.Add(depth, path)
        except Exception as exc:
            notes.append("ERROR: %s" % exc)
        # One line per thing worth saying, on `out`, so C and D stay geometry.
        for note in dict.fromkeys(notes):
            print("%s   %s" % (str(path).strip("{}"), note))
