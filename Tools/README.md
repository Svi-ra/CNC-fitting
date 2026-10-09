# DXF → woodWOP MPR batch converter

`dxf2mpr.py` reads DXF files and writes a woodWOP `.mpr` program for each one.
It exists because woodWOP DXF-Import cannot read the DXF files this project
produces: they contain a 3D solid (ACIS), not the 2D geometry on named layers
that DXF-Import expects. This tool goes straight from the solid to MPR and
skips DXF-Import entirely.

Nothing to install — Python 3.8 or newer, standard library only.

## Quick start

```bash
python Tools/dxf2mpr.py Examples/CAD-models/Noptiera-1.dxf
```

Batch a whole folder into one output directory, with a report:

```bash
python Tools/dxf2mpr.py C:\parts -r -o C:\out --log C:\out\convert-log.csv
```

On a shop PC you can also drag DXF files (or a folder) onto
`Tools/dxf2mpr.cmd`. It writes the programs into an `MPR` sub-folder next to
what you dropped.

Check the result before it goes to the machine:

```bash
python Tools/check_mpr.py C:\out -r
```

## What it reads

**3D solids** (`3DSOLID`, `BODY`, `REGION`) — both ACIS encodings are handled:

| DXF version | ACIS form | status |
| --- | --- | --- |
| up to AutoCAD 2010 (AC1021, AC1024) | ASCII SAT, obfuscated | read |
| AutoCAD 2013 and newer (AC1027, AC1032) | binary SAB/ASM in `ACDSDATA` | read |
| binary DXF | — | rejected with a message; re-save as ASCII |

Every ACIS *body* becomes its own MPR. A DXF holding a whole assembly (like
`Examples/CAD-models/Test-noptiera.dxf`, 9 solids) produces
`<name>_1.mpr` … `<name>_9.mpr`. Use `--largest-only` to keep just the biggest.

**2D geometry on woodWOP layers** — used when no solid is present, so DXFs
prepared the "official" way convert through the same tool:

| Layer | CAD element | Result |
| --- | --- | --- |
| `Werkstk_<t>`, `ProcPart_<t>` | rectangle | part size, thickness from the name |
| `V_Bohr<m>[_<d>]`, `V_Drill<m>[_<d>]` | circle | `<102 BohrVert>`, Ø from the circle |
| `H_Bohr_<z>`, `H_Drill_<z>` | block insert | `<103 BohrHoriz>`, direction from the insert angle |
| `V_Fraes_<z>T<n>`, `V_Trim_…`, `Geometrie_<z>`, `Nest_…` | lines/arcs/polylines | contour + `<105 Konturfraesen>` |

Layer numbers use `_` as the decimal point, as woodWOP does
(`V_Bohr1_12_5` = mode 1, depth 12.5 mm).

## What it writes

| Feature found | MPR macro |
| --- | --- |
| panel bounding box | `<100 \WerkStck\` |
| bore along Z, open at the top | `<102 \BohrVert\` |
| bore along Z, open only at the bottom | `<131 \UfluBohr\` |
| bore along X or Y, open at an edge | `<103 \BohrHoriz\` |
| bore at any other angle | `<104 \BohrUniv\` (needs a swivel unit) |
| outline that is not the bounding rectangle | contour `]n` + `<105 \Konturfraesen\` |

This is the DXF converter's mapping. The Grasshopper component below
differs in two ways: it never writes `<131 UfluBohr>`, because its machine
drills from one side only and an underside bore is handled by turning the
piece over, and it additionally writes `<109 \Nuten\` for sawn grooves.

Coordinate system (woodWOP coordinate system 0): origin at the lower left
corner of the underside, X = length, Y = width, Z = 0 at the bottom face.
Vertical drillings enter from the top, `TI` is the depth. `ZA` of a horizontal
drilling is the height above the bottom face.

Files are written **CRLF** in cp1252, matching the MPR files already in
`Examples/PAL_8681_SM_Alb_Diamant/`. This matters: woodWOP splits the program
on CRLF, so an LF-only file is read as a single unparseable line and opens
silently as an empty default blank instead of reporting an error.
`check_mpr.py` checks for this.

## Automatic orientation

Parts modelled in their assembled position are laid down for machining:

1. the thinnest direction is rotated to Z (only when it is clearly a panel —
   under 60 % of the next smallest dimension);
2. the part is turned so the longer side runs along X;
3. if all the vertical drilling would come from underneath, the part is
   turned over so it is drilled from above;
4. the part is moved to the zero point.

Every one of these is reported as a `note:` line and recorded in the CSV log.
Switch them off with `--no-orient`, `--no-long-x`, `--no-flip`,
`--no-normalize`.

## Options

```
-o, --outdir DIR      output folder (default: next to each DXF)
-r, --recursive       recurse into sub folders
    --ext .MPR        output extension (default .mpr)
    --thickness 19    force the part thickness
    --snap 0.5        round drill diameters to a step
    --max-dia 60      larger round openings are not treated as drillings
    --bm-vert SS      drill mode for vertical bores (LS SS LSL SSS)
    --largest-only    keep only the biggest solid in a multi-solid DXF
    --force-2d        ignore solids, read woodWOP layers only
    --hbore-dia / --hbore-depth   fallbacks for H_Bohr blocks without attributes
    --log FILE        CSV report (source, output, size, macros, notes)
