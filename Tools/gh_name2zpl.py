# -*- coding: utf-8 -*-
r"""
gh_name2zpl.py -- Grasshopper Script component: panel names -> Code 128
labels, as one ZPL file ready to send to the printer.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   NAME   str      access = Tree   one panel name per label
    input   QTY    int      access = Tree   copies of each label, optional
    input   PATH   str      access = Item   where to write the .zpl, optional
    input   WRITE  bool     access = Item   write it, optional
    output  ZPL    -                        the whole file, one string
    output  LABEL  -                        one label per name
    output  FILE   -                        the file written, if it was
    output  INFO   -                        a report

Wire the panel names you already have -- NAME from `gh_brep2mpr.py`, a list of
piece IDs, anything -- and ZPL comes out as one string holding every label,
line endings embedded. LABEL is the same labels one by one, keeping NAME's
paths, for when only some of them are to be printed.

Nothing is encoded here by hand: `^BC` is the printer's own Code 128, so the
subsets, the check digit and the quiet zones are its business. What this
component does is lay the label out, keep the data printable, and size the
bars so the code fits the stock.

The label
---------
    +--------------------------+
    |      0_600x400-F_4       |   the name, centred, up to two lines
    |                          |
    |     || ||| | || |||      |   Code 128 of the same name
    +--------------------------+

Sizes are in millimetres in the settings below and turned into dots with DPI.
Set those two to whatever the printer and the stock actually are -- a 300 dpi
printer given a file written for 203 dpi prints a label two thirds the size,
and no error anywhere says so.

The bars are drawn with the widest module that still fits the label, from
MODULE_MAX dots down to MODULE_MIN. A name too long to fit even at MODULE_MIN
is still written out, and INFO says which ones and by how much: a clipped
barcode does not scan, and it is better to hear it here than at the machine.

What can be in a name
---------------------
Code 128 carries printable ASCII, so anything outside it -- an accented
letter, a dash that came out of a word processor -- has no barcode and the
label is left out rather than printed wrong. INFO names it. `^` and `~` are
ZPL's own control characters and would otherwise cut the field short, and `\`
starts an escape of `^FB`'s own; all three are written as hex under `^FH` and
come out of the scanner as themselves.

The same name twice is printed twice. That is usually a mistake -- two pieces
sharing a name are two pieces nobody can tell apart afterwards -- so INFO says
where. Use QTY for a piece that simply needs several labels; it becomes `^PQ`,
which the printer repeats itself.

Sending it
----------
The file is plain ZPL: it goes to the printer as bytes, not through a driver.

    copy /b labels.zpl \\server\zebra
    lpr -S 192.168.1.50 -P raw labels.zpl

Trees
-----
NAME's paths are kept on LABEL. QTY is read branch for branch with NAME where
the paths agree and by position otherwise, like the other components here; a
single QTY covers the whole lot. ZPL is the labels of every branch in order,
in one string.
"""

from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

DPI = 203                   # printer resolution: 203, 300 or 600
LABEL_W_MM = 70.0           # the stock, across the web
LABEL_H_MM = 40.0           # the stock, along the web
MARGIN_MM = 3.0             # kept clear on every side

TITLE_MM = 4.0              # cap height of the name above the bars
TITLE_LINES = 2             # how many lines a long name may wrap over
GAP_MM = 3.0                # between the name and the bars
BAR_H_MM = 15.0             # height of the bars themselves
HUMAN_READABLE = False      # the printer's own line under the bars as well

MODULE_MAX = 4              # widest bar module to try, in dots
MODULE_MIN = 2              # narrowest -- below this a handheld starts to miss
RATIO = 3.0                 # wide bar : narrow bar

ENCODING = "utf-8"          # ^CI28 below must agree with this
NEWLINE = "\r\n"
DEFAULT_FILE = "labels.zpl"


# ---------------------------------------------------------------------------
# dots
# ---------------------------------------------------------------------------


def dots(mm):
    """Millimetres as whole printer dots, never below one."""
    return max(1, int(round(mm * DPI / 25.4)))


def fnum(value):
    """A number as ZPL takes it: 3.0, not 3."""
    return "%.1f" % float(value)


# ---------------------------------------------------------------------------
# the data
# ---------------------------------------------------------------------------


def printable(data):
    """Code 128 carries ASCII 32..126 and nothing else here."""
    return all(32 <= ord(ch) <= 126 for ch in data)


def escape(data):
    r"""Field data as it is written under ^FH.

    ^ and ~ end a field or start a control sequence, so they go in as _5E and
    _7E; \ starts one of ^FB's own escapes and goes in as _5C; and _, being
    the escape character itself, has to go in as _5F or it would eat the two
    characters after it. ^FH turns the hex back into the character after the
    line has been parsed, so none of them is read as a control any more.
    """
    out = []
    for ch in data:
        out.append("_%02X" % ord(ch) if ch in "^~_\\" else ch)
    return "".join(out)


