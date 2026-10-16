# -*- coding: utf-8 -*-
r"""
gh_cutlist2json.py -- Grasshopper Script component: the cut list from
gh_brep2mpr -> one JSON document that lays the list out the way the shop's
Excel cut lists are laid out.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   TABLE     str   access = Tree   the cut list: TABLE from
                                            gh_brep2mpr, or the CSV as text
    input   CAT       str   access = List   the material categories, as they
                                            appear in TABLE's Material column
    input   MATERIAL  str   access = List   the exact material name for each
                                            category, in the same order
    input   PROJECT   str   access = Item   the project name
    output  JSON      -                     the whole document, one string
    output  INFO      -                     a report

The access settings matter. A new Script component input starts on Item
access, and on Item access Grasshopper runs the script once per item: a
15-line cut list comes out as 15 JSON documents of one line each, which
saved together are not JSON at all, and each run sees only one material
name. So the component checks: if TABLE, CAT or MATERIAL is on Item access
it turns red, says which, and gives no JSON. Set them to Tree (List works
too).

It outputs text only and writes no file -- ShapeDiver forbids saving to a
local path. Save JSON as a .json through whatever exports text downstream: a
ShapeDiver export component online, a panel or a writer of your own on the
desktop. Write it as UTF-8: material and panel names keep their diacritics.

The layout
----------
The sheet follows the shop's reference workbook ("1. Mobilier birou copii
str. Victoriei 8"): the project name across the top, then one block per
material, two empty rows apart.

    row 1    the project name, bold, across A:Q
    row 3    Material: PAL 8681 SM                         COMENTARII
    row 4    Nr. | Lungime (L) | Latime (W) | cant. | L-1 x3 | L-2 x3 |
             W-1 x3 | W-2 x3 |
    row 5..  1   | 490         | 100        | 4     |  ...edges...    | Bottom

    A   Nr.          counts 1, 2, 3 ... within each material
    B   Lungime (L)  Lungime from the cut list -- the side along the grain
    C   Latime (W)   Latime from the cut list
    D   cant.        Cantitate
    E:P              the edges, three cells each: L-1, L-2, W-1, W-2
    Q   COMENTARII   Denumire -- the panel name

The edge cells are left empty: the cut list says nothing about banding, and
an empty cell is safer than a guess. Everything else in a row comes from the
cut list unchanged -- the sizes, the quantity, the panel name -- and the
program ID it belongs to is kept in the data as well, so a line can be traced
back to its .mpr.

Materials
---------
CAT and MATERIAL are two plain lists read side by side: item *i* of CAT is a
category as gh_brep2mpr's MAT carried it ("base", "interior" ...) and item
*i* of MATERIAL is the name to print for it ("PAL 8681 SM"). The name is used
exactly as given -- nothing is trimmed inside it or changed in case.

The blocks come in the order of CAT. A category the cut list uses but CAT
does not name still gets its block, after the named ones, titled with the
category itself, and INFO warns about it: that title is a stand-in, not a
material name. A category named in CAT that no line uses gets no block, and
INFO says so. Categories are matched exactly, case and all, apart from
spaces at either end.

Within a block the lines keep the cut list's order, which is the order of the
program IDs. A program whose copies carry different names comes in as
several lines under one ID; each stays a row of its own, with its own name
and its own share of the quantity.

The JSON
--------
One object with two halves. ``sections`` is the data, one entry per material:

    {"category": "base", "material": "PAL 8681 SM", "first_row": 3, ...
     "rows": [{"nr": 1, "id": "0", "length": 490, "width": 100, "qty": 4,
               "edges": {"L-1": null, "L-2": null, "W-1": null,
                         "W-2": null},
               "comment": "Bottom"}, ...]}

``sheet`` is the same rows already placed on the grid, ready to write
straight into a worksheet:

    values    one entry per row: its number and the cells from A onwards
    columns   the width of every column, A to Q
    heights   the rows that are taller than the default
    styles    named formats -- font, fill, alignment, border, number format
    formats   which style goes on which range
    outlines  the ranges boxed with a medium line
    merges    the merged ranges
    page      landscape A4, one page wide, the reference's margins

An importer writes each ``values`` row into its row, applies ``formats`` in
order, draws ``outlines`` over them, then merges. ``CutListImport.bas``
next to this file is that importer for Excel: import it in the VBA editor
and run ImportCutList, which asks for the .json and lays it out in a new
workbook. Power Query reads
``sections`` as it is: Data > Get Data > From File > From JSON, then expand
``sections`` and ``rows``.

Reading the cut list
--------------------
TABLE is read whichever way it comes: the line-per-item list gh_brep2mpr
writes, one string holding the whole CSV, or a tree of either. The header
line is found by its field names, and the columns are taken by name from
it, so a cut list with its columns moved still reads. Without a
header the columns are taken in gh_brep2mpr's order. A line counts as the
header when it names at least two of the columns:

    Material;ID;Lungime;Latime;Cantitate;Denumire

A line that cannot be read -- too few fields, a size or a quantity that is
not a number -- is left out and named in INFO.
"""

