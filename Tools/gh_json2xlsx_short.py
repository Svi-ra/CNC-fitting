# -*- coding: utf-8 -*-
r"""
gh_json2xlsx_short.py -- Grasshopper Script component: the JSON from
gh_cutlist2json -> the text files of an .xlsx, as gh_json2xlsx.py writes
them, but with one cell per edge instead of three: the banding material's
name under L-1, L-2, W-1 and W-2, without its repeat and thickness.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   JSON   str   access = Item   JSON from gh_cutlist2json
    output  PATH   -                     the six parts' paths in the archive
    output  TEXT   -                     their texts, in the same order
    output  NAME   -                     the archive's name, without the
                                         extension: PROJECT
    output  INFO   -                     a report

Zipping it
----------
An .xlsx is a zip of XML files. Feed PATH and TEXT to the archive download
-- ShapeDiver's, online -- as two lists of six, item for item: each text
saved under its path, at the root of the archive, not in a folder, and the
archive named NAME with .xlsx after it -- NAME carries no extension, so the
download adds its own, and it must be .xlsx, not .zip. The parts are

    [Content_Types].xml          what each part is
    _rels/.rels                  where the workbook is
    xl/workbook.xml              the one sheet, by name
    xl/_rels/workbook.xml.rels   where the sheet and the styles are
    xl/styles.xml                fonts, fills, borders, alignment
    xl/worksheets/sheet1.xml     the cells, widths, merges and the page

**TEXT must arrive as six items.** If anything on the way joins the list
into one text -- a Panel, a Text Join, an input that takes one item -- that
one text is saved under all six paths, every part holds all six documents,
and Excel says the file's format or extension is not valid. A Panel or
Param Viewer just before the archive should show 6 items on each wire. A
folder round the parts, a changed path, or no [Content_Types].xml, and Excel
refuses the archive the same way.

What it writes
--------------
The JSON's "sheet" with columns F G, I J, L M and O P left out -- each
edge's second and third cells -- and the rest moved left to close the gaps:

    A    B            C           D      E    F    G    H    I
    Nr.  Lungime (L)  Latime (W)  cant.  L-1  L-2  W-1  W-2  COMENTARII

The ranges that spanned the edges -- the band row over E:P, the header's
outline -- now span E:H; every cell kept looks as it does in gh_json2xlsx's
workbook: value, fill, font, alignment, borders, width. The rows, the
merges and the page are the same: landscape A4, one page wide.

The code from "the .xlsx" down is gh_json2xlsx.py's, unchanged; a fix there
goes into this one too.

A JSON that is not gh_cutlist2json's, of a newer version than this script
knows, or whose sheet is not the A:Q layout it cuts down, gives no parts and
an ERROR in INFO, rather than a workbook laid out half right.
"""

import json
import re

from Grasshopper import DataTree
from Grasshopper.Kernel import GH_RuntimeMessageLevel
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

DOC_FORMAT = "cnc-fitting cut list"     # gh_cutlist2json's "format"
DOC_VERSION = 1                         # the newest version this reads
# The font of a cell no format reaches. The column widths assume it: a
# digit of Calibri 11 is 7 px wide.
FONT = {"name": "Calibri", "size": 11}
# gh_cutlist2json's columns: A:D, then the edges E:P three cells each --
# Наим., Обозначение, Толщина -- then the comment in Q. Only the first cell
# of each edge is kept.
N_COLS = 17
FIRST_EDGE_COL = 5
N_EDGES = 4
CELLS_PER_EDGE = 3


def col(n):
    """1 -> A, 17 -> Q, 27 -> AA."""
    name = ""
    while n:
        n, rest = divmod(n - 1, 26)
        name = chr(65 + rest) + name
    return name


def ref(c, r):
    """A cell: ref(1, 3) -> A3."""
    return "%s%d" % (col(c), r)


# ---------------------------------------------------------------------------
# the .xlsx
# ---------------------------------------------------------------------------

# An .xlsx is a zip of XML parts. These are the parts it needs and no more;
# zipped as they are -- at the root of the archive, these exact paths, the
# square brackets included -- and named .xlsx, the archive opens in Excel.
# A folder round them, or no [Content_Types].xml, and Excel refuses it.
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = ("http://schemas.openxmlformats.org/officeDocument/2006/"
          "relationships")
