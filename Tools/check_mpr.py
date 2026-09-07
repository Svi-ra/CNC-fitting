#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_mpr.py -- sanity check MPR programs before they go to the machine.

Verifies the things that are cheap to get wrong and expensive to find out at
the spindle:

  * CRLF line endings -- woodWOP reads an LF-only file as a single line and
    silently opens it as a default blank panel
  * file structure ([H header, terminating '!')
  * every macro coordinate lies inside the workpiece
  * ZA of a horizontal drilling lies between 0 and the thickness
  * TI of a vertical drilling does not exceed the thickness
  * a <109 Nuten> groove runs somewhere, and does not saw through the part
  * drill diameters are in a plausible range
  * <105 Konturfraesen> references contour elements that actually exist

Usage:
    python check_mpr.py PROGRAM.mpr
    python check_mpr.py C:\\out\\*.mpr
    python check_mpr.py C:\\out -r
"""

from __future__ import annotations

import argparse
import glob as globmod
import os
import re
import sys

MACRO_RE = re.compile(r"^<(\d+) .(\w+).\s*$")
PARAM_RE = re.compile(r'^([A-Z_][A-Z_0-9]*)="(.*)"\s*$')
ELEM_RE = re.compile(r"^\$E(\d+)\s*$")


def _f(text, key, default=None):
    m = re.search(r"%s=([-\d.]+)" % key, text)
    return float(m.group(1)) if m else default


def check_bytes(raw):
    """Line-ending check. woodWOP needs CRLF; LF-only opens as a blank panel."""
    issues = []
    lf = raw.count(b"\n")
    crlf = raw.count(b"\r\n")
    if lf and crlf == 0:
        issues.append("LF line endings - woodWOP needs CRLF (the program will "
                      "open as an empty default panel)")
    elif crlf and crlf != lf:
        issues.append("mixed line endings: %d LF but only %d CRLF"
                      % (lf, crlf))
    if not raw.rstrip(b"\r\n").endswith(b"!"):
        issues.append("does not end with '!'")
    return issues


def check_text(txt, min_dia, max_dia):
    issues = []
    if not txt.startswith("[H"):
        issues.append("does not start with '[H'")

    lx = _f(txt, "_BSX")
    ly = _f(txt, "_BSY")
    lz = _f(txt, "_BSZ")
    if lx is None or ly is None or lz is None:
        issues.append("no _BSX/_BSY/_BSZ in the data head")
        return issues, 0
    if min(lx, ly) < 1.0 or lz < 0.5:
        issues.append("implausible part size %g x %g x %g" % (lx, ly, lz))

    elements = set()
    macros = []
    cur = None
    params = {}
    for line in txt.split("\n"):
        m = ELEM_RE.match(line)
        if m:
            elements.add(int(m.group(1)))
            continue
        m = MACRO_RE.match(line)
        if m:
            if cur:
                macros.append((cur, params))
            cur = m.group(2)
            params = {}
            continue
        m = PARAM_RE.match(line)
        if m and cur:
            params[m.group(1)] = m.group(2)
    if cur:
        macros.append((cur, params))

    n = 0
    for name, p in macros:
        if name == "WerkStck":
            la, br, di = p.get("LA"), p.get("BR"), p.get("DI")
            for key, want, got in (("LA", lx, la), ("BR", ly, br),
                                   ("DI", lz, di)):
                try:
                    if got is not None and abs(float(got) - want) > 0.01:
                        issues.append("WerkStck %s=%s but header says %g"
                                      % (key, got, want))
                except ValueError:
                    pass
            continue
        n += 1

        def num(key):
            v = p.get(key)
            if v in (None, "", "STANDARD") or v.startswith("@"):
                return None
            try:
                return float(v)
            except ValueError:
                return None

        xa, ya, za = num("XA"), num("YA"), num("ZA")
        xe, ye, nb = num("XE"), num("YE"), num("NB")
        ti, du = num("TI"), num("DU")
        if xa is not None and not -0.01 <= xa <= lx + 0.01:
            issues.append("%s: XA=%g outside 0..%g" % (name, xa, lx))
        if ya is not None and not -0.01 <= ya <= ly + 0.01:
            issues.append("%s: YA=%g outside 0..%g" % (name, ya, ly))
        if xe is not None and not -0.01 <= xe <= lx + 0.01:
            issues.append("%s: XE=%g outside 0..%g" % (name, xe, lx))
        if ye is not None and not -0.01 <= ye <= ly + 0.01:
            issues.append("%s: YE=%g outside 0..%g" % (name, ye, ly))
        if za is not None and not -0.01 <= za <= lz + 0.01:
            issues.append("%s: ZA=%g outside 0..%g" % (name, za, lz))
        if name in ("BohrVert", "UfluBohr") and ti and ti > lz + 0.01:
            issues.append("%s: TI=%g deeper than the %g mm part"
                          % (name, ti, lz))
        if ti is not None and ti <= 0:
            issues.append("%s: TI=%g is not positive" % (name, ti))
        if du is not None and not min_dia <= du <= max_dia:
            issues.append("%s: DU=%g outside %g..%g mm"
                          % (name, du, min_dia, max_dia))
        if name == "BohrHoriz" and p.get("BM") not in ("XP", "XM", "YP", "YM",
                                                       "C", None):
            issues.append("BohrHoriz: unknown BM=%r" % p.get("BM"))
        if name == "Nuten":
            if ti is not None and ti > lz - 0.01:
                issues.append("Nuten: TI=%g saws through the %g mm part"
                              % (ti, lz))
            if nb is not None and nb <= 0:
                issues.append("Nuten: NB=%g is not a width" % nb)
            if None not in (xa, ya, xe, ye) and                     abs(xa - xe) < 1e-9 and abs(ya - ye) < 1e-9:
                issues.append("Nuten: start and end are the same point")

    for _ci, last in re.findall(r'EE="(\d+):(\d+)"', txt):
        if int(last) not in elements:
            issues.append("Konturfraesen references missing element $E%s"
                          % last)
    for _ci, first in re.findall(r'EA="(\d+):(\d+)"', txt):
        if int(first) not in elements:
            issues.append("Konturfraesen starts at missing element $E%s"
                          % first)
    return issues, n


def expand(patterns, recursive):
    out = []
    for pat in patterns:
        if os.path.isdir(pat):
            walker = os.walk(pat) if recursive else \
                [(pat, [], os.listdir(pat))]
            for root, _d, names in walker:
                out.extend(os.path.join(root, x) for x in names
                           if x.lower().endswith(".mpr"))
        else:
            hits = globmod.glob(pat, recursive=recursive)
            out.extend(h for h in hits if h.lower().endswith(".mpr"))
            if not hits and os.path.isfile(pat):
                out.append(pat)
    return sorted(set(out))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="check_mpr",
                                 description="Sanity check woodWOP MPR files.")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-r", "--recursive", action="store_true")
    ap.add_argument("--min-dia", type=float, default=1.0)
    ap.add_argument("--max-dia", type=float, default=60.0)
    opts = ap.parse_args(argv)

    files = expand(opts.inputs, opts.recursive)
    if not files:
        print("no .mpr files found")
        return 2
    bad = 0
    for f in files:
        try:
            with open(f, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print("BAD  %s  (%s)" % (f, exc))
            bad += 1
            continue
        txt = raw.decode("cp1252", errors="replace").replace("\r\n", "\n")
        issues, n = check_text(txt, opts.min_dia, opts.max_dia)
        issues = check_bytes(raw) + issues
        print("%s %-30s %d macro(s)"
              % ("BAD " if issues else "ok  ", os.path.basename(f), n))
        for i in issues:
            print("       - %s" % i)
        bad += bool(issues)
    print("\n%d file(s) checked, %d with findings" % (len(files), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
