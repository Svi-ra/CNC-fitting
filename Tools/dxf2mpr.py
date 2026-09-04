#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dxf2mpr.py -- batch converter DXF -> woodWOP MPR (MPR 4.x / woodWOP 4 .. 8).

Two input flavours are handled automatically:

  A) "Solid" DXF -- model space holds 3DSOLID / BODY / REGION entities.  That is
     what Rhino/Grasshopper (Pancake), Inventor, SolidWorks or Fusion write, and
     it is exactly what woodWOP DXF-Import cannot read.  This script decodes the
     embedded ACIS stream -- both the ASCII SAT form used up to DXF 2010 and the
     binary SAB/ASM form used from DXF 2013 on -- rebuilds the B-rep and derives:
         panel size                -> <100 \WerkStck\
         vertical drillings        -> <102 \BohrVert\
         drillings from below      -> <131 \UfluBohr\
         horizontal drillings      -> <103 \BohrHoriz\
         slanted drillings         -> <104 \BohrUniv\
         non rectangular outline   -> contour ]n + <105 \Konturfraesen\

  B) "2D layer" DXF -- flat geometry sorted onto woodWOP layer names
     (Werkstk_<t>, V_Bohr<m>_<d>, H_Bohr_<z>, V_Fraes_<z>T<n>, Geometrie_<z>).
     That is the layout woodWOP DXF-Import Basic itself expects.

woodWOP part coordinate system produced (coordinate system 0):
    origin = lower left corner of the part, on the underside
    X = length (LA / _BSX), Y = width (BR / _BSY), Z = 0 at the bottom face
    vertical drillings enter from the top face, TI = depth
    horizontal drillings: ZA = height above the bottom face

Parts that sit in an assembly orientation are laid down automatically: the
thinnest direction becomes Z, the longest becomes X, and a panel whose drilling
all comes from underneath is turned over.  Use --no-orient to switch that off.

Usage
-----
    python dxf2mpr.py PART.dxf
    python dxf2mpr.py C:\parts\*.dxf -o C:\out
    python dxf2mpr.py C:\parts -r -o C:\out --log convert.csv

