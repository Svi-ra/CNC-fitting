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
| output | `MPR` | — | | one whole program per setup, line endings embedded |
| output | `NAME` | — | | the file name for each program |
| output | `INFO` | — | | one report per part |

`MPR` and `NAME` are parallel trees: item *i* of a branch is the program, item
*i* of the same branch in `NAME` is what to call it. The component runs with
only `B` wired; `ID` and `QTY` may be left off.

`ID` and `QTY` can each be wired either branch-for-branch with `B`, or as one
flat list in part order. With no `ID` the branch path is used, so a flat list
of parts gives `0`, `1`, `2` …

### What the machine can reach

The drilling head cannot do every hole in one clamping, so **one part may come
out as more than one program**. What it is fitted with lives in one dict near
the top of the file:

```python
MACHINE = {
    "vert_blind": (35.0, 20.0, 15.0, 10.0, 8.0, 5.0),   # dead-end, from above
    "vert_thru":  (7.0, 5.0),                           # right through
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

The one re-clamping the planner will use is a **flip about the X axis**: the
piece is turned face for back, which swaps the top and lower edges and brings
the underside up. Left and right carry the same bits, so no other rotation
buys anything.

Every bore is tried face up (`F`) and turned over (`B`):

* one that works only one way **forces** that setup;
* one that works either way — a through bore, anything in the left or right
  edge — rides along with the first setup already needed, so a part that fits
  in one clamping stays **one** file;
* one that works neither way is named in `INFO` and left out of the program.
  Set `STRICT = False` to have it written anyway; it is still reported.

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

When a part needs two setups *and* has a contour, the outline is cut in the
first program only — repeating it would cut air — and `INFO` says so, because
a piece cut free in the first setup may no longer be held for the second.

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
This is checked against `Examples/WoodWop_export/0_472x420-F_1.mpr`, a
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
when neither does is a contour emitted at all.

### Identical panels

**Solids of the same shape are converted once.** A nested sheet where the same
panel appears twenty times gives one program, not twenty, and the quantities
add up: the file comes out named for the total. The copies are recognised
before anything is planned, so a duplicate costs a bounding box and a walk
over its vertices rather than a full conversion.

Two solids count as the same shape when their vertices, and the radius and
axis of every cylindrical face, measure the same from the corner of their own
bounding boxes, within `DUP_TOL`. Position is therefore irrelevant — copies
laid out across a sheet still fold together. **Orientation is deliberately
not normalised:** a copy turned end for end carries its holes at the other end
and is a genuinely different program, so it stays separate.

```python
MERGE_IDENTICAL = True  # off converts every solid separately, as before
DUP_TOL = 0.01          # two solids count as the same shape within this, mm
```

The first solid of a group is the one converted, and its `ID` names the
programs. `MPR` and `NAME` carry nothing for the copies; `INFO` gives each of
them a line saying which program covers it, and the surviving report names the
copies folded in — including a note if they did not all carry the same `ID`.

### File names

```
<ID>_<length>x<width>-<F|B>_<quantity>.mpr        ND0142_800x400-F_4.mpr
```

`F` = face up, as modelled. `B` = turned over. The quantity is the sum of
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
drillings classified by which face they break out through, and the top face
outline becomes a contour when it is not simply the bounding rectangle.

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

Which face ends up on top is **not** a setting: it is decided per part by the
planner above, because it is a machining choice rather than a property of the
model. The rest of the block is `SNAP`, `MAX_DIA`, `BM_VERT`, `THICKNESS`,
`CONTOUR`, `GROOVE`, `GROOVE_MAX_WIDTH` and `EOL`.

It outputs **text, not files**. When you write it out, use CRLF —
`open(path, "w", encoding="cp1252", newline="\r\n")` — for the reason above.
Put a boolean `Run` gate in front of any file writing, or a solve on every
slider drag will write the whole batch.

The component assumes the Rhino document is in millimetres and puts a warning
in `INFO` if it is not.

## Limits — read this before the first cut

* **The output has not been run on a machine.** It matches the MPR 4.x
  specification in `Docs/homag-mpr4x-format-us_compress.md` and the structure
  of the shop's existing programs, and `check_mpr.py` passes on all 82 of them
  as well as on everything this tool generates — but the first converted
  program should still be opened in woodWOP and dry-run before it cuts.
* **The two-setup split covers drilling and grooving.** Contour milling is
  not checked against the machine, and the `B` program assumes the operator
  turns the piece over about its long axis and re-references it to the same
  zero corner.
* Only cylindrical bores become drilling macros. Countersinks, chamfers,
  spherical and toroidal faces are reported as notes and skipped.
* Pockets modelled as solid cavities are **not** converted
  (`<112 Tasche>` is not generated). The Grasshopper component does read
  sawn grooves — see [Grooves](#grooves) — but `dxf2mpr.py` does not.
* Feed rates, spindle speeds and tool numbers are left at `STANDARD` /
  woodWOP defaults. `BohrVert` is written with `BM="LS"`, `S_="2"` — change
  with `--bm-vert` or edit in woodWOP.
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
