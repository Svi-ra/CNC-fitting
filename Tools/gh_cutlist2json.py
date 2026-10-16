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

For a workbook that opens ready to print, with no macro, wire JSON on into
gh_json2xlsx.py: it turns the sheet into the text files of an .xlsx for an
archive download to zip.

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

    A   Nr.          the program ID from the cut list -- the number the
                     .mpr file name starts with
    B   Lungime (L)  Lungime from the cut list -- the side along the grain
    C   Latime (W)   Latime from the cut list
    D   cant.        Cantitate
    E:P              the edges, three cells each: L-1, L-2, W-1, W-2
    Q   COMENTARII   Denumire -- the panel name

The edges come from the cut list's L-1, L-2, W-1 and W-2 columns: the
banding material gh_brep2mpr read off BANDTYPE and BAND_MAP for that edge.
Its three cells are the ones the cutting software's Excel import reads for
each facing (Облицовка) -- name, designation, thickness:

    Наим.         the material, as on BAND_MAP          ABS 22/0.5
    Обозначение   the material again                    ABS 22/0.5
    Толщина       the number after the last "/" in it   0.5

A name with no number after a "/" leaves Толщина empty, and INFO says so:
the importer may take the thickness off the panel's size, so a guess there
would cut the panel wrong. An edge with no material -- unbanded, or a cut
list from before those columns -- leaves all three cells empty. Everything
else in a row comes from the cut list unchanged -- the sizes, the quantity,
the panel name -- and the program ID it belongs to is kept in the data as
well, so a line can be traced back to its .mpr.

Materials
---------
CAT and MATERIAL are two plain lists read side by side: item *i* of CAT is a
category as gh_brep2mpr's MAT carried it ("base", "interior" ...) and item
*i* of MATERIAL is the name to print for it ("PAL 8681 SM"). The name is used
exactly as given -- nothing is trimmed inside it or changed in case.

The blocks come in the order of CAT. Categories that print the same
material -- "base" and "drawers" both PAL 8681 SM -- share one block, where
the first of them stands on CAT, and the section lists them all. A category
the cut list uses but CAT does not name still gets its block, after the
named ones, titled with the category itself, and INFO warns about it: that
title is a stand-in, not a material name. A category named in CAT that no
line uses gets no block, and INFO says so. Categories are matched exactly,
case and all, apart from spaces at either end.

Within a block the lines keep the cut list's order, which is the order of the
program IDs. A program whose copies carry different names comes in as
several lines under one ID; each stays a row of its own, with its own name
and its own share of the quantity.

Nr. is the program ID, so a row leads straight to its .mpr: 7 is
7_480x232-B_1.mpr. It does not count the rows -- the lines of one program
share its number, and a material's block starts at whatever number its
first program has. A line with no ID has no file to point at, and its Nr.
is left empty rather than given a number that may be another program's.