Requires only the Python standard library (3.8+).
"""

from __future__ import annotations

import argparse
import binascii
import csv
import glob as globmod
import math
import os
import re
import struct
import sys
import traceback

EPS = 1e-9
GEO_TOL = 1e-4
FACE_TOL = 0.02          # "reaches the outer face", mm


# ---------------------------------------------------------------------------
# vector helpers (plain 3-tuples)
# ---------------------------------------------------------------------------

def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def vnorm(a):
    n = vlen(a)
    return (0.0, 0.0, 0.0) if n < EPS else (a[0] / n, a[1] / n, a[2] / n)


def canonical_axis(a):
    """Flip a direction so +Z and -Z count as the same axis."""
    a = vnorm(a)
    for c in a:
        if c > 1e-6:
            return a
        if c < -1e-6:
            return vmul(a, -1.0)
    return a


def perp_frame(axis):
    axis = vnorm(axis)
    ref = (0.0, 0.0, 1.0)
    if abs(vdot(axis, ref)) > 0.9:
        ref = (1.0, 0.0, 0.0)
    e1 = vnorm(vcross(axis, ref))
    return e1, vnorm(vcross(axis, e1))


def solve3(m, rhs):
    a = [row[:] + [rhs[i]] for i, row in enumerate(m)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        pv = a[col][col]
        for j in range(col, 4):
            a[col][j] /= pv
        for r in range(3):
            if r != col and a[r][col]:
                f = a[r][col]
                for j in range(col, 4):
                    a[r][j] -= f * a[col][j]
    return [a[0][3], a[1][3], a[2][3]]


def fit_circle_2d(pts):
    """Least squares circle. Returns (cx, cy, r) or None."""
    pts = list(pts)
    if len(pts) < 3:
        return None
    sxx = sxy = syy = sx = sy = sxz = syz = sz = 0.0
    n = float(len(pts))
    for x, y in pts:
        z = x * x + y * y
        sxx += x * x
        sxy += x * y
        syy += y * y
        sx += x
        sy += y
        sxz += x * z
        syz += y * z
        sz += z
    sol = solve3([[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]],
                 [-sxz, -syz, -sz])
    if sol is None:
        return None
    a, b, c = sol
    cx, cy = -a / 2.0, -b / 2.0
    r2 = cx * cx + cy * cy - c
    if r2 <= 0:
        return None
    return cx, cy, math.sqrt(r2)


def circle_from_points(pts):
    """Fit a circle through >=3 coplanar 3D points -> (centre, radius, normal)."""
    if len(pts) < 3:
        return None
    nrm = None
    for i in range(1, len(pts) - 1):
        cand = vcross(vsub(pts[i], pts[0]), vsub(pts[i + 1], pts[0]))
        if vlen(cand) > 1e-7:
            nrm = vnorm(cand)
            break
    if nrm is None:
        return None
    e1, e2 = perp_frame(nrm)
    flat = [(vdot(p, e1), vdot(p, e2)) for p in pts]
    res = fit_circle_2d(flat)
    if res is None:
        return None
    cx, cy, r = res
    if r < 0.05 or r > 5000.0:
        return None
    for x, y in flat:
        if abs(math.hypot(x - cx, y - cy) - r) > max(0.01, r * 0.02):
            return None
    d = vdot(pts[0], nrm)
    centre = vadd(vadd(vmul(e1, cx), vmul(e2, cy)), vmul(nrm, d))
    return centre, r, nrm


# ---------------------------------------------------------------------------
# DXF reading
# ---------------------------------------------------------------------------

class ConvertError(Exception):
    pass


def read_dxf_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:18] == b"AutoCAD Binary DXF":
        raise ConvertError(
            "this is a binary DXF - re-export as ASCII DXF (R12 or 2000)")
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def read_tags(path):
    txt = read_dxf_text(path).replace("\r\n", "\n").replace("\r", "\n")
    lines = txt.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    tags = []
    i = 0
    n = len(lines)
    while i + 1 < n:
        raw = lines[i].strip()
        val = lines[i + 1]
        i += 2
        if raw == "":
            continue
        try:
            tags.append((int(raw), val))
        except ValueError:
            raise ConvertError(
                "malformed DXF: group code expected near line %d (%r)"
                % (i - 1, lines[i - 2][:40]))
    return tags


class Ent:
    __slots__ = ("type", "tags")

    def __init__(self, etype):
        self.type = etype
        self.tags = []

    def first(self, code, default=None):
        for c, v in self.tags:
            if c == code:
                return v
        return default

    def num(self, code, default=0.0):
        v = self.first(code)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def ints(self, code, default=0):
        v = self.first(code)
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    @property
    def layer(self):
        return (self.first(8) or "0").strip()


def parse_structure(tags):
    """Split the tag stream into model space entities, blocks and ACDS blobs."""
    entities = []
    blocks = {}
    acds = {}                      # owner handle -> raw bytes
    section = None
    cur_block = None
    cur_list = None
    ent = None
    acds_owner = None
    acds_kind = None
    acds_hex = None

    i = 0
    n = len(tags)
    while i < n:
        code, val = tags[i]
        sval = val.strip()

        if code == 0 and sval == "SECTION":
            ent = None
            section = None
            if i + 1 < n and tags[i + 1][0] == 2:
                section = tags[i + 1][1].strip()
                i += 2
                continue
        elif code == 0 and sval == "ENDSEC":
            _flush_acds(acds, acds_owner, acds_kind, acds_hex)
            acds_owner = acds_kind = acds_hex = None
            ent = None
            section = None
            cur_block = cur_list = None
            i += 1
            continue

        if section == "ENTITIES":
            if code == 0:
                ent = Ent(sval)
                entities.append(ent)
            elif ent is not None:
                ent.tags.append((code, val))

        elif section == "BLOCKS":
            if code == 0:
                if sval == "BLOCK":
                    cur_block = Ent("BLOCK")
                    cur_list = []
                    ent = cur_block
                elif sval == "ENDBLK":
                    if cur_block is not None:
                        bname = (cur_block.first(2) or "").strip()
                        if bname:
                            blocks[bname.upper()] = cur_list
                    cur_block = cur_list = None
                    ent = None
                else:
                    ent = Ent(sval)
                    if cur_list is not None:
                        cur_list.append(ent)
            elif ent is not None:
                ent.tags.append((code, val))

        elif section == "ACDSDATA":
            if code == 0 or code == 101:
                _flush_acds(acds, acds_owner, acds_kind, acds_hex)
                acds_owner = acds_kind = acds_hex = None
            elif code == 320:
                acds_owner = sval
            elif code == 2:
                acds_kind = sval
            elif code == 310:
                if acds_hex is None:
                    acds_hex = []
                acds_hex.append(sval)

        i += 1

    _flush_acds(acds, acds_owner, acds_kind, acds_hex)
    return entities, blocks, acds


def _flush_acds(acds, owner, kind, hexparts):
    if not hexparts or kind not in ("ASM_Data", "AcDbDs::Binary"):
        return
    try:
        data = binascii.unhexlify("".join(hexparts))
    except (binascii.Error, ValueError):
        return
    key = owner or ("#%d" % len(acds))
    acds[key] = data


# ---------------------------------------------------------------------------
# ACIS: SAT (ascii) and SAB (binary) -> one common record table
# ---------------------------------------------------------------------------

class Rec:
    __slots__ = ("idx", "type", "toks", "raw")

    def __init__(self, idx, rtype, toks, raw):
        self.idx = idx
        self.type = rtype
        self.toks = toks
        self.raw = raw

    def f(self, i):
        j = i + 1
        return self.toks[j] if j < len(self.toks) else None


def ptr(tok):
    if not tok or not tok.startswith("$"):
        return None
    try:
        v = int(tok[1:])
    except ValueError:
        return None
    return None if v < 0 else v


def acis_decode(text):
    """Undo the ASCII obfuscation AutoCAD applies to SAT data inside DXF."""
    out = []
    for ch in text:
        o = ord(ch)
        out.append(chr(0x9F - o) if 0x20 < o < 0x7F else ch)
    return "".join(out)


SAT_HEADER_RE = re.compile(r"^\s*-?\d+\s+\d+\s+\d+\s+\d+\s*$")


def acis_sat_text(ent):
    parts = [v for c, v in ent.tags if c in (1, 3)]
    if not parts:
        return None
    raw = "\n".join(parts)
    dec = acis_decode(raw)
    for cand in (dec, raw):
        if SAT_HEADER_RE.match(cand.split("\n", 1)[0]):
            return cand
    return None


def parse_sat(text):
    """ASCII SAT -> {index: Rec}."""
    lines = text.split("\n")
    body = "\n".join(lines[3:]) if len(lines) > 3 else ""
    recs = {}
    auto = 0
    for chunk in body.split("#"):
        s = chunk.strip()
        if not s:
            continue
        toks = s.split()
        if toks[0].startswith("-") and toks[0][1:].isdigit():
            idx = int(toks[0][1:])
            toks = toks[1:]
            if not toks:
                continue
        else:
            idx = auto
        auto = idx + 1
        recs[idx] = Rec(idx, toks[0], toks, s)
    return recs


SAB_SIG = b"ACIS BinaryFile"


def parse_sab(data):
    """Binary SAB/ASM -> {index: Rec} with SAT compatible field order."""
    start = data.find(SAB_SIG)
    if start < 0:
        return {}
    p = start + len(SAB_SIG) + 16          # signature + 4 header int32
    n = len(data)
    records = []
    cur = None
    namebuf = []
    depth = 0

    while p < n:
        t = data[p]
        p += 1
        tok = None
        if t in (0x04, 0x05, 0x15):
            tok = str(struct.unpack_from("<i", data, p)[0])
            p += 4
        elif t in (0x06, 0x16):
            tok = repr(struct.unpack_from("<d", data, p)[0])
            p += 8
        elif t in (0x07, 0x08, 0x09):
            ln = data[p]
            p += 1
            tok = "@" + data[p:p + ln].decode("latin-1")
            p += ln
        elif t == 0x0A:
            tok = "reversed"
        elif t == 0x0B:
            tok = "forward"
        elif t == 0x0C:
            tok = "$%d" % struct.unpack_from("<i", data, p)[0]
            p += 4
        elif t in (0x0D, 0x0E):
            ln = data[p]
            p += 1
            nm = data[p:p + ln].decode("latin-1")
            p += ln
            if t == 0x0E:
                namebuf.append(nm)
                continue
            full = "-".join(namebuf + [nm])
            namebuf = []
            if depth == 0:
                if cur:
                    records.append(cur)
                cur = [full]
                continue
            tok = full
        elif t in (0x0F, 0x17):
            depth += 1
            tok = "{"
        elif t in (0x10, 0x18):
            depth -= 1
            tok = "}"
        elif t == 0x11:
            if cur:
                records.append(cur)
            cur = None
            depth = 0
            continue
        elif t == 0x12:
            ln = struct.unpack_from("<I", data, p)[0]
            p += 4
            tok = "@" + data[p:p + ln].decode("latin-1")
            p += ln
        elif t in (0x13, 0x14):
            v = struct.unpack_from("<3d", data, p)
            p += 24
            if cur is not None:
                cur.extend(repr(x) for x in v)
            continue
        else:
            break                                    # unknown tag: stop safely
        if cur is not None:
            cur.append(tok)
    if cur:
        records.append(cur)

    records = [r for r in records if r and not r[0].startswith("@")]
    recs = {}
    for idx, toks in enumerate(records):
        toks = _sab_to_sat(toks)
        recs[idx] = Rec(idx, toks[0], toks, " ".join(toks))
    return recs


def _sab_to_sat(toks):
    """Drop the SAB-only id/back-pointer so field positions match SAT 4.0."""
    typ = toks[0]
    rest = toks[1:]
    # SAB writes  <attrib ptr> <entity id> <extra back ptr> <SAT fields...>
    if len(rest) >= 2 and re.fullmatch(r"-?\d+", rest[1] or ""):
        rest = [rest[0]] + rest[2:]                  # entity id
    if len(rest) >= 2 and rest[1].startswith("$") and typ != "transform":
        rest = [rest[0]] + rest[2:]                  # extra back pointer
    if typ == "vertex":
        ptrs = [t for t in rest if t.startswith("$")]
        return [typ] + ptrs[:3]
    if typ == "edge":
        ptrs = [t for t in rest if t.startswith("$")]
        sense = "forward"
        for t in rest:
            if t in ("forward", "reversed"):
                sense = t
                break
        return [typ] + ptrs[:5] + [sense]
    return [typ] + rest


# --- NURBS blobs (identical structure in SAT and SAB) ----------------------

def _blob(raw):
    a = raw.find("{")
    b = raw.rfind("}")
    if a < 0 or b < a:
        return None
    return raw[a + 1:b].split()


def _read_knots(toks, p, count):
    total = 0
    for _ in range(count):
        float(toks[p])
        total += int(float(toks[p + 1]))
        p += 2
    return total, p


def parse_spline_surface(raw):
    """ACIS spline-surface -> dict(du, dv, nu, nv, cps[(x,y,z,w)])."""
    toks = _blob(raw)
    if not toks:
        return None
    if toks[0] == "exactsur":
        p = 1
    elif toks[0] == "exact_spl_sur":
        p = 3                                   # + version, flag
    else:
        return None
    try:
        kind = toks[p]
        if kind not in ("nubs", "nurbs"):
            return None
        p += 1
        du = int(toks[p])
        dv = int(toks[p + 1])
        p += 2
        rational = toks[p] if kind == "nurbs" else "none"
        if kind == "nurbs":
            p += 1
        p += 4                                  # form_u form_v sing_u sing_v
        nku = int(toks[p])
        nkv = int(toks[p + 1])
        p += 2
        mu, p = _read_knots(toks, p, nku)
        mv, p = _read_knots(toks, p, nkv)
    except (ValueError, IndexError):
        return None

    nu = mu + 2 - du - 1
    nv = mv + 2 - dv - 1
    if nu < 2 or nv < 2 or nu * nv > 20000:
        return None
    wide = 4 if kind == "nurbs" else 3
    if p + nu * nv * wide > len(toks):
        return None
    cps = []
    for k in range(nu * nv):
        b = p + k * wide
        try:
            cps.append((float(toks[b]), float(toks[b + 1]), float(toks[b + 2]),
                        float(toks[b + 3]) if wide == 4 else 1.0))
        except ValueError:
            return None
    return {"du": du, "dv": dv, "nu": nu, "nv": nv, "cps": cps,
            "rational": rational}


def parse_spline_curve(raw):
    """ACIS intcurve / exactcur -> dict(deg, cps[(x,y,z,w)])."""
    toks = _blob(raw)
    if not toks:
        return None
    if toks[0] == "exactcur":
        p = 1
    elif toks[0] in ("exact_int_cur", "exactcur_int"):
        p = 3
    else:
        return None
    try:
        kind = toks[p]
        if kind not in ("nubs", "nurbs"):
            return None
        p += 1
        deg = int(toks[p])
        p += 2                                  # degree, form
        nk = int(toks[p])
        p += 1
        mult, p = _read_knots(toks, p, nk)
    except (ValueError, IndexError):
        return None
    cnt = mult + 2 - deg - 1
    if cnt < 2 or cnt > 5000:
        return None
    wide = 4 if kind == "nurbs" else 3
    if p + cnt * wide > len(toks):
        return None
    cps = []
    for k in range(cnt):
        b = p + k * wide
        try:
            cps.append((float(toks[b]), float(toks[b + 1]), float(toks[b + 2]),
                        float(toks[b + 3]) if wide == 4 else 1.0))
        except ValueError:
            return None
    return {"deg": deg, "cps": cps}


def on_circle_points(cps):
    """Control points that really lie on the circle of a rational conic."""
    on = [p[:3] for p in cps if abs(p[3] - 1.0) < 1e-6]
    if len(on) >= 3:
        return on
    out = list(on)
    for i in range(0, len(cps) - 2, 2):
        p0, p1, p2 = cps[i], cps[i + 1], cps[i + 2]
        w = p1[3]
        if w <= EPS:
            continue
        mid = vmul(vadd(vadd(p0[:3], vmul(p1[:3], 2.0 * w)), p2[:3]),
                   1.0 / (2.0 + 2.0 * w))
        out.extend([p0[:3], mid, p2[:3]])
    return out


# ---------------------------------------------------------------------------
# B-rep -> Shape (what we actually machine)
# ---------------------------------------------------------------------------

class Hole:
    def __init__(self, axis, base, radius, tmin, tmax):
        self.axis = axis                # unit, canonical
        self.base = base                # point on the axis nearest the origin
        self.radius = radius
        self.tmin = tmin
        self.tmax = tmax

    def key(self, nd=3):
        return (tuple(round(c, nd) for c in self.axis),
                tuple(round(c, nd) for c in self.base),
                round(self.radius, nd))

    def low(self):
        return vadd(self.base, vmul(self.axis, self.tmin))

    def high(self):
        return vadd(self.base, vmul(self.axis, self.tmax))


class Shape:
    """One solid body reduced to what a woodWOP program needs."""

    def __init__(self):
        self.points = []            # every vertex of the body
        self.holes = []             # merged cylinders
        self.plane_loops = []       # (normal, [ [seg, ...], ... ])
        self.notes = []

    def rotate(self, fn):
        self.points = [fn(p) for p in self.points]
        for h in self.holes:
            lo, hi = fn(h.low()), fn(h.high())
            ax = canonical_axis(vsub(hi, lo))
            base = vsub(lo, vmul(ax, vdot(lo, ax)))
            t0, t1 = vdot(lo, ax), vdot(hi, ax)
            h.axis, h.base = ax, base
            h.tmin, h.tmax = min(t0, t1), max(t0, t1)
        newloops = []
        for nrm, loops in self.plane_loops:
            nl = []
            for loop in loops:
                nl.append([{"p0": fn(s["p0"]), "p1": fn(s["p1"]),
                            "r": s["r"],
                            "c": fn(s["c"]) if s["c"] else None,
                            "n": fn(s["n"]) if s["n"] else None,
                            "m": fn(s["m"]) if s["m"] else None}
                           for s in loop])
            newloops.append((fn(nrm), nl))
        self.plane_loops = newloops

    def bbox(self):
        pts = list(self.points)
        for h in self.holes:
            pts.append(h.low())
            pts.append(h.high())
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _identity():
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0), 1.0)


def _parse_transform(r):
    try:
        v = [float(r.f(i)) for i in range(1, 14)]
    except (TypeError, ValueError):
        return _identity()
    return ((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8]),
            (v[9], v[10], v[11]), v[12] if abs(v[12]) > EPS else 1.0)


def _apply(x, p):
    r0, r1, r2, t, s = x
    return vadd(vmul((vdot(r0, p), vdot(r1, p), vdot(r2, p)), s), t)


def _apply_dir(x, d):
    r0, r1, r2, _t, _s = x
    return vnorm((vdot(r0, d), vdot(r1, d), vdot(r2, d)))


def build_shapes(recs):
    """One Shape per ACIS body record."""
    shapes = []
    for bi in sorted(i for i, r in recs.items() if r.type == "body"):
        body = recs[bi]
        xform = _identity()
        tp = ptr(body.f(3))
        if tp is not None and tp in recs and recs[tp].type == "transform":
            xform = _parse_transform(recs[tp])
        faces = _body_faces(recs, body)
        if faces:
            shapes.append(_shape_from_faces(recs, faces, xform))
    return shapes


def _body_faces(recs, body):
    faces = []
    seen = set()
    lump = ptr(body.f(1))
    g = 0
    while lump is not None and lump in recs and g < 100000:
        g += 1
        lr = recs[lump]
        shell = ptr(lr.f(2))
        gs = 0
        while shell is not None and shell in recs and gs < 100000:
            gs += 1
            sr = recs[shell]
            face = ptr(sr.f(3))
            gf = 0
            while face is not None and face in recs and gf < 200000:
                gf += 1
                if face in seen:
                    break
                seen.add(face)
                faces.append(recs[face])
                face = ptr(recs[face].f(1))
            shell = ptr(sr.f(1))
        lump = ptr(lr.f(1))
    return faces


def _shape_from_faces(recs, faces, xform):
    shape = Shape()
    cylinders = []

    for fr in faces:
        loops = _face_loops(recs, fr, xform)
        for loop in loops:
            for seg in loop:
                shape.points.append(seg["p0"])

        si = ptr(fr.f(5))
        sr = recs.get(si) if si is not None else None
        if sr is None:
            continue

        if sr.type == "plane-surface":
            pl = _plane_of(sr, xform)
            if pl:
                shape.plane_loops.append((pl[1], loops))
        elif sr.type == "cone-surface":
            cyl = _cyl_from_cone(sr, loops, xform, shape.notes)
            if cyl:
                cylinders.append(cyl)
        elif sr.type == "spline-surface":
            cyl = _cyl_from_spline(sr, xform)
            if cyl is None:
                cyl = _cyl_from_loops(loops)     # e.g. SAB "ref" surfaces
            if cyl:
                cylinders.append(cyl)
            else:
                shape.notes.append(
                    "free-form face ignored (not a cylinder)")
        elif sr.type in ("sphere-surface", "torus-surface"):
            shape.notes.append("%s ignored - no matching woodWOP macro"
                               % sr.type)

    shape.holes = _merge_cylinders(cylinders)
    return shape


def _merge_cylinders(cyls):
    groups = {}
    for c in cyls:
        k = c.key()
        if k in groups:
            g = groups[k]
            g.tmin = min(g.tmin, c.tmin)
            g.tmax = max(g.tmax, c.tmax)
        else:
            groups[k] = Hole(c.axis, c.base, c.radius, c.tmin, c.tmax)
    return [h for h in groups.values() if h.tmax - h.tmin > 0.05]


def _plane_of(sr, xform):
    try:
        pt = (float(sr.f(1)), float(sr.f(2)), float(sr.f(3)))
        nr = (float(sr.f(4)), float(sr.f(5)), float(sr.f(6)))
    except (TypeError, ValueError):
        return None
    return _apply(xform, pt), _apply_dir(xform, nr)


def _cyl_from_cone(sr, loops, xform, notes):
    try:
        c = (float(sr.f(1)), float(sr.f(2)), float(sr.f(3)))
        ax = (float(sr.f(4)), float(sr.f(5)), float(sr.f(6)))
        mj = (float(sr.f(7)), float(sr.f(8)), float(sr.f(9)))
        ratio = float(sr.f(10))
        sine = float(sr.f(11))
    except (TypeError, ValueError):
        return None
    if abs(sine) > 1e-6:
        notes.append("conical face ignored (countersink / chamfer)")
        return None
    if abs(ratio - 1.0) > 1e-6:
        notes.append("elliptical cylinder ignored")
        return None
    r = vlen(mj) * xform[4]
    if r < EPS:
        return None
    pts = []
    for loop in loops:
        for s in loop:
            pts.append(s["p0"])
            pts.append(s["p1"])
    return _mk_cyl(_apply_dir(xform, ax), _apply(xform, c), r, pts)


def _cyl_from_spline(sr, xform):
    sp = parse_spline_surface(sr.raw)
    if not sp:
        return None
    nu, nv, cps = sp["nu"], sp["nv"], sp["cps"]

    def cp(u, v):
        return cps[v * nu + u]

    if sp["du"] == 1 and nu == 2:
        axis = vsub(cp(1, 0)[:3], cp(0, 0)[:3])
        ring = [cp(0, v) for v in range(nv)]
    elif sp["dv"] == 1 and nv == 2:
        axis = vsub(cp(0, 1)[:3], cp(0, 0)[:3])
        ring = [cp(u, 0) for u in range(nu)]
    else:
        return None
    if vlen(axis) < EPS:
        return None

    on = [_apply(xform, p) for p in on_circle_points(ring)]
    fit = circle_from_points(on)
    if fit is None:
        return None
    centre, radius, _n = fit
    allpts = [_apply(xform, p[:3]) for p in cps]
    return _mk_cyl(_apply_dir(xform, axis), centre, radius, allpts)


def _cyl_from_loops(loops):
    """Recover a cylinder from the circular edges bounding the face."""
    circles = []
    pts = []
    for loop in loops:
        for s in loop:
            pts.append(s["p0"])
            pts.append(s["p1"])
            if s["r"] and s["c"] and s["n"]:
                circles.append((s["c"], s["r"], s["n"]))
    if not circles:
        return None
    axis = canonical_axis(circles[0][2])
    radius = circles[0][1]
    for _c, r, n in circles[1:]:
        if abs(r - radius) > 0.01 or abs(abs(vdot(canonical_axis(n), axis))
                                         - 1.0) > 1e-3:
            return None
    return _mk_cyl(axis, circles[0][0], radius, pts)


def _mk_cyl(axis, centre_any, radius, pts):
    axis = canonical_axis(axis)
    if vlen(axis) < EPS or not pts:
        return None
    base = vsub(centre_any, vmul(axis, vdot(centre_any, axis)))
    ts = [vdot(p, axis) for p in pts]
    return Hole(axis, base, radius, min(ts), max(ts))


def _face_loops(recs, face_rec, xform):
    loops = []
    lp = ptr(face_rec.f(2))
    g = 0
    while lp is not None and lp in recs and g < 10000:
        g += 1
        lr = recs[lp]
        segs = _walk_loop(recs, lr, xform)
        if segs:
            loops.append(segs)
        lp = ptr(lr.f(1))
    return loops


def _walk_loop(recs, loop_rec, xform):
    start = ptr(loop_rec.f(2))
    if start is None or start not in recs:
        return []
    out = []
    ce = start
    g = 0
    while ce is not None and ce in recs and g < 20000:
        g += 1
        cr = recs[ce]
        ei = ptr(cr.f(4))
        forward = (cr.f(5) or "forward") == "forward"
        if ei is not None and ei in recs:
            seg = _edge_segment(recs, recs[ei], xform)
            if seg:
                if not forward:
                    seg = {"p0": seg["p1"], "p1": seg["p0"], "r": seg["r"],
                           "c": seg["c"], "n": seg["n"], "m": seg["m"]}
                out.append(seg)
        ce = ptr(cr.f(1))
        if ce == start:
            break
    return out


def _edge_segment(recs, er, xform):
    p0 = _vertex_point(recs, ptr(er.f(1)), xform)
    p1 = _vertex_point(recs, ptr(er.f(2)), xform)
    if p0 is None or p1 is None:
        return None
    ci = ptr(er.f(4))
    arc = _arc_of_curve(recs.get(ci) if ci is not None else None, xform)
    if (er.f(5) or "forward") != "forward":
        p0, p1 = p1, p0
    if arc:
        return {"p0": p0, "p1": p1, "r": arc[1], "c": arc[0], "n": arc[2],
                "m": arc[3]}
    return {"p0": p0, "p1": p1, "r": None, "c": None, "n": None, "m": None}


def _vertex_point(recs, vi, xform):
    if vi is None or vi not in recs:
        return None
    pi = ptr(recs[vi].f(2))
    if pi is None or pi not in recs:
        return None
    pr = recs[pi]
    try:
        return _apply(xform, (float(pr.f(1)), float(pr.f(2)), float(pr.f(3))))
    except (TypeError, ValueError):
        return None


def _arc_of_curve(cur, xform):
    """Return (centre, radius, normal, interior_point) for a circular arc."""
    if cur is None:
        return None
    if cur.type == "ellipse-curve":
        try:
            c = (float(cur.f(1)), float(cur.f(2)), float(cur.f(3)))
            nr = (float(cur.f(4)), float(cur.f(5)), float(cur.f(6)))
            mj = (float(cur.f(7)), float(cur.f(8)), float(cur.f(9)))
            ratio = float(cur.f(10))
        except (TypeError, ValueError):
            return None
        if abs(ratio - 1.0) > 1e-6:
            return None
        return (_apply(xform, c), vlen(mj) * xform[4],
                _apply_dir(xform, nr), None)
    if cur.type in ("intcurve-curve", "curve"):
        sc = parse_spline_curve(cur.raw)
        if not sc or sc["deg"] < 2:
            return None
        on = [_apply(xform, p) for p in on_circle_points(sc["cps"])]
        fit = circle_from_points(on)
        if fit is None:
            return None
        # a point strictly inside the arc, in curve order -> tells us which
        # way round the arc actually runs
        return fit[0], fit[1], fit[2], on[len(on) // 2]
    return None


# ---------------------------------------------------------------------------
# Shape -> woodWOP part
# ---------------------------------------------------------------------------

class Part:
    def __init__(self, name):
        self.name = name
        self.lx = self.ly = self.lz = 0.0
        self.macros = []
        self.contours = []
        self.notes = []


def _rot_x90(p):
    return (p[0], -p[2], p[1])


def _rot_y90(p):
    return (-p[2], p[1], p[0])


def _rot_z90(p):
    return (p[1], -p[0], p[2])


def _rot_x180(p):
    return (p[0], -p[1], -p[2])


def orient_shape(shape, opts):
    """Lay a panel flat: thinnest direction -> Z, longest -> X, drilling up."""
    if not opts.orient:
        return
    box = shape.bbox()
    if not box:
        return
    dims = [box[3] - box[0], box[4] - box[1], box[5] - box[2]]
    thin = min(range(3), key=lambda i: dims[i])
    others = sorted(d for i, d in enumerate(dims) if i != thin)
    if dims[thin] < 0.6 * others[0] and thin != 2:
        shape.rotate(_rot_y90 if thin == 0 else _rot_x90)
        shape.notes.append(
            "part laid flat (%s was the thickness direction)"
            % "XYZ"[thin])

    box = shape.bbox()
    if opts.long_x and (box[3] - box[0]) < (box[4] - box[1]) - GEO_TOL:
        shape.rotate(_rot_z90)
        shape.notes.append("part turned 90 deg so the long side runs along X")

    if opts.auto_flip:
        box = shape.bbox()
        zlo, zhi = box[2], box[5]
        top = bot = 0
        for h in shape.holes:
            if abs(abs(h.axis[2]) - 1.0) > 1e-3:
                continue
            if abs(h.high()[2] - zhi) <= FACE_TOL:
                top += 1
            elif abs(h.low()[2] - zlo) <= FACE_TOL:
                bot += 1
        if bot and not top:
            shape.rotate(_rot_x180)
            shape.notes.append(
                "part turned over so the drilling is done from above")


def shape_to_part(shape, name, opts):
    part = Part(name)
    orient_shape(shape, opts)
    part.notes.extend(shape.notes)

    box = shape.bbox()
    if not box:
        raise ConvertError("solid contains no usable geometry")
    x0, y0, z0, x1, y1, z1 = box

    if opts.normalize and (abs(x0) > GEO_TOL or abs(y0) > GEO_TOL
                           or abs(z0) > GEO_TOL):
        shape.rotate(lambda p: vsub(p, (x0, y0, z0)))
        part.notes.append("moved to the woodWOP zero point by (%s, %s, %s)"
                          % (fnum(-x0), fnum(-y0), fnum(-z0)))
        box = shape.bbox()
        x0, y0, z0, x1, y1, z1 = box

    part.lx = x1 - x0
    part.ly = y1 - y0
    part.lz = z1 - z0 if opts.thickness is None else opts.thickness
    if part.lx < 1.0 or part.ly < 1.0 or part.lz < 0.5:
        raise ConvertError(
            "implausible part size %s x %s x %s mm - wrong drawing units?"
            % (fnum(part.lx), fnum(part.ly), fnum(part.lz)))

    for h in shape.holes:
        _emit_hole(part, h, opts)

    if opts.contour:
        outline = _outline(shape, z1)
        if outline and not _is_bbox_rectangle(outline, part.lx, part.ly):
            part.contours.append(outline)

    part.macros.sort(key=lambda m: (m[0], _sort_key(m)))
    return part


def _sort_key(m):
    d = dict(m[2])
    try:
        return (float(d.get("XA", 0)), float(d.get("YA", 0)))
    except ValueError:
        return (0.0, 0.0)


def _emit_hole(part, hole, opts):
    dia = _snap(2.0 * hole.radius, opts)
    if dia > opts.max_dia:
        part.notes.append(
            "round opening d=%s treated as geometry, not as a drilling "
            "(over --max-dia)" % fnum(dia))
        return
    p0, p1 = hole.low(), hole.high()
    ax, ay, az = hole.axis
    thickness = part.lz

    # ---- vertical --------------------------------------------------------
    if abs(abs(az) - 1.0) < 1e-3:
        zlo, zhi = min(p0[2], p1[2]), max(p0[2], p1[2])
        x, y = p0[0], p0[1]
        open_top = abs(zhi - thickness) <= FACE_TOL
        open_bot = abs(zlo) <= FACE_TOL
        if open_top:
            depth = thickness if open_bot else thickness - zlo
            part.macros.append((102, "BohrVert", [
                ("XA", fnum(x)), ("YA", fnum(y)),
                ("TI", fnum(depth)), ("DU", fnum(dia)),
                ("BM", opts.bm_vert), ("S_", "2"),
                ("AN", "1"), ("AB", "0"), ("WI", "0")]))
        elif open_bot:
            part.macros.append((131, "UfluBohr", [
                ("XA", fnum(x)), ("YA", fnum(y)),
                ("DU", fnum(dia)), ("WI", "0"),
                ("TI", fnum(zhi)), ("AB", "0"), ("F_", "STANDARD")]))
        else:
            part.notes.append(
                "closed internal bore d=%s at X=%s Y=%s skipped (reaches no "
                "outer face)" % (fnum(dia), fnum(x), fnum(y)))
        return

    # ---- horizontal ------------------------------------------------------
    along_x = abs(abs(ax) - 1.0) < 1e-3
    along_y = abs(abs(ay) - 1.0) < 1e-3
    if abs(az) < 1e-3 and (along_x or along_y):
        i = 0 if along_x else 1
        lo, hi = (p0, p1) if p0[i] <= p1[i] else (p1, p0)
        limit = part.lx if along_x else part.ly
        if abs(lo[i]) <= FACE_TOL:
            bm = "XP" if along_x else "YP"
            entry = lo
        elif abs(hi[i] - limit) <= FACE_TOL:
            bm = "XM" if along_x else "YM"
            entry = hi
        else:
            part.notes.append(
                "internal horizontal bore d=%s skipped (reaches no edge)"
                % fnum(dia))
            return
        part.macros.append((103, "BohrHoriz", [
            ("XA", fnum(entry[0])), ("YA", fnum(entry[1])),
            ("ZA", fnum(entry[2])), ("DU", fnum(dia)),
            ("TI", fnum(hi[i] - lo[i])), ("BM", bm),
            ("AN", "1"), ("AB", "0"), ("F_", "STANDARD")]))
        return

    # ---- slanted ---------------------------------------------------------
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
    part.notes.append(
        "slanted bore exported as <104 BohrUniv> (CA=%s WI=%s) - needs a "
        "swivel drilling unit" % (fnum(ca), fnum(wi)))


def _snap(dia, opts):
    return round(dia / opts.snap) * opts.snap if opts.snap > 0 else dia


def _outline(shape, top_z):
    """Outer loop of the topmost horizontal face as MPR contour elements."""
    best = None
    best_z = None
    for nrm, loops in shape.plane_loops:
        if abs(abs(nrm[2]) - 1.0) > 1e-3 or not loops:
            continue
        z = max(s["p0"][2] for loop in loops for s in loop)
        if best_z is None or z > best_z + GEO_TOL:
            best_z, best = z, loops
    if not best or best_z is None or abs(best_z - top_z) > 0.5:
        return None

    scored = sorted(((abs(_area2d([s["p0"] for s in lp])), lp)
                     for lp in best), key=lambda t: t[0], reverse=True)
    loop = scored[0][1]

    elems = [("KP", {"X": cnum(loop[0]["p0"][0]), "Y": cnum(loop[0]["p0"][1]),
                     "Z": "0", "KO": "0"})]
    for s in loop:
        p1 = s["p1"]
        if s["r"] and s["c"]:
            elems.append(("KA", {"X": cnum(p1[0]), "Y": cnum(p1[1]),
                                 "R": cnum(s["r"]),
                                 "DS": str(_ds(s["p0"], p1, s["c"], s["m"]))}))
        else:
            elems.append(("KL", {"X": cnum(p1[0]), "Y": cnum(p1[1])}))
    return elems


TWO_PI = 2.0 * math.pi


def ds_code(ccw, sweep):
    """woodWOP DS (MPR parser constants _cc/_cw/_CC/_CW).

    0 = counter clockwise, small arc      2 = counter clockwise, big arc
    1 = clockwise, small arc              3 = clockwise, big arc
    """
    big = sweep > math.pi + 1e-9
    if ccw:
        return 2 if big else 0
    return 3 if big else 1


def _ds(p0, p1, centre, mid=None):
    """Direction code for an arc, using an interior point when we have one."""
    def ang(p):
        return math.atan2(p[1] - centre[1], p[0] - centre[0])

    a0 = ang(p0)
    d1 = (ang(p1) - a0) % TWO_PI
    if mid is not None:
        dm = (ang(mid) - a0) % TWO_PI
        if 1e-9 < dm < d1:
            return ds_code(True, d1)
        return ds_code(False, TWO_PI - d1)
    # no interior point: assume the shorter way round
    return ds_code(True, d1) if d1 <= math.pi else ds_code(False, TWO_PI - d1)


def _area2d(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _is_bbox_rectangle(elems, lx, ly):
    if len(elems) != 5 or any(k == "KA" for k, _ in elems):
        return False
    corners = {(round(float(d["X"]), 2), round(float(d["Y"]), 2))
               for _k, d in elems}
    return corners == {(0.0, 0.0), (round(lx, 2), 0.0),
                       (round(lx, 2), round(ly, 2)), (0.0, round(ly, 2))}


# ---------------------------------------------------------------------------
# route B: flat DXF on woodWOP layers
# ---------------------------------------------------------------------------

RE_WERK = re.compile(r"^(?:werkstk|procpart)_([0-9_.]+)", re.I)
RE_VBOHR = re.compile(r"^(?:v_bohr|v_drill)([0-9]*)(?:_([0-9_.]+))?$", re.I)
RE_HBOHR = re.compile(r"^(?:h_bohr|h_drill)_([0-9_.]+)", re.I)
RE_MILL = re.compile(r"^(?:v_fraes|v_trim|geometrie|geometry|nest)"
                     r"_(-?[0-9_.]+)(?:t([0-9]+))?", re.I)

DRILL_MODES = {"0": "LS", "1": "SS", "2": "LSL", "3": "SSS",
               "6": "LSU", "8": "LSLU", "": "LS"}


def _lnum(s):
    try:
        return float(s.replace("_", "."))
    except (ValueError, AttributeError):
        return None


def layers_to_part(entities, blocks, name, opts):
    part = Part(name)
    thickness = None
    rect = None
    drills = []
    hdrills = []
    mills = {}
    used = False

    for ent in entities:
        lay = ent.layer
        m = RE_WERK.match(lay)
        if m:
            used = True
            thickness = _lnum(m.group(1))
            pts = _entity_points(ent)
            if pts:
                rect = _bbox2(pts + ([(rect[0], rect[1]), (rect[2], rect[3])]
                                     if rect else []))
            continue
        m = RE_VBOHR.match(lay)
        if m and ent.type == "CIRCLE":
            used = True
            drills.append((ent.num(10), ent.num(20), 2.0 * ent.num(40),
                           _lnum(m.group(2)) if m.group(2) else None,
                           DRILL_MODES.get(m.group(1) or "", "LS")))
            continue
        m = RE_HBOHR.match(lay)
        if m:
            used = True
            hdrills.append((ent, _lnum(m.group(1))))
            continue
        m = RE_MILL.match(lay)
        if m:
            used = True
            mills.setdefault((_lnum(m.group(1)), m.group(2)), []).append(ent)

    if not used:
        return None

    if rect is None:
        allpts = []
        for ent in entities:
            allpts.extend(_entity_points(ent))
        if not allpts:
            raise ConvertError("no usable 2D geometry found")
        rect = _bbox2(allpts)
        part.notes.append("no Werkstk_/ProcPart_ layer - size taken from the "
                          "overall drawing extents")
    x0, y0, x1, y1 = rect
    part.lx, part.ly = x1 - x0, y1 - y0
    part.lz = (opts.thickness if opts.thickness is not None
               else (thickness if thickness else 19.0))
    if thickness is None and opts.thickness is None:
        part.notes.append("thickness not given by a layer name - assumed 19")
    off = (x0, y0) if opts.normalize else (0.0, 0.0)

    for x, y, dia, depth, bm in drills:
        part.macros.append((102, "BohrVert", [
            ("XA", fnum(x - off[0])), ("YA", fnum(y - off[1])),
            ("TI", fnum(depth if depth is not None else part.lz)),
            ("DU", fnum(_snap(dia, opts))), ("BM", bm), ("S_", "2"),
            ("AN", "1"), ("AB", "0"), ("WI", "0")]))

    for ent, z in hdrills:
        if ent.type != "INSERT":
            part.notes.append("H_Bohr layer: expected a block insert, found %s"
                              % ent.type)
            continue
        ang = ent.num(50, 0.0) % 360.0
        bm = {0: "XP", 90: "YP", 180: "XM", 270: "YM"}.get(round(ang))
        if bm is None:
            part.notes.append("H_Bohr block at %s deg skipped - only 0/90/180/"
                              "270 supported" % fnum(ang))
            continue
        dia = _attr(ent, "DU")
        depth = _attr(ent, "TI")
        if dia is None or depth is None:
            part.notes.append("H_Bohr block without DU/TI attributes - used "
                              "defaults %s x %s"
                              % (fnum(opts.hbore_dia), fnum(opts.hbore_depth)))
        part.macros.append((103, "BohrHoriz", [
            ("XA", fnum(ent.num(10) - off[0])),
            ("YA", fnum(ent.num(20) - off[1])),
            ("ZA", fnum(z if z is not None else part.lz / 2.0)),
            ("DU", fnum(dia if dia is not None else opts.hbore_dia)),
            ("TI", fnum(depth if depth is not None else opts.hbore_depth)),
            ("BM", bm), ("AN", "1"), ("AB", "0"), ("F_", "STANDARD")]))

    for (z, _tool), ents in sorted(mills.items(), key=lambda kv: kv[0][0] or 0):
        for loop in _chain_2d(ents, off):
            part.contours.append(loop)
            part.notes.append("contour at Z=%s -> <105 Konturfraesen>"
                              % fnum(z or 0.0))

    part.macros.sort(key=lambda m: (m[0], _sort_key(m)))
    return part


def _attr(ent, tag):
    want = tag.upper()
    pending = None
    for c, v in ent.tags:
        if c == 2:
            pending = v.strip().upper()
        elif c == 1 and pending == want:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def _bbox2(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _entity_points(ent):
    t = ent.type
    if t == "LINE":
        return [(ent.num(10), ent.num(20)), (ent.num(11), ent.num(21))]
    if t in ("CIRCLE", "ARC"):
        cx, cy, r = ent.num(10), ent.num(20), ent.num(40)
        return [(cx - r, cy - r), (cx + r, cy + r)]
    if t in ("LWPOLYLINE", "POLYLINE"):
        return [(p[0], p[1]) for p in _poly_vertices(ent)]
    if t in ("POINT", "INSERT"):
        return [(ent.num(10), ent.num(20))]
    return []


def _poly_vertices(ent):
    out = []
    x = y = None
    bulge = 0.0
    for c, v in ent.tags:
        if c == 10:
            if x is not None:
                out.append((x, y, bulge))
            try:
                x = float(v)
            except ValueError:
                x = 0.0
            y, bulge = 0.0, 0.0
        elif c == 20 and x is not None:
            try:
                y = float(v)
            except ValueError:
                y = 0.0
        elif c == 42 and x is not None:
            try:
                bulge = float(v)
            except ValueError:
                bulge = 0.0
    if x is not None:
        out.append((x, y, bulge))
    return out


def _chain_2d(ents, off):
    segs = []
    for ent in ents:
        if ent.type == "LINE":
            segs.append(("L", (ent.num(10) - off[0], ent.num(20) - off[1]),
                         (ent.num(11) - off[0], ent.num(21) - off[1]), None))
        elif ent.type == "ARC":
            # a DXF ARC always runs counter clockwise from start to end angle
            cx, cy, r = ent.num(10) - off[0], ent.num(20) - off[1], ent.num(40)
            a0, a1 = math.radians(ent.num(50)), math.radians(ent.num(51))
            segs.append(("A", (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                         (cx + r * math.cos(a1), cy + r * math.sin(a1)),
                         (r, True, (a1 - a0) % TWO_PI)))
        elif ent.type == "CIRCLE":
            cx, cy, r = ent.num(10) - off[0], ent.num(20) - off[1], ent.num(40)
            segs.append(("A", (cx + r, cy), (cx - r, cy), (r, True, math.pi)))
            segs.append(("A", (cx - r, cy), (cx + r, cy), (r, True, math.pi)))
        elif ent.type == "LWPOLYLINE":
            pts = [(v[0] - off[0], v[1] - off[1], v[2])
                   for v in _poly_vertices(ent)]
            closed = bool(ent.ints(70, 0) & 1)
            for i in range(len(pts) - 1 + (1 if closed else 0)):
                a, b = pts[i], pts[(i + 1) % len(pts)]
                if abs(a[2]) < 1e-9:
                    segs.append(("L", (a[0], a[1]), (b[0], b[1]), None))
                    continue
                theta = 4.0 * math.atan(a[2])
                chord = math.hypot(b[0] - a[0], b[1] - a[1])
                if chord < EPS:
                    continue
                r = abs(chord / (2.0 * math.sin(theta / 2.0)))
                segs.append(("A", (a[0], a[1]), (b[0], b[1]),
                             (r, a[2] > 0, abs(theta))))

    loops = []
    remaining = segs[:]
    while remaining:
        chain = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            tail = chain[-1][2]
            for i, s in enumerate(remaining):
                if _close2(s[1], tail):
                    chain.append(s)
                elif _close2(s[2], tail):
                    chain.append((s[0], s[2], s[1],
                                  None if s[3] is None
                                  else (s[3][0], not s[3][1], s[3][2])))
                else:
                    continue
                remaining.pop(i)
                changed = True
                break
        elems = [("KP", {"X": cnum(chain[0][1][0]), "Y": cnum(chain[0][1][1]),
                         "Z": "0", "KO": "0"})]
        for kind, _p0, p1, arc in chain:
            if kind == "L":
                elems.append(("KL", {"X": cnum(p1[0]), "Y": cnum(p1[1])}))
            else:
                elems.append(("KA", {"X": cnum(p1[0]), "Y": cnum(p1[1]),
                                     "R": cnum(arc[0]),
                                     "DS": str(ds_code(arc[1], arc[2]))}))
        if len(elems) > 1:
            loops.append(elems)
    return loops


def _close2(a, b):
    return abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01


# ---------------------------------------------------------------------------
# MPR output
# ---------------------------------------------------------------------------

def fnum(v, nd=3):
    try:
        v = round(float(v), nd)
    except (TypeError, ValueError):
        return "0"
    if abs(v) < 10 ** (-nd):
        v = 0.0
    s = ("%.*f" % (nd, v)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


def cnum(v, nd=4):
    """Contour element coordinate -- woodWOP writes these with 4 decimals."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0.0000"
    if abs(v) < 10 ** -(nd + 1):
        v = 0.0
    return "%.*f" % (nd, v)