NS_PKG = "http://schemas.openxmlformats.org/package/2006/"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
OOXML = "application/vnd.openxmlformats-officedocument.spreadsheetml."
PAPER = {"A4": 9, "A3": 8, "LETTER": 1}
SIDES = ("left", "right", "top", "bottom")
OPPOSITE = {"left": ("right", 0, -1), "right": ("left", 0, 1),
            "top": ("bottom", -1, 0), "bottom": ("top", 1, 0)}
BAD_XML = re.compile(u"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def xml_text(value):
    """Text for an XML element or attribute: escaped, and with the control
    characters XML cannot carry at all left out."""
    text = BAD_XML.sub("", str(value))
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def cells_of(rng):
    """'A3:D4' -> [(3, 1), (3, 2) ... (4, 4)], as (row, column)."""
    def split(cell):
        m = re.match(r"^([A-Z]+)(\d+)$", cell)
        n = 0
        for ch in m.group(1):
            n = n * 26 + ord(ch) - 64
        return int(m.group(2)), n
    first, _, last = rng.partition(":")
    r1, c1 = split(first)
    r2, c2 = split(last or first)
    return r1, c1, r2, c2


def resolve(sheet):
    """Every cell's own look, {(row, column): look}, built the way
    CutListImport.bas builds it: the formats in order, then the outlines on
    top. A look is font, fill, alignment, number format and four sides.

    Excel keeps a line between two cells on both of them, so a side set on
    one cell is set on its neighbour's facing side too -- otherwise a medium
    outline next to a thin rule shows whichever the neighbour has. Not past
    the sheet's last row or column, though: a cell out there would widen the
    used range, and with it the page that is fitted to one sheet wide.
    """
    looks = {}
    spans = [cells_of(f["range"]) for f in sheet["formats"]]
    spans += [cells_of(o["range"]) for o in sheet["outlines"]]
    last_row = max([s[2] for s in spans] + [1])
    last_col = max([s[3] for s in spans] + [1])

    def look(rc):
        return looks.setdefault(rc, {"font": dict(FONT, bold=False),
                                     "fill": None, "h": None, "v": None,
                                     "number_format": "General",
                                     "border": {}})

    def side(r, c, name, weight):
        look((r, c))["border"][name] = weight
        other, dr, dc = OPPOSITE[name]
        if 1 <= r + dr <= last_row and 1 <= c + dc <= last_col:
            look((r + dr, c + dc))["border"][other] = weight

    styles = sheet["styles"]
    for f in sheet["formats"]:
        st = styles[f["style"]]
        r1, c1, r2, c2 = cells_of(f["range"])
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                lk = look((r, c))
                if st.get("font"):
                    lk["font"].update(st["font"])
                if "fill" in st:
                    lk["fill"] = st["fill"]
                align = st.get("align") or {}
                if "horizontal" in align:
                    lk["h"] = align["horizontal"]
                if "vertical" in align:
                    lk["v"] = align["vertical"]
                if st.get("number_format"):
                    lk["number_format"] = st["number_format"]
                bd = st.get("border")
                if bd:
                    # inside a range the left line is the inside vertical,
                    # the top line the inside horizontal -- as in the .bas
                    for name, weight in (
                            ("left", bd.get("left")),
                            ("right", bd.get("right") if c == c2
                             else bd.get("left")),
                            ("top", bd.get("top")),
                            ("bottom", bd.get("bottom") if r == r2
                             else bd.get("top"))):
                        if weight is not None:
                            side(r, c, name, weight)
    for o in sheet["outlines"]:
        r1, c1, r2, c2 = cells_of(o["range"])
        for r in range(r1, r2 + 1):
            side(r, c1, "left", o["weight"])
            side(r, c2, "right", o["weight"])
        for c in range(c1, c2 + 1):
            side(r1, c, "top", o["weight"])
            side(r2, c, "bottom", o["weight"])
    return looks


def look_key(lk):
    """A look as something hashable: equal looks share one cell format."""
    return ((lk["font"].get("name"), lk["font"].get("size"),
             bool(lk["font"].get("bold"))), lk["fill"],
            tuple(lk["border"].get(s) or None for s in SIDES), lk["h"],
            lk["v"], lk["number_format"])


def styles_part(looks):
    """xl/styles.xml for the looks used, and {look key: its xf index}."""
    fonts, fills, borders, numfmts, xfs = [], [], [], [], []

    def index(items, item):
        if item not in items:
            items.append(item)
        return items.index(item)

    xf_of = {}
    for key in dict.fromkeys(look_key(lk) for lk in looks.values()):
        font, fill, border, h, v, fmt = key
        f = index(fonts, font)
        fl = 0 if not fill else 2 + index(fills, fill)
        b = index(borders, border)
        n = 0 if fmt in (None, "", "General") else 164 + index(numfmts, fmt)
        xf_of[key] = 1 + index(xfs, (f + 1, fl, b + 1, n, h, v))

    out = [XML_HEAD, '<styleSheet xmlns="%s">' % NS_MAIN]
    if numfmts:
        out.append('<numFmts count="%d">%s</numFmts>' % (len(numfmts), "".join(
            '<numFmt numFmtId="%d" formatCode="%s"/>' % (164 + i, xml_text(f))
            for i, f in enumerate(numfmts))))
    out.append('<fonts count="%d">' % (len(fonts) + 1))
    for name, size, bold in [(FONT["name"], FONT["size"], False)] + fonts:
        out.append('<font>%s<sz val="%s"/><name val="%s"/></font>'
                   % ("<b/>" if bold else "", size, xml_text(name)))
    out.append('</fonts><fills count="%d"><fill>'
               '<patternFill patternType="none"/></fill>'
               '<fill><patternFill patternType="gray125"/></fill>'
               % (len(fills) + 2))
    for fill in fills:
        out.append('<fill><patternFill patternType="solid">'
                   '<fgColor rgb="FF%s"/></patternFill></fill>'
                   % fill.lstrip("#").upper())
    out.append('</fills><borders count="%d"><border/>' % (len(borders) + 1))
    for border in borders:
        out.append("<border>%s<diagonal/></border>" % "".join(
            '<%s style="%s"/>' % (s, w) if w and w != "none" else "<%s/>" % s
            for s, w in zip(SIDES, border)))
    out.append('</borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
               '<cellXfs count="%d"><xf/>' % (len(xfs) + 1))
    for f, fl, b, n, h, v in xfs:
        align = "".join(' %s="%s"' % (k, val) for k, val in
                        (("horizontal", h), ("vertical", v)) if val)
        out.append('<xf numFmtId="%d" fontId="%d" fillId="%d" borderId="%d" '
                   'applyNumberFormat="1" applyFont="1" applyFill="1" '
                   'applyBorder="1" applyAlignment="1">%s</xf>'
                   % (n, f, fl, b, "<alignment%s/>" % align if align else ""))
    out.append("</cellXfs></styleSheet>")
    return "".join(out), xf_of


def file_width(chars):
    """A column width as Excel shows it (7.71 characters) -> as the file
    holds it, cell padding included: 5 px on a 7 px digit of Calibri 11."""
    return round((chars * 7 + 5) / 7.0 * 256) / 256.0


def sheet_part(sheet, looks, xf_of):
    """xl/worksheets/sheet1.xml: the values, sizes, merges and the page."""
    values = {}
    for entry in sheet["values"]:
        for i, v in enumerate(entry["cells"]):
            if v is not None and v != "":
                values[(entry["row"], i + 1)] = v
    heights = dict((h["row"], h["height"]) for h in sheet["heights"])
    rows = sorted(set(r for r, _ in values) | set(r for r, _ in looks)
                  | set(heights))

    out = [XML_HEAD, '<worksheet xmlns="%s"><sheetPr>'
           '<pageSetUpPr fitToPage="1"/></sheetPr>'
           '<sheetFormatPr defaultRowHeight="15"/><cols>' % NS_MAIN]
    for i, c in enumerate(sheet["columns"]):
        out.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                   % (i + 1, i + 1, file_width(c["width"])))
    out.append("</cols><sheetData>")
    for r in rows:
        attrs = ""
        if r in heights:
            attrs = ' ht="%s" customHeight="1"' % heights[r]
        out.append('<row r="%d"%s>' % (r, attrs))
        cols = sorted(set(c for rr, c in values if rr == r)
                      | set(c for rr, c in looks if rr == r))
        for c in cols:
            s = xf_of[look_key(looks[(r, c)])] if (r, c) in looks else 0
            cell = '<c r="%s" s="%d"' % (ref(c, r), s)
            v = values.get((r, c))
            if v is None:
                out.append(cell + "/>")
            elif isinstance(v, bool) or not isinstance(v, (int, float)):
                # text stays text: a name such as 1/2 is not made a date
                out.append(cell + ' t="inlineStr"><is><t xml:space="preserve">'
                           '%s</t></is></c>' % xml_text(v))
            else:
                out.append(cell + "><v>%r</v></c>" % v)
        out.append("</row>")
    out.append("</sheetData>")
    if sheet["merges"]:
        out.append('<mergeCells count="%d">%s</mergeCells>'
                   % (len(sheet["merges"]), "".join(
                       '<mergeCell ref="%s"/>' % m for m in sheet["merges"])))
    page = sheet["page"]
    m = page.get("margins_in") or {}
    out.append('<pageMargins left="%s" right="%s" top="%s" bottom="%s" '
               'header="%s" footer="%s"/>'
               % tuple(m.get(k, d) for k, d in
                       (("left", 0.7), ("right", 0.7), ("top", 0.75),
                        ("bottom", 0.75), ("header", 0.3), ("footer", 0.3))))
    out.append('<pageSetup paperSize="%d" orientation="%s" fitToWidth="%d" '
               'fitToHeight="%d"/></worksheet>'
               % (PAPER.get(str(page.get("paper", "A4")).upper(), 9),
                  "landscape" if page.get("orientation") == "landscape"
                  else "portrait",
                  page.get("fit_width") or 0, page.get("fit_height") or 0))
    return "".join(out)