import csv
import json

from Grasshopper import DataTree
from Grasshopper.Kernel import GH_ParamAccess, GH_RuntimeMessageLevel
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

SEP = ";"                   # gh_brep2mpr's TABLE_SEP
FIELDS = ("Material", "ID", "Lungime", "Latime", "Cantitate", "Denumire")

SHEET_NAME = "Lista"        # Excel allows 31 characters, none of []:*?/\
TITLE_PREFIX = "Material: "
GAP_ROWS = 2                # empty rows between two materials
INDENT = 1                  # JSON indent; None writes it on one line
WHOLE = ("TABLE", "CAT", "MATERIAL")    # inputs that must come in whole

# The reference workbook's columns, A to Q. Each edge takes three cells.
EDGES = ("L-1", "L-2", "W-1", "W-2")
CELLS_PER_EDGE = 3
HEAD = (["Nr.", "Lungime (L)", "Latime (W)", "cant."]
        + [e for e in EDGES for _ in range(CELLS_PER_EDGE)])
COMMENT_HEAD = "COMENTARII"
WIDTHS = ([7.71, 12.71, 12.71, 7.71]
          + [12.57] * 3 + [13.0] * 3 + [13.57] * 3 + [12.71] * 3
          + [77.57])
TALL_ROW = 15.75            # the title, material and header rows

FILL = "B7DEE8"             # theme accent 5, 60 % lighter, as rgb
FONT = {"name": "Calibri", "size": 11}
MARGINS_IN = {"left": 0.71, "right": 0.71, "top": 0.75, "bottom": 0.75,
              "header": 0.31, "footer": 0.31}

# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------

N_COLS = len(HEAD) + 1                  # A..Q
LAST_HEAD = len(HEAD)                   # P: the last column with a heading
COMMENT_COL = N_COLS                    # Q


def col(n):
    """1 -> A, 17 -> Q, 27 -> AA."""
    name = ""
    while n:
        n, rest = divmod(n - 1, 26)
        name = chr(65 + rest) + name
    return name


def ref(c1, r1, c2=None, r2=None):
    """A cell or a range: ref(1, 3) -> A3, ref(1, 3, 4, 3) -> A3:D3."""
    first = "%s%d" % (col(c1), r1)
    if c2 is None:
        return first
    return "%s:%s%d" % (first, col(c2), r1 if r2 is None else r2)


# ---------------------------------------------------------------------------
# reading the input
# ---------------------------------------------------------------------------


def branches_of(tree):
    """Work whether the input access is Tree, List or Item."""
    if tree is None:
        return []
    if hasattr(tree, "Branches") and hasattr(tree, "Paths"):
        return [list(b) for b in tree.Branches]
    if isinstance(tree, (list, tuple)):
        return [list(tree)]
    return [[tree]]


def unwrap(item):
    """The value inside a Grasshopper wrapper, or the item as it came."""
    inner = getattr(item, "Value", None)
    return item if inner is None else inner


def texts(tree):
    """Every item of every branch, as text, None left out."""
    out = []
    for branch in branches_of(tree):
        for item in branch:
            item = unwrap(item)
            if item is not None:
                out.append(str(item))
    return out


def table_lines(tree):
    """TABLE as lines, however it was wired.

    An item may be one line or a whole CSV; a file read in from disk may
    also start with a byte order mark.
    """
    lines = []
    for text in texts(tree):
        for line in text.replace("﻿", "").splitlines():
            if line.strip():
                lines.append(line)
    return lines


def number(text):
    """A size or a quantity: 480 -> 480, 480.5 -> 480.5, 480,5 -> 480.5.

    Whole numbers stay whole, so Excel shows 480, not 480.0.
    """
    text = text.strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(text)
    return int(value) if value.is_integer() else value