SEP = " "


def render_mpr(part):
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

    for ci, elems in enumerate(part.contours, start=1):
        a("]%d" % ci)
        for ei, (kind, vals) in enumerate(elems):
            a("$E%d" % ei)
            a(kind)
            for k, v in vals.items():
                a("%s=%s" % (k, v))
            a(SEP)
    # contour element values carry no quotes (format spec section 3)

    a("<100 \\WerkStck\\")
    a('LA="%s"' % fnum(part.lx))
    a('BR="%s"' % fnum(part.ly))
    a('DI="%s"' % fnum(part.lz))
    a('FNX="0"')
    a('FNY="0"')
    a('AX="0"')
    a('AY="0"')
    a(SEP)

    for ci, elems in enumerate(part.contours, start=1):
        a("<105 \\Konturfraesen\\")
        a('EA="%d:0"' % ci)
        a('MDA="TAN"')
        a('RK="NoWRK"')
        a('EE="%d:%d"' % (ci, len(elems) - 1))
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

    for mid, mname, params in part.macros:
        a("<%d \\%s\\" % (mid, mname))
        for k, v in params:
            a('%s="%s"' % (k, v))
        a(SEP)

    # real woodWOP files put '!' straight after the last block, with no
    # separator line in between
    while out and out[-1] == SEP:
        out.pop()
    a("!")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# per-file driver