def xlsx_parts(doc):
    """The document's sheet as an .xlsx: [(path in the archive, text)]."""
    sheet = doc["sheet"]
    looks = resolve(sheet)
    styles, xf_of = styles_part(looks)
    return [
        ("[Content_Types].xml", XML_HEAD +
         '<Types xmlns="%scontent-types">'
         '<Default Extension="rels" ContentType="application/'
         'vnd.openxmlformats-package.relationships+xml"/>'
         '<Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/xl/workbook.xml" '
         'ContentType="%ssheet.main+xml"/>'
         '<Override PartName="/xl/worksheets/sheet1.xml" '
         'ContentType="%sworksheet+xml"/>'
         '<Override PartName="/xl/styles.xml" ContentType="%sstyles+xml"/>'
         "</Types>" % (NS_PKG, OOXML, OOXML, OOXML)),
        ("_rels/.rels", XML_HEAD +
         '<Relationships xmlns="%srelationships"><Relationship Id="rId1" '
         'Type="%s/officeDocument" Target="xl/workbook.xml"/></Relationships>'
         % (NS_PKG, NS_REL)),
        ("xl/workbook.xml", XML_HEAD +
         '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="%s" '
         'sheetId="1" r:id="rId1"/></sheets></workbook>'
         % (NS_MAIN, NS_REL, xml_text(sheet["name"]))),
        ("xl/_rels/workbook.xml.rels", XML_HEAD +
         '<Relationships xmlns="%srelationships">'
         '<Relationship Id="rId1" Type="%s/worksheet" '
         'Target="worksheets/sheet1.xml"/>'
         '<Relationship Id="rId2" Type="%s/styles" Target="styles.xml"/>'
         "</Relationships>" % (NS_PKG, NS_REL, NS_REL)),
        ("xl/styles.xml", styles),
        ("xl/worksheets/sheet1.xml", sheet_part(sheet, looks, xf_of)),
    ]