-n, --dry-run         analyse only, write nothing
```

## Grasshopper component

`gh_brep2mpr.py` is the same MPR writer driven from Rhino instead of from a
DXF. Paste the whole file into a **Rhino 8 Script component set to Python 3**:

| | Name | Type | Access | |
| --- | --- | --- | --- | --- |
| input | `B` | Brep | **Tree** | one part per branch |
| input | `ID` | str | **Tree** | piece ID — optional |
| input | `QTY` | int | **Tree** | how many of this piece — optional |
| input | `DIR` | bool | **List** | grain direction per part — optional |
| input | `MAT` | str | **List** | material per part — optional |
| output | `MPR` | — | | one whole program per setup, line endings embedded |
| output | `NAME` | — | | the file name for each program |
| output | `INFO` | — | | one report per part |
| output | `TABLE` | — | | the cut list, one line per piece |

`MPR` and `NAME` are parallel trees: item *i* of a branch is the program, item
*i* of the same branch in `NAME` is what to call it. The component runs with
only `B` wired; everything else may be left off.

`ID` and `QTY` can each be wired either branch-for-branch with `B`, or as one
flat list in part order. With no `ID` the programs are simply numbered in the
order they are written — `0`, `1`, `2` … — with no gaps, however many solids
were folded together.

`DIR` and `MAT` are different: they are plain lists as long as the list of
parts, read straight through in the order the parts arrive on `B`. See
[Material, grain and the cut list](#material-grain-and-the-cut-list).

### What the machine can reach

The drilling head cannot do every hole in one clamping, so **one part may come
out as more than one program**. What it is fitted with lives in one dict near
the top of the file:

```python
MACHINE = {
    "vert_blind": (35.0, 20.0, 15.0, 10.0, 8.0, 7.0, 5.0),  # dead-end, from above
    "vert_thru":  (7.0, 5.0),                               # right through
    "YM": (8.0,),        # top edge,   Y = BR, drills towards -Y
    "YP": (4.5,),        # lower edge, Y = 0,  drills towards +Y
    "XM": (8.0, 4.5),    # right edge, X = LA, drills towards -X
    "XP": (8.0, 4.5),    # left edge,  X = 0,  drills towards +X
}
```

Two constraints follow from it:

* the vertical array is a bank of fixed spindles working from **one side
  only**, so a bore that opens at the underside is reachable only with the
  piece turned over. A bore that breaks out the far side is checked against
  `vert_thru`, everything else against `vert_blind`;
* the horizontal spindles carry a **different bit on each side** — the top
  edge drills Ø8 only, the lower edge Ø4.5 only, left and right do both;
* the grooving saw runs **along X only** with a 4 mm blade, and saws from the
  top face — see [Grooves](#grooves) below.

The piece always lies with its long side on X, but **four ways round**:

| Placement | What it does to the piece | Edges |
| --- | --- | --- |
| `F` face up | as modelled | as modelled |
| `F` face up, turned end for end | 180° in its own plane | top ↔ lower, left ↔ right |
| `B` turned over | 180° about the long (X) axis | top ↔ lower |
| `B` turned over about its short axis | 180° about the short (Y) axis | left ↔ right |

Turning over brings the underside up; turning end for end keeps the face up.
Because the top and lower edges carry different bits, both moves change what
the horizontal spindles can reach. Every bore and groove is tried all four
ways, and **at most two setups** are used — one face up, one turned over:

* a bore that works only some ways **steers** the choice of placement;
* one that works in every setup chosen — a through bore, anything in the left
  or right edge — rides along with the first;
* one that works in none of them is named in `INFO` and left out of the
  program. Set `STRICT = False` to have it written anyway; it is still
  reported.

Which plan wins is decided in this order: **reach every bore** the machine can
reach at all; then **hold the piece best** (see
[Holding the piece](#holding-the-piece)); only then **the fewest setups**; and
face up, as modelled, when nothing else decides. A piece with only Ø4.5 holes
in its top edge therefore needs no flip: turned end for end they sit in the
lower edge, in one setup. `INFO` names the placement of each setup and how
the piece is turned between the two.

So a piece with Ø8 *and* Ø4.5 holes in its top edge comes out as two programs:

```
ND0142_800x400-F_4.mpr   <103 BohrHoriz> XA=300 YA=400 ZA=9 DU=8   BM="YM"
ND0142_800x400-B_4.mpr   <103 BohrHoriz> XA=500 YA=0   ZA=9 DU=4.5 BM="YP"
```

The first drills the Ø8 with the piece face up. The second is written for the
flipped piece, where those Ø4.5 holes now sit in the lower edge. Turn the
finished part back over and every hole is where the model put it.

**"Top edge" means Y = `BR`** and lower means Y = 0, as woodWOP draws the part
in plan. If the shop means it the other way round, swap those two lines in
`MACHINE`.

**A bore is one hole only where its faces meet.** Cylinder faces on the same
axis with the same diameter are joined when their extents overlap or touch —
the halves of one bore, or a through bore modelled in two pieces. Two bores on
one axis with material between them stay two holes, so marks punched from both
faces of a panel are two dead-end bores, one per setup, not one through bore.

### Holding the piece

The machine grips the piece by its edges and corners, so a placement that puts
a cut corner, a rebate or a pocket where the gripper takes hold gives a piece
that cannot be held. The zones it needs, most important first, **as the panel
is seen from its back** with the face towards the tools — the mirror image of
the woodWOP view, so "right" here is X = 0 in the program:

| Rank | Zone | In the program |
| --- | --- | --- |
| 1 | lower-right corner | X 0, Y 0 |
| 2 | right edge | X 0 |
| 3 | upper-right corner | X 0, Y BR |
| 4 | lower edge | Y 0 |
| 5 | lower-left corner | X LA, Y 0 |
| 6 | upper-left corner | X LA, Y BR |
| 7 | left edge | X LA |
| 8 | upper edge | Y BR |

Each zone is measured on the solid itself: columns are sampled over it, and
a column counts only where the panel is there **through its whole
thickness** — so a pocket or rebate from either face takes it away, as a cut
corner does. Drilled bores do not count against a zone: a dowel or a cup hole
near a corner must not cost the piece a setup. Corners are `GRIP_CORNER`
squares, edges `GRIP_EDGE`-deep strips the length of the edge. The shares are
weighted 128, 64, 32 … down the list, so losing a whole zone costs more than
losing every zone below it, while a small nick high up can still lose to a
large cut lower down. A plan is judged by the weaker of its setups.

**Holding comes before the number of setups.** Take a 323 × 78 piece with an
R78 radius on one corner, Ø4.5 holes in the lower edge, Ø8 in the top edge, a
Ø4.5 in the end and two Ø15 blind from the face. Face up, everything is in
reach in one clamping — but the radius takes the right edge and the
upper-right corner. So it comes out as two programs instead:

```
5_323x78-B_2.mpr   turned over about its short axis   7 x BohrHoriz
5_323x78-F_2.mpr   face up, turned end for end        2 x BohrVert
```

`B` drills the edges with the radius at the upper-left; then the piece is
turned over about its long axis and `F` drills the two Ø15 with the radius at
the lower-left. **Of two setups, the better-held one goes first** — it is
where the piece is worked hardest. `INFO` says when a second setup was taken
for the grip alone, and warns when one of the first `GRIP_CHECK` zones is
still under `GRIP_WARN` solid in the placement chosen.

With nothing to steer it, a piece may also be machined **turned over** in one
setup, if that keeps the gripping zones more solid than face up.

```python
GRIP = True          # off: place by tool access alone, as before
GRIP_CORNER = 100.0  # side of the square checked at each corner, mm
GRIP_EDGE = 40.0     # depth of the strip checked along each edge, mm
GRIP_GRID = 4        # sample columns across a corner square (more = slower)
GRIP_CHECK = 3       # INFO warns when one of the first this-many zones ...
GRIP_WARN = 0.9      # ... is less solid than this
```

`GRIP_ZONES` holds the ranking and the zone positions; reorder it to change
the priorities. The check needs a **closed solid** — an open Brep is placed by
tool access alone, and `INFO` says so. Each sample is a `Brep.IsPointInside`
call, made only when the grip actually has a choice to make; raise
`GRIP_GRID` for finer detail at the cost of time.

The corner and edge sizes are placeholders: set them to the reach of the
actual gripper.

### Center punch

A vertical dead-end bore shallower than `PUNCH_DEPTH` (1 mm) is a **mark**,
not a hole: the 7 mm bit only dimples the face. It is written as an ordinary
`<102 \BohrVert\` with `BM="CP"` — woodWOP's *Center punch* mode, which lets
the cycle allow for the pointed tip. `TI` stays the depth as modelled.

```
<102 \BohrVert\   XA="68"  YA="197"  BM="CP"  TI="0.5"  DU="7"
```

This is exactly how woodWOP 9.0.152 saves it —
`Examples/WoodWop_export/0_340x252-B_1_Center-punch-mode.mpr`, where the marks
differ from the plain `LS` bores in `BM` alone. Dead-end bores 1 mm deep or
more keep `BM_VERT`. `PUNCH_DEPTH = 0` turns punching off.

### Through bores

A vertical bore that breaks out the far side is drilled **slow-fast-slow**, so
the bit eases out through the underside: `BM="LSL"` (`BM_THRU`), woodWOP's
*Slow-fast-slow through* mode. Like woodWOP's own save of it, the block carries
**no `TI`** — the cycle drills the part's own thickness.

```
<102 \BohrVert\   XA="101"  YA="291"  BM="LSL"  DU="8"
```

### Grooves

A groove is read off the solid as a **flat rectangular cavity floor lying
between the two faces** — a planar face whose normal is along Z at a height
that is neither 0 nor the panel thickness, with four straight edges square to
X and Y. Its short dimension is the width, its long one the run, and its
height gives the depth. A round-ended slot, a floor split over several faces
or any free-form cavity is reported in `INFO` and left alone, as pockets
always have been; the flat bottom of a blind bore is passed over in silence.

```python
GROOVE = True             # detect grooves at all
SAW_KERF = 4.0            # blade thickness, mm
SAW_ALONG = "X"           # directions the saw can run: "X", "Y" or "XY"
GROOVE_MAX_WIDTH = 40.0   # wider flat cavities are pockets, not grooves
GROOVE_RK = "WRKR"        # which side of the programmed edge the groove lies
```

A groove is rejected and reported if it runs a direction the saw cannot, is
narrower than the blade, or is wider than `GROOVE_MAX_WIDTH` — that is where
a groove stops being a groove and starts being a pocket. Wider than the blade
but under that limit is fine: woodWOP makes it in several passes.

Grooves go through the same setup planner as bores. `<109 Nuten>` saws from
the top face and carries no Z reference, and MPR 4.x has **no below-table
sawing macro at all** — only `<131 UfluBohr>`, `<151 UflurTasche>` and
`<113 Unterflur-Fraesen>`, which are drilling, pocketing and routing. So a
groove in the underside needs the piece turned over exactly as an underside
bore does, and rides along with that setup when the drilling already calls
for one.

**woodWOP programs a groove by one of its edges, not down its middle.**
`XA/YA`…`XE/YE` is one edge and `RK` offsets the blade a full `NB` to one
side. With `RK="WRKR"` the groove lies on the +Y side of a run towards +X.
This is checked against `Examples/WoodWop_export/0_472x420-F_1_Standard-mode.mpr`, a
woodWOP 9.0.152 program for the part that `Examples/Meshes/472x420.gltf`
holds as a model: a groove occupying Y 410…414 is written

```
<109 \Nuten\   XA="75"  YA="410"  XE="_BSX"  YE="410"  NB="8"  RK="WRKR"
```

Set `GROOVE_RK` to `"WRKL"` for the other side, or to `"NoWRK"` to programme
the centre line instead. The side convention is confirmed only for a run
towards +X, the direction this saw runs; the +Y case, reachable by setting
`SAW_ALONG = "XY"`, is derived by rotating that result and is unverified.

A groove that runs out to an edge **notches the face it was sawn into**, so
that face's outer loop is no longer the bounding rectangle. That notch
belongs to the groove, not to the panel outline — following it would rout the
panel to the shape of its own grooving — so the outline is taken from
whichever of the two faces still goes round the plain rectangle, and only
when neither does is the panel taken to be shaped at all.

### Shaped outlines are not milled

The machine has no router, so **an outline that is not the bounding rectangle
is not milled**: no contour `]1`, no `<105 \Konturfraesen\`. woodWOP flags
that block as an error — it names no tool, and there is none to name. The
piece has to arrive already cut to shape, and `INFO` says so. Its shape still
counts for [Holding the piece](#holding-the-piece), which is measured on the
solid.

`CONTOUR = True` writes the contour and its milling again, in the first setup
only — repeating it would cut air — with an `INFO` note when a second setup
follows, since a piece cut free in the first may no longer be held for the
second.

### Identical panels

**Solids of the same shape are converted once.** A nested sheet where the same
panel appears twenty times gives one program, not twenty, and the quantities
add up: the file comes out named for the total. The copies are recognised
before anything is planned, so a duplicate costs a bounding box and a walk
over its vertices rather than a full conversion.

Two solids count as the same shape when their vertices, and the radius and
axis of every cylindrical face, measure the same from the corner of their own
bounding boxes, within `DUP_TOL`, **and** they carry the same material and the
same grain direction — the very same shape cut from another board, or laid
across the grain, is a piece of its own however well the solids match. Position is therefore irrelevant — copies
laid out across a sheet still fold together. **Orientation is deliberately
not normalised:** a copy turned end for end carries its holes at the other end
and is a genuinely different program, so it stays separate.

```python
MERGE_IDENTICAL = True  # off converts every solid separately, as before
DUP_TOL = 0.01          # two solids count as the same shape within this, mm
```

The first solid of a group is the one converted, and its `ID` names the
programs. **Folding copies in eats no numbers:** where the numbering is left
to the component it counts programs, not solids, so a group of four still
advances the count by one and the piece after it takes the next number. A
piece with an `ID` of its own keeps it untouched.

`MPR` and `NAME` carry nothing for the copies; `INFO` gives each of them a
line saying which program covers it, and the surviving report names the copies
folded in — including a note if they did not all carry the same `ID`. A copy
that had no `ID` of its own has no number any more, so `INFO` points at it by
where it sat in the input instead.

### Material, grain and the cut list

`DIR` and `MAT` carry the per-part data the geometry does not. Each is a plain
list as long as the list of parts, read in the order the parts arrive on `B`:

| Input | Meaning |
| --- | --- |
| `DIR` | `True` — the first dimension runs along the grain, as modelled. `False` — the piece is laid 90° across the grain, so its two dimensions swap in the cut list. |
| `MAT` | `interior`, `base`, … — free text, carried through as given. |

Either may be left unwired: the pieces then all run along the grain, with no
material named. A list of the wrong length is read as far as it goes — the
parts past its end fall back on those defaults — and `INFO` says so, because
it is nearly always a wiring mistake. `DIR` takes a real boolean, a number, or
`"true"` / `"false"` as text.

Both feed the identical-panel test above, and both feed `TABLE`, the cut list:
a header line and then one line per piece.

```
Material;ID;Lungime;Latime;Cantitate
base;0;480;232;1
```

`ID` is which program the line is for, counting from zero, and is the same
number the file name carries. Solids folded into one program share that one
number, and the numbering runs on without gaps. `Lungime` is the dimension
along the grain —
the long side of the panel unless `DIR` said otherwise — and `Cantitate` is
the same total the file name carries. A part the converter throws out still
gets a line, sized from its bounding box, so nothing drops out of the list.

`DIR` changes the cut list only, never the program: the machine has no notion
of grain, so the sizes swap on the sheet while the holes stay exactly where
the model put them.

### File names

```
<ID>_<length>x<width>-<F|B>_<quantity>.mpr        ND0142_800x400-F_4.mpr
```

`F` = face up. `B` = turned over. Whether a setup is also turned end for end
is not in the name — `INFO` says it, and the program itself shows where
everything is. Of two programs, the one written first is the one to run
first; it may be `B`. The quantity is the sum of
`QTY` over the identical solids folded into that program — 1 per solid if
nothing came in on `QTY` — and is the same on every program of one piece.
Two pieces asking for the same name is caught and reported rather than
silently overwriting — give them distinct IDs. Change `EXT` for a different
extension, or `""` for a bare name.

### Line endings

`MPR` carries the line ending inside the string, CRLF by default, set by
`EOL`. woodWOP splits a program on CRLF; an LF-only file is read as one
unparseable line and opens silently as an empty default panel.

If the export path applies CRLF *itself* while joining, feeding it a string
that already contains CRLF gives CR CR LF — set `EOL` to `\n` in that case.

### The single-space lines are load bearing

The MPR format separates blocks with a line containing one space, and every
program in `Examples/PAL_8681_SM_Alb_Diamant/` has them. They look like stray
whitespace when you copy the text out of a panel, but they are required.
**Do not let the export path trim trailing whitespace.**

### Placement and settings

**Parts are expected to arrive lying flat in the world XY plane**, thickness
along Z. Nothing is ever rotated out of that plane. A part fed in standing on
edge is reported in `INFO` as a `WARNING` rather than quietly corrected,
because turning it would contradict the layout the definition produced.

Beyond that it takes raw solids with no attached data and recognises the rest:
the world bounding box gives the panel size, cylindrical faces become
drillings classified by which face they break out through, and the outline,
when it is not simply the bounding rectangle, is reported and used to place
the piece for the gripper — not milled.

| Setting | Default | Effect |
| --- | --- | --- |
| `LONG_X` | on | turn the part 90 degrees so its long side runs along X, as `LA`/`_BSX` expects. The top and lower edges follow the turn |
| `STRICT` | on | leave bores the head cannot reach out of the program; off writes them anyway |
| `DIA_TOL` | 0.2 | how far a measured diameter may sit from a listed one and still count as that bit |
| `EXT` | `.mpr` | appended to every `NAME` |
| `SAW_KERF` | 4.0 | grooving blade thickness; a narrower groove cannot be cut |
| `SAW_ALONG` | `"X"` | the directions the saw unit can run |
| `GROOVE_RK` | `"WRKR"` | which side of the programmed edge the groove lies |
| `MERGE_IDENTICAL` | on | convert one solid per shape and add the quantities up; off converts every solid separately |
| `DUP_TOL` | 0.01 | how far two solids may differ and still count as the same shape |
| `CONTOUR` | off | mill a shaped outline (`]1` + `<105 Konturfraesen>`); off while the machine has no router |
| `GRIP` | on | place each setup so the gripping zones stay solid — see [Holding the piece](#holding-the-piece) |
| `BM_THRU` | `"LSL"` | drill mode for through bores, written without `TI` |

Which face ends up on top, and which way round, is **not** a setting: it is
decided per part by the planner above, because it is a machining choice
rather than a property of the model. The rest of the block is `SNAP`,
`MAX_DIA`, `BM_VERT`, `BM_PUNCH`, `PUNCH_DEPTH`, `THICKNESS`, `GROOVE`,
`GROOVE_MAX_WIDTH`, the `GRIP_…` sizes and `EOL`.

It outputs **text, not files**. When you write it out, use CRLF —
`open(path, "w", encoding="cp1252", newline="\r\n")` — for the reason above.
Put a boolean `Run` gate in front of any file writing, or a solve on every
slider drag will write the whole batch.

**The model must be in millimetres.** The component never reads the Rhino
document — not its units, not its tolerance — because ShapeDiver forbids it;
see [ShapeDiver](#shapediver). Sizes are taken as mm as they stand, and
curves are recognised against a fixed `TOL = 0.001`.

## Labels

`gh_name2zpl.py` turns the panel names into Code 128 labels and returns them
as one ZPL text, ready to go to the printer. It is a second **Rhino 8 Script
component set to Python 3**, wired downstream of the one above — `NAME` off
`gh_brep2mpr` is exactly what it wants:

| | Name | Type | Access | |
| --- | --- | --- | --- | --- |
| input | `NAME` | str | **Tree** | one panel name per label |
| input | `QTY` | int | **Tree** | copies of each label — optional |
| output | `ZPL` | — | | the whole file, one string, line endings embedded |
| output | `LABEL` | — | | the same labels one by one, on `NAME`'s paths |
| output | `INFO` | — | | the report |

Each label is a complete `^XA … ^XZ` format: the name centred on top, the
Code 128 of the same name below it.

```
+--------------------------+
|      0_600x400-F_4       |
|                          |
|     || ||| | || |||      |
+--------------------------+
```

Nothing is encoded by hand — the barcode is `^BC` in auto mode, so the
subsets, the check digit and the quiet zones are the printer's business. What
the component does is lay the label out, keep the data printable, and size the
bars to the stock. `QTY` becomes `^PQ`, which the printer repeats itself, so a
piece needing four labels is four labels and one format.

It writes **no file**. Save `ZPL` as a `.zpl` downstream — a ShapeDiver
export component online, a writer of your own on the desktop — as UTF-8
(`^CI28` in every label says so) with its CRLF line endings kept. Nothing is
imported beyond Grasshopper's own data tree types.

### Stock and dots

Everything is in millimetres in a settings block at the top of the file, and
turned into printer dots against `DPI`. The defaults are a 203 dpi printer on
70 × 40 mm stock:

```python
DPI = 203                   # 203, 300 or 600
LABEL_W_MM = 70.0
LABEL_H_MM = 40.0
MARGIN_MM = 3.0
TITLE_MM = 4.0              # cap height of the name
TITLE_LINES = 2             # how many lines a long name may wrap over
BAR_H_MM = 15.0
HUMAN_READABLE = False      # the printer's own line under the bars as well
MODULE_MAX, MODULE_MIN = 4, 2
```

Set `DPI` to what the printer actually is. A file written for 203 dpi sent to
a 300 dpi printer comes out two thirds the size, and nothing anywhere reports
it — the dots are simply smaller.

The bars are drawn with the widest module from `MODULE_MAX` down to
`MODULE_MIN` that still fits between the margins, and centred on that width.
Below 2 dots at 203 dpi a handheld starts to miss, so the component will not
go thinner: a name too long to fit is still written out, and `INFO` says which
one and by how many dots it would be clipped. On the default stock that is
about 20 characters at the 2-dot module — roughly what
`<ID>_<length>x<width>-<F|B>_<qty>.mpr` comes to, which is why the default is
70 mm wide.

### What can be in a name

Code 128 carries printable ASCII. An accented letter — `Ușă` — has no barcode,
so the label is left out rather than printed wrong, and `INFO` names it and
the characters that did it. `^` and `~` are ZPL's own control characters and
`\` starts an escape of `^FB`'s; all three are written as hex under `^FH`
(`_5E`, `_7E`, `_5C`, and `_5F` for `_` itself) and come back off the scanner
as themselves.

The centred name field ends with `\&`, ZPL's line separator. `^FB` only
centres lines it has been told are finished, so without it a one-line name
sits at the left margin — which is what a ZPL validator means by *"field
block is centered but does not end with a line separator"*.

The same name twice is printed twice and reported: two pieces under one name
cannot be told apart at the stack. `QTY` is how one piece gets several labels.

### Sending it

The file is plain ZPL. It goes to the printer as bytes — no driver, no page
setup:

```bash
copy /b labels.zpl \server\zebra
```

```bash
lpr -S 192.168.1.50 -P raw labels.zpl
```

To see a label before there is a printer, paste `ZPL` into a ZPL viewer
(labelary.com renders it and reports what is wrong with it).

## ShapeDiver

Both components are written to pass ShapeDiver's script review
([forbidden Grasshopper functionalities](https://help.shapediver.com/doc/forbidden-grasshopper-functionalities)):
a definition there may not read from or write to the Rhino document, and may
not read or save local files.

* **Nothing reads the Rhino document.** `gh_brep2mpr.py` used to take its
  tolerance and units from `RhinoDoc.ActiveDoc`; it now has `TOL = 0.001` as
  a setting and assumes millimetres.
* **Nothing touches the file system.** Both components return text only —
  `MPR` and `NAME`, `ZPL` — and the files are made downstream: on ShapeDiver
  by its export components, on the desktop by whatever writer you put there.
* No sliders or other inputs are changed, no solution is rescheduled, and the
  only imports are `math`, `Rhino` (for the Brep geometry) and Grasshopper's
  data tree types.

## Limits — read this before the first cut

* **The output has not been run on a machine.** It matches the MPR 4.x
  specification in `Docs/homag-mpr4x-format-us_compress.md` and the structure
  of the shop's existing programs, and `check_mpr.py` passes on all 82 of them
  as well as on everything this tool generates — but the first converted
  program should still be opened in woodWOP and dry-run before it cuts.
* **The two-setup split covers drilling and grooving.** Contour milling is
  off and, when switched on, not checked against the machine. Each program
  assumes the operator lays the piece the way `INFO` names — turned over
  about the long or the short axis, or end for end — and re-references it to
  the same zero corner.
* **The gripping zones are an estimate.** Their ranking is the shop's, but
  `GRIP_CORNER` and `GRIP_EDGE` are placeholders, and the "seen from the back"
  reading — right = X 0 — was confirmed on one piece. Check the first shaped
  part on the machine.
* Only cylindrical bores become drilling macros. Countersinks, chamfers,
  spherical and toroidal faces are reported as notes and skipped.
* Pockets modelled as solid cavities are **not** converted
  (`<112 Tasche>` is not generated). The Grasshopper component does read
  sawn grooves — see [Grooves](#grooves) — but `dxf2mpr.py` does not.
* Feed rates, spindle speeds and tool numbers are left at `STANDARD` /
  woodWOP defaults. `BohrVert` is written with `BM="LS"`, `S_="2"` — change
  with `--bm-vert` or edit in woodWOP. The Grasshopper component writes
  marks under 1 mm deep as `BM="CP"` (see [Center punch](#center-punch)) and
  through bores as `BM="LSL"` (see [Through bores](#through-bores));
  `dxf2mpr.py` does neither.
* Arc direction in contours follows the MPR parser constants documented in
  section 4 of the format spec (`DS`: 0 = counter clockwise short, 1 =
  clockwise short, 2/3 = the same over 180°). Verify the first contour part.
* Route B does not yet handle `V_Tasche`, `F_Tasche`, `H_Tasche`, `Uni_Bohr`,
  `U_Bohr`, sawing layers or clamp/suction-cup layers. Those layers are
  ignored and reported.

## The other route

If you would rather keep using woodWOP DXF-Import, export 2D geometry instead
of a solid and put it on the layer names in the table above — that is what
`Docs/Bpp50BasicENU.md` §3.3 describes. Either way, the layer naming is the
same, so the two routes stay interchangeable.