# ---------------------------------------------------------------------------

class Result:
    def __init__(self, src):
        self.src = src
        self.outputs = []           # (path, Part)


def _solid_records(entities, acds):
    """Yield a record table for every solid entity we can decode."""
    tables = []
    used_blobs = set()
    solids = [e for e in entities if e.type in ("3DSOLID", "BODY", "REGION")]
    for ent in solids:
        sat = acis_sat_text(ent)
        if sat:
            tables.append(parse_sat(sat))
            continue
        handle = (ent.first(5) or "").strip()
        blob = acds.get(handle)
        if blob is None and len(acds) == 1 and len(solids) == 1:
            blob = next(iter(acds.values()))
            handle = next(iter(acds))
        if blob is not None and handle not in used_blobs:
            used_blobs.add(handle)
            tables.append(parse_sab(blob))
    # a binary blob can also hold bodies that no entity handle pointed at
    if not tables:
        for handle, blob in acds.items():
            if handle not in used_blobs:
                tables.append(parse_sab(blob))
    return tables


def convert_file(path, opts):
    res = Result(path)
    entities, blocks, acds = parse_structure(read_tags(path))
    base = os.path.splitext(os.path.basename(path))[0]
    outdir = opts.outdir or os.path.dirname(os.path.abspath(path))

    parts = []
    shapes = []
    if not opts.force_2d:
        for recs in _solid_records(entities, acds):
            shapes.extend(build_shapes(recs))

    if shapes:
        if opts.largest_only and len(shapes) > 1:
            shapes = [max(shapes, key=_size_hint)]
        multi = len(shapes) > 1
        for si, shape in enumerate(shapes, start=1):
            pname = "%s_%d" % (base, si) if multi else base
            try:
                parts.append(shape_to_part(shape, pname, opts))
            except ConvertError as exc:
                p = Part(pname)
                p.notes.append("skipped: %s" % exc)
                parts.append(p)
        parts = [p for p in parts if p.lx > 0]

    if not parts:
        p = layers_to_part(entities, blocks, base, opts)
        if p is not None:
            parts.append(p)

    if not parts:
        counts = {}
        for e in entities:
            counts[e.type] = counts.get(e.type, 0) + 1
        summary = ", ".join("%s x%d" % kv for kv in sorted(counts.items())) \
            or "nothing"
        raise ConvertError(
            "nothing convertible found (model space holds: %s). Export either "
            "a 3D solid, or 2D geometry on woodWOP layers (Werkstk_<t>, "
            "V_Bohr..., V_Fraes_...)." % summary)

    for part in parts:
        text = render_mpr(part)
        dest = os.path.join(outdir, part.name + opts.ext)
        if not opts.dry_run:
            os.makedirs(outdir, exist_ok=True)
            # woodWOP splits the file on CRLF; an LF-only file is read as one
            # unparseable line and silently opens as a default blank panel.
            with open(dest, "w", encoding="cp1252", errors="replace",
                      newline="\r\n") as fh:
                fh.write(text)
        res.outputs.append((dest, part))
    return res