def xlsx_name(project):
    """The archive's name, no extension: the project, minus what Windows
    forbids in a file name."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", project).strip(" .")
    return name or "cut list"


# ---------------------------------------------------------------------------
# cutting the sheet down
# ---------------------------------------------------------------------------

def cut(sheet, row_of, col_of):
    """A copy of the sheet with only some of its rows and columns, moved to
    close the gaps. row_of and col_of take a row or column number to its new
    one, or to None to leave it out. A range keeps what is left of it, or
    goes if nothing is; a merge left one cell is no merge."""
    def span(first, last, new):
        kept = [n for n in (new(i) for i in range(first, last + 1))
                if n is not None]
        return (min(kept), max(kept)) if kept else None

    def move(rng):
        r1, c1, r2, c2 = cells_of(rng)
        rows, cols = span(r1, r2, row_of), span(c1, c2, col_of)
        if rows is None or cols is None:
            return None
        return "%s:%s" % (ref(cols[0], rows[0]), ref(cols[1], rows[1]))

    values = []
    for entry in sheet["values"]:
        r = row_of(entry["row"])
        if r is None:
            continue
        cells = {}
        for i, v in enumerate(entry["cells"]):
            c = col_of(i + 1)
            if c is not None:
                cells[c] = v
        values.append({"row": r, "cells": [cells.get(c) for c in
                                           range(1, max(cells or [0]) + 1)]})
    columns = sorted((col_of(i + 1), c["width"])
                     for i, c in enumerate(sheet["columns"])
                     if col_of(i + 1) is not None)
    out = dict(sheet)
    out["values"] = values
    out["columns"] = [{"col": col(c), "width": w} for c, w in columns]
    out["heights"] = [dict(h, row=row_of(h["row"])) for h in sheet["heights"]
                      if row_of(h["row"]) is not None]
    for key in ("formats", "outlines"):
        out[key] = [dict(f, range=move(f["range"])) for f in sheet[key]
                    if move(f["range"])]
    out["merges"] = [m for m in (move(m) for m in sheet["merges"])
                     if m and m.split(":")[0] != m.split(":")[1]]
    return out


def first_cells(c):
    """A column of the whole sheet -> its column in the short one, or None
    for an edge's second and third cells."""
    last_edge = FIRST_EDGE_COL + N_EDGES * CELLS_PER_EDGE - 1
    if c < FIRST_EDGE_COL:
        return c
    if c > last_edge:
        return c - (last_edge - FIRST_EDGE_COL + 1) + N_EDGES
    k, i = divmod(c - FIRST_EDGE_COL, CELLS_PER_EDGE)
    return FIRST_EDGE_COL + k if i == 0 else None