def symbols(data):
    """How many Code 128 symbols the data takes, near enough to place it.

    ^BC in auto mode packs digits two to a symbol in subset C and everything
    else one to a symbol. Only the two ends of that are worth counting: it is
    the width on the label that is being worked out, and a name is either a
    number or it is not.
    """
    if data.isdigit():
        return (len(data) + 1) // 2
    return len(data)


def bar_modules(data):
    """The width of the printed code, in modules.

    Start, check and stop are 11 modules each bar the stop, which carries a
    thirteenth: 11 * (symbols + 2) + 13.
    """
    return 11 * (symbols(data) + 2) + 13


def module_for(data, usable):
    """The widest module the code fits in. -> (module, width), both in dots.

    The width is given back even when it is over the label: the caller says
    so, rather than dropping the label or thinning the bars past what a
    handheld can read.
    """
    count = bar_modules(data)
    for module in range(MODULE_MAX, MODULE_MIN - 1, -1):
        if count * module <= usable:
            return module, count * module
    return MODULE_MIN, count * MODULE_MIN


# ---------------------------------------------------------------------------
# the label
# ---------------------------------------------------------------------------


def label(data, qty=1, note=""):
    """One whole label, ^XA to ^XZ. -> (text, how far over the edge)."""
    width, height = dots(LABEL_W_MM), dots(LABEL_H_MM)
    margin = dots(MARGIN_MM)
    usable = width - 2 * margin

    title_h = dots(TITLE_MM)
    bar_h = dots(BAR_H_MM)
    bar_y = margin + title_h * TITLE_LINES + dots(GAP_MM)

    module, bar_w = module_for(data, usable)
    # ^FB centres the text over a width of its own; bars are placed, so they
    # are centred by hand -- and kept at the margin when they are too wide,
    # so what is lost is the right hand end and not both ends.
    bar_x = margin + max(0, (usable - bar_w) // 2)

    text = escape(data)
    lines = ["^XA"]
    if note:
        # ^FX is ZPL's comment: it is read and nothing is printed for it.
        lines.append("^FX%s^FS" % note.replace("^", " ").replace("~", " "))
    lines += [
        "^CI28",                                # the file is UTF-8
        "^PW%d" % width,
        "^LL%d" % height,
        "^LH0,0",
        # \& ends the last line of a ^FB block. Without it the block has no
        # line to centre and the name is left where it starts, which is what
        # a validator means by "centered but does not end with a separator".
        r"^FO%d,%d^A0N,%d,%d^FB%d,%d,0,C^FH^FD%s\&^FS"
        % (margin, margin, title_h, title_h, usable, TITLE_LINES, text),
        "^BY%d,%s,%d" % (module, fnum(RATIO), bar_h),
        "^FO%d,%d^BCN,%d,%s,N,N,A^FH^FD%s^FS"
        % (bar_x, bar_y, bar_h, "Y" if HUMAN_READABLE else "N", text),
    ]
    if qty > 1:
        lines.append("^PQ%d,0,0,N" % qty)
    lines.append("^XZ")
    return NEWLINE.join(lines) + NEWLINE, max(0, bar_w - usable)


def too_tall():
    """How far the layout runs past the bottom of the label, in dots."""
    used = (dots(MARGIN_MM) + dots(TITLE_MM) * TITLE_LINES + dots(GAP_MM)
            + dots(BAR_H_MM) + dots(MARGIN_MM))
    return max(0, used - dots(LABEL_H_MM))


def header(count):
    """What the file says about itself, in the first label's comment."""
    return "gh_name2zpl - %d label%s, Code 128, %d dpi, %s x %s mm" % (
        count, "" if count == 1 else "s", DPI, fnum(LABEL_W_MM),
        fnum(LABEL_H_MM))


# ---------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------


def out_path(path):
    """PATH as a file to write: a folder gets DEFAULT_FILE inside it."""
    import os
    path = str(path).strip().strip('"')
    if not path:
        return ""
    if os.path.isdir(path):
        return os.path.join(path, DEFAULT_FILE)
    if not os.path.splitext(path)[1]:
        return path + ".zpl"
    return path


def write_file(path, text):
    """Write the labels where PATH says. -> what was written."""
    import io
    import os
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    # newline="" so the CRLF already in the text is left as it is.
    with io.open(path, "w", encoding=ENCODING, newline="") as handle:
        handle.write(text)
    return path


# ---------------------------------------------------------------------------
# reading the input
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


def unwrap(item):
    """The value inside a Grasshopper wrapper, or the item as it came."""
    inner = getattr(item, "Value", None)
    return item if inner is None else inner


def as_text(item):
    """An item as the name it stands for, tidied of stray whitespace."""
    if item is None:
        return ""
    return " ".join(str(unwrap(item)).split())


def as_qty(item):
    """A count of labels, or 1 when it is not a count."""
    try:
        number = int(round(float(unwrap(item))))
    except (TypeError, ValueError):
        return 1
    return number if number >= 1 else 1


def as_bool(value, default=False):
    """A Grasshopper boolean may arrive as a bool, a number or a string."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(unwrap(value)).strip().lower()
    if text in ("true", "1", "1.0", "yes", "y", "t"):
        return True
    if text in ("false", "0", "0.0", "no", "n", "f", ""):
        return False
    return default


def name_of(text):
    """A name as INFO shows it -- short, and never throws."""
    return text if len(text) <= 32 else text[:29] + "..."


class Column(object):
    """QTY read against the names: by path, or by position, or one for all."""

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
        if len(self.flat) == 1:
            return self.flat[0]     # one QTY covers the whole lot
        if n < len(self.flat):
            return self.flat[n]
        return None


# ---------------------------------------------------------------------------
# Grasshopper plumbing
# ---------------------------------------------------------------------------

ZPL = ""
LABEL = DataTree[object]()
FILE = None
INFO = DataTree[object]()

# Everything but NAME is optional: the component still runs with only NAME.
try:
    QTY
except NameError:
    QTY = None
try:
    PATH
except NameError:
    PATH = None
try:
    WRITE
except NameError:
    WRITE = False

write = as_bool(WRITE)
quantities = Column(QTY)
branches = branches_of(NAME)
if not branches:
    INFO.Add("nothing on NAME - no labels to make", GH_Path(0))

parts = []                          # the labels, in the order they print
seen = {}                           # name -> which label it was first on
n = 0                               # which name this is, over every branch

for path, items in branches:
    tag = str(path)
    for j, item in enumerate(items):
        if item is None:
            continue
        data = as_text(item)
        n += 1
        if not data:
            INFO.Add("%s   item %d is empty - no label" % (tag, j), path)
            continue
        if not printable(data):
            odd = sorted(set(ch for ch in data if not printable(ch)))
            INFO.Add("%s   %s has %s, which Code 128 cannot carry - no label"
                     % (tag, name_of(data),
                        ", ".join("'%s'" % ch for ch in odd)), path)
            continue

        qty = as_qty(quantities.get(path, j, n - 1))
        text, over = label(data, qty)
        parts.append((data, qty, text))
        LABEL.Add(text, path)

        if over:
            INFO.Add("WARNING: %s   the barcode is %d dot%s wider than the "
                     "label and would be clipped - shorten the name, use "
                     "wider stock, or lower MODULE_MIN"
                     % (name_of(data), over, "" if over == 1 else "s"), path)
        if data in seen:
            INFO.Add("WARNING: %s   the same name is already on label %d - "
                     "two pieces under one name cannot be told apart "
                     "afterwards. QTY is how one piece gets several labels."
                     % (name_of(data), seen[data]), path)
        else:
            seen[data] = len(parts)
        if qty > 1:
            INFO.Add("%s   %s   x%d" % (tag, name_of(data), qty), path)

if parts:
    # Only whole ^XA...^XZ formats go in the file, so what the file has to
    # say about itself goes in as a comment inside the first of them.
    texts = [text for _data, _qty, text in parts]
    texts[0] = label(parts[0][0], parts[0][1], header(len(parts)))[0]
    ZPL = "".join(texts)
    INFO.Add("%d label%s of %d name%s, Code 128, %d dpi, %s x %s mm"
             % (len(parts), "" if len(parts) == 1 else "s", n,
                "" if n == 1 else "s", DPI, fnum(LABEL_W_MM),
                fnum(LABEL_H_MM)), GH_Path(0))
    over = too_tall()
    if over:
        INFO.Add("WARNING: the name, the gap and the bars come to %d dots "
                 "more than the label is tall - lower BAR_H_MM, TITLE_MM or "
                 "TITLE_LINES" % over, GH_Path(0))

target = out_path(PATH) if PATH else ""
if target and not parts:
    INFO.Add("nothing to write - no labels were made", GH_Path(0))
elif target and not write:
    INFO.Add("set WRITE to true to write %s" % target, GH_Path(0))
elif target:
    try:
        FILE = write_file(target, ZPL)
        INFO.Add("written: %s" % FILE, GH_Path(0))
    except Exception as exc:
        INFO.Add("ERROR: %s could not be written - %s" % (target, exc),
                 GH_Path(0))
elif write:
    INFO.Add("WRITE is on but PATH is empty - nowhere to write", GH_Path(0))