def _size_hint(shape):
    box = shape.bbox()
    if not box:
        return 0.0
    return (box[3] - box[0]) * (box[4] - box[1]) * (box[5] - box[2])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def expand_inputs(patterns, recursive):
    files = []
    for pat in patterns:
        if os.path.isdir(pat):
            walker = os.walk(pat) if recursive else \
                [(pat, [], os.listdir(pat))]
            for root, _d, names in walker:
                files.extend(os.path.join(root, n) for n in names
                             if n.lower().endswith(".dxf"))
        else:
            hits = [h for h in globmod.glob(pat, recursive=recursive)
                    if h.lower().endswith(".dxf")]
            if hits:
                files.extend(hits)
            elif os.path.isfile(pat):
                files.append(pat)
            else:
                print("  ! no such file: %s" % pat)
    seen = set()
    uniq = []
    for f in files:
        k = os.path.normcase(os.path.abspath(f))
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return sorted(uniq)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="dxf2mpr",
        description="Batch convert DXF drawings to woodWOP MPR programs.")
    ap.add_argument("inputs", nargs="+",
                    help="DXF files, wildcards or folders")
    ap.add_argument("-o", "--outdir", default=None,
                    help="output folder (default: next to each DXF)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="recurse into sub folders")
    ap.add_argument("--ext", default=".mpr",
                    help="output extension (default .mpr)")
    ap.add_argument("--thickness", type=float, default=None,
                    help="force the part thickness in mm")
    ap.add_argument("--snap", type=float, default=0.0,
                    help="round drill diameters to this step, e.g. 0.5")
    ap.add_argument("--max-dia", type=float, default=60.0,
                    help="bores larger than this are not turned into "
                         "drilling macros (default 60)")
    ap.add_argument("--bm-vert", default="LS",
                    help="drill mode for vertical bores (LS SS LSL SSS)")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false",
                    help="keep the CAD coordinates instead of moving the part "
                         "to the woodWOP zero point")
    ap.add_argument("--no-orient", dest="orient", action="store_false",
                    help="do not lay the part flat / turn it over")
    ap.add_argument("--no-long-x", dest="long_x", action="store_false",
                    help="do not rotate so the long side runs along X")
    ap.add_argument("--no-flip", dest="auto_flip", action="store_false",
                    help="do not turn a part over to drill from above")
    ap.add_argument("--no-contour", dest="contour", action="store_false",
                    help="never emit an outline contour / Konturfraesen")
    ap.add_argument("--largest-only", action="store_true",
                    help="if a DXF holds several solids, keep only the "
                         "biggest")
    ap.add_argument("--force-2d", action="store_true",
                    help="ignore 3D solids, read woodWOP layers only")
    ap.add_argument("--hbore-dia", type=float, default=8.0,
                    help="fallback diameter for H_Bohr blocks (default 8)")
    ap.add_argument("--hbore-depth", type=float, default=30.0,
                    help="fallback depth for H_Bohr blocks (default 30)")
    ap.add_argument("--log", default=None, help="write a CSV report here")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="analyse only, write nothing")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap


def main(argv=None):
    opts = build_parser().parse_args(argv)
    files = expand_inputs(opts.inputs, opts.recursive)
    if not files:
        print("no .dxf files found")
        return 2

    rows = []
    ok = failed = 0
    for path in files:
        try:
            res = convert_file(path, opts)
            ok += 1
            for dest, part in res.outputs:
                counts = {}
                for _mid, mname, _p in part.macros:
                    counts[mname] = counts.get(mname, 0) + 1
                detail = ", ".join("%d x %s" % (v, k)
                                   for k, v in sorted(counts.items()))
                if part.contours:
                    detail += (", " if detail else "") + \
                        "%d x contour" % len(part.contours)
                if not opts.quiet:
                    print("OK  %s -> %s" % (path, os.path.basename(dest)))
                    print("    %s x %s x %s mm   %s"
                          % (fnum(part.lx), fnum(part.ly), fnum(part.lz),
                             detail or "(no machining)"))
                    for n in dict.fromkeys(part.notes):
                        print("    note: %s" % n)
                rows.append({"source": path, "output": dest,
                             "length_x": fnum(part.lx),
                             "width_y": fnum(part.ly),
                             "thickness_z": fnum(part.lz),
                             "macros": len(part.macros),
                             "contours": len(part.contours),
                             "detail": detail,
                             "notes": " | ".join(dict.fromkeys(part.notes)),
                             "status": "ok"})
        except ConvertError as exc:
            failed += 1
            print("ERR %s\n    %s" % (path, exc))
            rows.append({"source": path, "output": "", "length_x": "",
                         "width_y": "", "thickness_z": "", "macros": "",
                         "contours": "", "detail": "", "notes": str(exc),
                         "status": "error"})
        except Exception as exc:                        # noqa: BLE001
            failed += 1
            print("ERR %s\n    unexpected: %s" % (path, exc))
            if not opts.quiet:
                traceback.print_exc()
            rows.append({"source": path, "output": "", "length_x": "",
                         "width_y": "", "thickness_z": "", "macros": "",
                         "contours": "", "detail": "",
                         "notes": "internal error: %s" % exc,
                         "status": "error"})

    if opts.log and rows:
        with open(opts.log, "w", encoding="cp1252", errors="replace",
                  newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()),
                               delimiter=";")
            w.writeheader()
            w.writerows(rows)
        print("report: %s" % opts.log)

    print("\n%d file(s) converted, %d failed" % (ok, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