def short_sheet(sheet):
    """The sheet with one cell per edge."""
    if len(sheet["columns"]) != N_COLS:
        raise ValueError("the sheet has %d columns, not the %d of A:Q it "
                         "cuts down" % (len(sheet["columns"]), N_COLS))
    return cut(sheet, lambda r: r, first_cells)



# ---------------------------------------------------------------------------
# Grasshopper plumbing
# ---------------------------------------------------------------------------

try:
    JSON
except NameError:
    JSON = None


def texts(tree):
    """Every item of the input, as text, however it was wired."""
    if tree is None:
        return []
    if hasattr(tree, "Branches"):
        items = [i for b in tree.Branches for i in b]
    elif isinstance(tree, (list, tuple)):
        items = list(tree)
    else:
        items = [tree]
    out = []
    for item in items:
        inner = getattr(item, "Value", None)
        item = item if inner is None else inner
        if item is not None:
            out.append(str(item))
    return out


def read_doc(notes):
    """The JSON's document, or None and an ERROR in notes."""
    text = "\n".join(texts(JSON)).strip().lstrip("\ufeff")
    if not text:
        notes.append("no JSON - nothing to write")
        return None
    try:
        doc = json.loads(text)
    except ValueError as e:
        notes.append("ERROR: JSON does not read as JSON - %s" % e)
        return None
    if not isinstance(doc, dict) or doc.get("format") != DOC_FORMAT:
        notes.append("ERROR: this JSON is not gh_cutlist2json's - its "
                     "\"format\" is not \"%s\"" % DOC_FORMAT)
        return None
    if doc.get("version", 0) > DOC_VERSION:
        notes.append("ERROR: the JSON is version %s; this script reads up "
                     "to version %d" % (doc.get("version"), DOC_VERSION))
        return None
    if not isinstance(doc.get("sheet"), dict):
        notes.append("ERROR: the JSON has no \"sheet\"")
        return None
    return doc


INFO = DataTree[object]()
PATH = TEXT = NAME = None
notes = []

doc = read_doc(notes)
if doc:
    try:
        sheet = short_sheet(doc["sheet"])
        parts = xlsx_parts(dict(doc, sheet=sheet))
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        notes.append("ERROR: the JSON's sheet is incomplete - %s: %s"
                     % (type(e).__name__, e))
    else:
        PATH = [path for path, _ in parts]
        TEXT = [text for _, text in parts]
        NAME = xlsx_name(doc.get("project") or "")
        notes.append("%s.xlsx - %d parts, %d rows of the sheet, columns "
                     "A:%s" % (NAME, len(parts), len(sheet["values"]),
                               col(len(sheet["columns"]))))
for note in notes:
    if note.startswith("ERROR"):
        try:
            ghenv.Component.AddRuntimeMessage(          # noqa: F821
                GH_RuntimeMessageLevel.Error, note)
        except NameError:
            pass
    INFO.Add(note, GH_Path(0))