def read_table(lines, info):
    """The cut list lines -> [{category, id, length, width, qty, name}]."""
    known = [name.lower() for name in FIELDS]
    index = {name: i for i, name in enumerate(known)}
    pieces = []
    for n, fields in enumerate(csv.reader(lines, delimiter=SEP), 1):
        fields = [f.strip() for f in fields]
        if not any(fields):
            continue
        heads = [f.lower() for f in fields]
        # A header names at least two of the columns; a piece whose
        # material happens to be called "Material" names one at most.
        if sum(h in known for h in heads) >= 2:
            missing = [f for f in FIELDS[:5] if f.lower() not in heads]
            if missing:
                info.append("WARNING: the header on line %d has no %s - "
                            "the columns are read in gh_brep2mpr's order"
                            % (n, ", ".join(missing)))
                index = {name: i for i, name in enumerate(known)}
            else:
                index = {h: i for i, h in enumerate(heads)}
            continue

        def field(name):
            i = index.get(name.lower())
            return fields[i] if i is not None and i < len(fields) else None

        if any(field(name) is None for name in FIELDS[:5]):
            info.append("line %d left out - only %d field%s: %s"
                        % (n, len(fields), "" if len(fields) == 1 else "s",
                           SEP.join(fields)))
            continue
        try:
            length = number(field("Lungime"))
            width = number(field("Latime"))
            qty = number(field("Cantitate"))
        except ValueError:
            info.append("line %d left out - a size or the quantity is not "
                        "a number: %s" % (n, SEP.join(fields)))
            continue
        pieces.append({"category": field("Material"), "id": field("ID"),
                       "length": length, "width": width, "qty": qty,
                       "name": field("Denumire") or ""})
    return pieces


def read_materials(cats, names, info):
    """CAT and MATERIAL side by side -> {category: exact name}, in order."""
    if len(cats) != len(names):
        info.append("WARNING: %d categories on CAT but %d names on MATERIAL "
                    "- read as far as both go" % (len(cats), len(names)))
    materials = {}
    for cat, name in zip(cats, names):
        cat = cat.strip()
        if cat in materials:
            if materials[cat] != name:
                info.append("WARNING: category '%s' is named twice - '%s' "
                            "is kept, '%s' is ignored"
                            % (cat, materials[cat], name))
            continue
        if not name.strip():
            info.append("WARNING: category '%s' has an empty material name"
                        % cat)
        materials[cat] = name
    return materials


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------


def group(pieces, materials, info):
    """The pieces in blocks by material: CAT's order, then the strays."""
    blocks = {cat: [] for cat in materials}
    for piece in pieces:
        blocks.setdefault(piece["category"], []).append(piece)
    for cat in materials:
        if not blocks[cat]:
            info.append("category '%s' (%s) has no line in the cut list - "
                        "no block for it" % (cat, materials[cat]))
    for cat in blocks:
        if blocks[cat] and cat not in materials:
            info.append("WARNING: category '%s' is in the cut list but not "
                        "on CAT - its block is titled with the category, "
                        "not a material name" % (cat or "(none)"))
    return [(cat, materials.get(cat, cat), rows)
            for cat, rows in blocks.items() if rows]


def styles():
    thin = {"left": "thin", "right": "thin", "top": "thin",
            "bottom": "thin"}

    def style(fill=None, bold=False, horizontal=None, vertical=None,
              border=None, number_format="General"):
        font = dict(FONT)
        font["bold"] = bold
        return {"font": font, "fill": fill,
                "align": {"horizontal": horizontal, "vertical": vertical},
                "border": border, "number_format": number_format}

    return {
        "title":    style(FILL, bold=True, horizontal="center"),
        "material": style(FILL, horizontal="left"),
        "band":     style(FILL),
        "comments": style(FILL, horizontal="center"),
        "head":     style(FILL, horizontal="center", border=thin),
        "nr":       style(border=thin),
        "number":   style(horizontal="right", vertical="center",
                          border=thin),
        "edge":     style(horizontal="left", border=thin),
        "comment":  style(horizontal="left", border=thin),
    }