The JSON
--------
One object with two halves. ``sections`` is the data, one entry per material:

    {"categories": ["base"], "material": "PAL 8681 SM", "first_row": 3, ...
     "rows": [{"nr": 1, "id": "1", "length": 490, "width": 100, "qty": 4,
               "edges": {"L-1": {"name": "ABS 22/1",
                                 "designation": "ABS 22/1",
                                 "thickness": 1},
                         "L-2": null, "W-1": null, "W-2": null},
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

    Material;ID;Lungime;Latime;Cantitate;Denumire;L-1;L-2;W-1;W-2

Denumire and the four edges may be missing; the first five may not.

A line that cannot be read -- too few fields, a size or a quantity that is
not a number -- is left out and named in INFO.
"""

import csv
import json
import re

from Grasshopper import DataTree
from Grasshopper.Kernel import GH_ParamAccess, GH_RuntimeMessageLevel
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

SEP = ";"                   # gh_brep2mpr's TABLE_SEP
FIELDS = ("Material", "ID", "Lungime", "Latime", "Cantitate", "Denumire",
          "L-1", "L-2", "W-1", "W-2")

SHEET_NAME = "Lista"        # Excel allows 31 characters, none of []:*?/\
TITLE_PREFIX = "Material: "
GAP_ROWS = 2                # empty rows between two materials
INDENT = 1                  # JSON indent; None writes it on one line
WHOLE = ("TABLE", "CAT", "MATERIAL")    # inputs that must come in whole

# The reference workbook's columns, A to Q. Each edge takes three cells.
EDGES = ("L-1", "L-2", "W-1", "W-2")
CELLS_PER_EDGE = 3          # Наим., Обозначение, Толщина
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
    """The cut list lines -> [{category, id, length, width, qty, name,
    edges}], edges being {edge: edge_cells(), or None}."""
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
                       "name": field("Denumire") or "",
                       "edges": dict((e, edge_cells(field(e), info))
                                     for e in EDGES)})
    return pieces


THICKNESS = re.compile(r"/\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*$", re.I)


def edge_cells(material, info):
    """A banding material -> {name, designation, thickness}, or None.

    The thickness is the number after the last "/" of the name -- ABS 22/0.5
    is 0.5 thick. A name that does not end so gets no thickness, never a
    guessed one, and INFO says so once.
    """
    if not material:
        return None
    found = THICKNESS.search(material)
    thickness = number(found.group(1)) if found else None
    if thickness is None:
        note = ("WARNING: no thickness in banding material '%s' - Толщина "
                "left empty; name it as <type> <width>/<thickness>, "
                "\"ABS 22/1\"" % material)
        if note not in info:
            info.append(note)
    return {"name": material, "designation": material,
            "thickness": thickness}


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
    """The pieces in blocks by material: CAT's order, then the strays.

    Categories that print the same material share one block, placed where
    the first of them is on CAT, its lines in the cut list's order. A stray
    keeps a block of its own even when its stand-in title happens to read
    like a material name, and so does a category with an empty name.
    """
    def key(cat):
        name = materials.get(cat)
        return ("material", name) if name else ("category", cat)

    blocks = {}                         # key -> [categories, pieces]
    for cat in materials:
        blocks.setdefault(key(cat), [[], []])
    used = set(piece["category"] for piece in pieces)
    for piece in pieces:
        block = blocks.setdefault(key(piece["category"]), [[], []])
        if piece["category"] not in block[0]:
            block[0].append(piece["category"])
        block[1].append(piece)
    for cat in materials:
        if cat not in used:
            info.append("category '%s' (%s) has no line in the cut list - "
                        "no block for it" % (cat, materials[cat]))
    for cat in sorted(used - set(materials), key=str):
        info.append("WARNING: category '%s' is in the cut list but not "
                    "on CAT - its block is titled with the category, "
                    "not a material name" % (cat or "(none)"))
    for (kind, name), (cats, rows) in blocks.items():
        if kind == "material" and len(cats) > 1:
            info.append("categories %s are all %s - one block for them"
                        % (", ".join("'%s'" % c for c in cats), name))
    return [(cats, materials.get(name, name) if kind == "category" else name,
             rows)
            for (kind, name), (cats, rows) in blocks.items() if rows]


def row_number(ident):
    """Nr. for a cut list line: its program ID, the number on the .mpr.

    An ID that is a whole number is written as a number, so Excel sorts it
    as one; any other ID -- one wired on gh_brep2mpr's ID -- as it is. A
    line with no ID gets None, an empty cell.
    """
    ident = (ident or "").strip()
    if not ident:
        return None
    try:
        value = number(ident)
    except ValueError:
        return ident
    return value if isinstance(value, int) else ident


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
    for cats, material, pieces in blocks:
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
        for i, piece in enumerate(pieces):
            nr = row_number(piece["id"])
            edges = piece.get("edges") or {}
            cells = []
            for e in EDGES:
                edge = edges.get(e) or {}
                cells += [edge.get("name"), edge.get("designation"),
                          edge.get("thickness")]
            put(first + i,
                [nr, piece["length"], piece["width"], piece["qty"]]
                + cells + [piece["name"] or None])
            rows.append({"nr": nr, "id": piece["id"],
                         "length": piece["length"], "width": piece["width"],
                         "qty": piece["qty"],
                         "edges": dict((e, edges.get(e)) for e in EDGES),
                         "comment": piece["name"]})
        formats += [{"range": ref(1, first, 1, last), "style": "nr"},
                    {"range": ref(2, first, 4, last), "style": "number"},
                    {"range": ref(5, first, LAST_HEAD, last),
                     "style": "edge"},
                    {"range": ref(COMMENT_COL, first, COMMENT_COL, last),
                     "style": "comment"}]

        sections.append({"categories": cats, "material": material,
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
                    "(%s)" % ", ".join(c or "no category"
                                       for c in section["categories"]),
                    section["first_row"], section["last_row"],
                    len(section["rows"]),
                    "" if len(section["rows"]) == 1 else "s",
                    section["pieces"],
                    "" if section["pieces"] == 1 else "s"), GH_Path(0))
    if not any(any(p["edges"].values()) for p in pieces):
        notes.append("edges L-1 L-2 W-1 W-2 left empty - the cut list "
                     "carries no banding materials")
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