def build(project, blocks):
    values, formats, outlines, merges, heights = [], [], [], [], []
    sections = []

    def put(row, cells):
        values.append({"row": row, "cells": cells})

    def tall(row):
        heights.append({"row": row, "height": TALL_ROW})

    put(1, [project] + [None] * (N_COLS - 1))
    formats.append({"range": ref(1, 1, N_COLS), "style": "title"})
    outlines.append(ref(1, 1, N_COLS))
    merges.append(ref(1, 1, N_COLS))
    tall(1)

    top = 3
    for cat, material, pieces in blocks:
        head, first, last = top + 1, top + 2, top + 1 + len(pieces)

        put(top, [TITLE_PREFIX + material] + [None] * (N_COLS - 2)
            + [COMMENT_HEAD])
        put(head, HEAD + [None])
        formats += [{"range": ref(1, top, 4), "style": "material"},
                    {"range": ref(5, top, LAST_HEAD), "style": "band"},
                    {"range": ref(COMMENT_COL, top, COMMENT_COL, head),
                     "style": "comments"},
                    {"range": ref(1, head, LAST_HEAD), "style": "head"}]
        outlines += [ref(1, top, 4), ref(5, top, LAST_HEAD),
                     ref(COMMENT_COL, top, COMMENT_COL, head),
                     ref(1, head, 4), ref(5, head, LAST_HEAD)]
        merges += [ref(1, top, 4), ref(COMMENT_COL, top, COMMENT_COL, head)]
        tall(top)
        tall(head)

        rows = []
        for nr, piece in enumerate(pieces, 1):
            put(first + nr - 1,
                [nr, piece["length"], piece["width"], piece["qty"]]
                + [None] * (len(EDGES) * CELLS_PER_EDGE)
                + [piece["name"] or None])
            rows.append({"nr": nr, "id": piece["id"],
                         "length": piece["length"], "width": piece["width"],
                         "qty": piece["qty"],
                         "edges": {e: None for e in EDGES},
                         "comment": piece["name"]})
        formats += [{"range": ref(1, first, 1, last), "style": "nr"},
                    {"range": ref(2, first, 4, last), "style": "number"},
                    {"range": ref(5, first, LAST_HEAD, last),
                     "style": "edge"},
                    {"range": ref(COMMENT_COL, first, COMMENT_COL, last),
                     "style": "comment"}]

        sections.append({"category": cat, "material": material,
                         "title": TITLE_PREFIX + material,
                         "first_row": top, "last_row": last,
                         "pieces": sum(p["qty"] for p in pieces),
                         "rows": rows})
        top = last + 1 + GAP_ROWS

    sheet = {
        "name": SHEET_NAME,
        "columns": [{"col": col(i + 1), "width": w}
                    for i, w in enumerate(WIDTHS)],
        "heights": heights,
        "styles": styles(),
        "values": values,
        "formats": formats,
        "outlines": [{"range": r, "weight": "medium"} for r in outlines],
        "merges": merges,
        "page": {"orientation": "landscape", "paper": "A4",
                 "fit_width": 1, "fit_height": 0, "margins_in": MARGINS_IN},
    }
    return {"format": "cnc-fitting cut list", "version": 1,
            "project": project, "sheet": sheet, "sections": sections}


# ---------------------------------------------------------------------------
# Grasshopper plumbing
# ---------------------------------------------------------------------------

try:
    TABLE
except NameError:
    TABLE = None
try:
    CAT
except NameError:
    CAT = None
try:
    MATERIAL
except NameError:
    MATERIAL = None
try:
    PROJECT
except NameError:
    PROJECT = None


def item_access():
    """The inputs of WHOLE that are left on Item access.

    Grasshopper runs a script once per item of an Item input, so a cut list
    on an Item TABLE comes out as one JSON per line, each a document of its
    own -- and saved together they are no JSON at all. ghenv is only there
    inside a Script component; without it nothing is checked.
    """
    try:
        params = ghenv.Component.Params.Input    # noqa: F821 -- Grasshopper's
    except (NameError, AttributeError):
        return []
    return [p.NickName for p in params
            if p.NickName in WHOLE and p.Access == GH_ParamAccess.item]


def lay_out(notes):
    """The JSON for the wired inputs, or None when there is nothing to lay
    out; one INFO line per material block, everything else into notes."""
    project = next((t for t in texts(PROJECT) if t.strip()), "")
    if not project:
        notes.append("WARNING: no PROJECT - the title row is empty")
    pieces = read_table(table_lines(TABLE), notes)
    if not pieces:
        notes.append("no cut list lines on TABLE - nothing to lay out")
        return None
    blocks = group(pieces, read_materials(texts(CAT), texts(MATERIAL),
                                          notes), notes)
    doc = build(project, blocks)
    for section in doc["sections"]:
        INFO.Add("%s   %s   rows %d-%d   %d line%s, %s piece%s"
                 % (section["title"],
                    "(%s)" % section["category"] if section["category"]
                    else "(no category)",
                    section["first_row"], section["last_row"],
                    len(section["rows"]),
                    "" if len(section["rows"]) == 1 else "s",
                    section["pieces"],
                    "" if section["pieces"] == 1 else "s"), GH_Path(0))
    notes.append("edges L-1 L-2 W-1 W-2 left empty - the cut list carries "
                 "no banding")
    return json.dumps(doc, ensure_ascii=False, indent=INDENT)


INFO = DataTree[object]()
JSON = None
notes = []

wrong = item_access()
if wrong:
    message = ("%s %s on Item access, so this component runs once per item "
               "and writes a JSON for each. Right-click %s and choose Tree "
               "Access (List Access does as well)."
               % (" and ".join(wrong), "is" if len(wrong) == 1 else "are",
                  "it" if len(wrong) == 1 else "each"))
    ghenv.Component.AddRuntimeMessage(              # noqa: F821
        GH_RuntimeMessageLevel.Error, message)
    notes.append("ERROR: " + message)
else:
    JSON = lay_out(notes)
for note in notes:
    INFO.Add(note, GH_Path(0))
