# Changelog

All notable changes to this project are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and
refer to the tooling in `Tools/`; the reference material in `Docs/` and
`Examples/` is inventoried in [MANIFEST.md](MANIFEST.md).

Repository: https://github.com/Svi-ra/CNC-fitting

## [0.17.0] — 2026-10-16

Two more ways to write the cut list's `.xlsx`: one workbook with a single
cell per edge, and a workbook per material.

### Added

- **`gh_json2xlsx_short.py`**, a Grasshopper component with the inputs and
  outputs of `gh_json2xlsx.py`. It writes the same sheet without each edge's
  second and third cells (*Обозначение*, *Толщина*): `Nr. | Lungime |
  Latime | cant. | L-1 | L-2 | W-1 | W-2 | COMENTARII`, columns `A:I`. The
  band row, outlines and merges move with the columns. A sheet that isn't
  the 17-column `A:Q` layout gives no parts and an error.
- **`gh_json2xlsx_split.py`**, a Grasshopper component that writes one
  workbook per block of the JSON. Each has the title row and then that
  material's block moved up to row 3, full `A:Q` layout. `PATH`, `TEXT` and
  `NAME` come as a branch per workbook, `{0}` `{1}` …, in block order.
  `NAME` is `PROJECT - MATERIAL`, and a repeated name gets ` (2)`, ` (3)`.
  `INFO` gives a line per workbook.
- Both carry `gh_json2xlsx.py`'s `.xlsx` code unchanged, so each one runs on
  its own in a Script component. A fix to that code has to be copied into
  all three.

### Tested

- Outside Grasshopper with its types stubbed, on
  `Examples/CutList/sample_cutlist.json`. Every cell kept was compared with
  the full workbook from `gh_json2xlsx.py` for value, bold, fill, alignment
  and all four borders. The three per-material workbooks match their rows
  exactly. The short workbook matches too, except column `H`, which now
  closes the edges' outline and takes the medium right line `P` had.
- All four workbooks opened in Excel and each printed on one landscape
  page. Not yet run on ShapeDiver, and it isn't known whether its archive
  download takes a tree of several workbooks.

## [0.16.0] — 2026-10-16

The cut list reaches Excel without the macro: `Tools/gh_json2xlsx.py` turns
the JSON into the parts of an `.xlsx`, for ShapeDiver's archive download to
zip into a workbook that opens ready to print. Categories that share a
material now share a block.

### Added

- **`gh_json2xlsx.py`**, a Grasshopper component wired after
  `gh_cutlist2json.py`. `JSON` in; out `PATH` and `TEXT`, the six files an
  `.xlsx` is made of (`[Content_Types].xml`, `_rels/.rels`,
  `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, `xl/styles.xml`,
  `xl/worksheets/sheet1.xml`) as paths and texts side by side, and `NAME`,
  the archive's name without extension. Zipped at the root of the archive and
  named `.xlsx`, they open in Excel as the sheet `CutListImport.bas` builds:
  values, text kept as text, widths and taller rows, fills, fonts,
  alignment, thin rules and medium outlines, merges, landscape A4 one page
  wide. A JSON that is not `gh_cutlist2json`'s, or a newer version, gives no
  parts and an error.
- `Examples/CutList/sample_cutlist.xml`, a short hand-written Excel 2003 XML
  Spreadsheet of the cut list layout.

### Changed

- **Categories that print the same material share one block** in the cut
  list sheet, where the first of them stands on `CAT`, lines in program
  order; `INFO` names the categories it joined. A category missing from
  `CAT`, or one with an empty material name, keeps a block of its own.
- **JSON:** each entry of `sections` carries `categories`, a list, in place
  of `category`. The `sheet` half, the one `CutListImport.bas` reads, is
  unchanged, and so is `version`. `Examples/CutList/sample_cutlist.json`
  updated to match.

### Tested

- Outside Grasshopper with its types stubbed: merging for shared, distinct
  and empty material names and for a stray category named like a material;
  the sample's sheet regenerated identical.
- The `.xlsx` for a 15-line cut list opened in Excel and compared cell by
  cell with the workbook the macro built from the same data: 473 of 475
  checks match — the two left are empty rows above a block, 15 pt where
  Excel makes them 15.75 after the macro. Names with `& < > "`, Romanian
  and Cyrillic letters, `1/2` and a text ID `106F` come through as text,
  `582,5` as the number 582.5. Archives with the parts in a folder, without
  `[Content_Types].xml`, or with one text repeated under all six paths are
  refused by Excel — the last is what a joined `TEXT` list gives, and the
  component's notes say so. Ran on ShapeDiver with the parts still on
  `gh_cutlist2json.py`; not yet run there as its own component.

## [0.15.0] — 2026-10-16

Banding materials: `Tools/gh_brep2mpr.py` names what each banded edge is
banded with, and the Excel cut list carries it. Programs are numbered from 1.

### Added

- **`BANDTYPE` and `BAND_MAP`** on `gh_brep2mpr.py`, both optional.
  `BANDTYPE` is one code per side per part (`1221`, `0111` …), in `BAND`'s
  order — bottom, left, top, right of the plane; `BAND_MAP` names what each
  one-character code stands for (`ABS 22/0.5=0`, `ABS 22/1=1` …, split at the
  last `=`). Only the sides `BAND` bands are read, so `0` is a material code
  like any other; `BAND` alone still says where the banding is.
- Each material is hung on the same world side as its mark and goes through
  the same turns, so it names the edge the mark is on in every setup. `INFO`
  adds it to the marks — `banding marked on the lower edge (ABS 22/1)` — and
  a note per part says which side got which material.
- `TABLE` has four more columns, `L-1;L-2;W-1;W-2`: the materials of the two
  edges along `Lungime` and the two along `Latime`, as the first program
  lies. The first six columns are where they were.
- `gh_cutlist2json.py` reads those columns and fills each edge's three cells
  as the cutting software's Excel import reads them (columns 5–16): *Наим.*
  and *Обозначение* the material, *Толщина* the number after its last `/`
  (`ABS 22/0.5` → 0.5). The JSON's `edges` hold the same three values.
- Setting `FIRST_ID = 1`, where the program count starts.

### Changed

- **Programs are numbered from 1, not 0.** File names and the cut list's
  `ID` start at `1_…`; a project converted before this comes out one number
  higher. IDs wired on `ID` are unchanged.
- **The cut list's `ID` is always the file name's.** With IDs wired on `ID`
  it used to carry the running number instead.
- **`Nr.` in the Excel sheet is the program `ID`** rather than a count of
  the block's rows, so a row leads straight to its `.mpr`. Lines of one
  program share it, a text ID stays text, and a line with no ID gets an empty
  `Nr.`.
- Two solids of one shape banded with different materials are now two pieces,
  as with `MAT`; `INFO` says so when it keeps them apart.
- `Examples/CutList/sample_cutlist.json` regenerated: IDs from 1, banding on
  six lines.

### Unchanged

- With or without `BANDTYPE`, the marks, setups, macros and `.mpr` text are
  the same. Unreadable banding codes — a code not on `BAND_MAP`, a type that
  is not four codes, a banded part with no type — leave those materials out
  with a `WARNING` and still write the marks.

### Tested

- Both components with Grasshopper stubbed: `BAND_MAP` parsing and its
  warnings, `BANDTYPE` read against `BAND` (codes under a 0 ignored, unmapped
  and lost-zero codes reported), each material landing on the same edge as
  its mark for every subset of sides in all eight placements, the `.mpr`
  byte-identical with and without materials, the cut list cells, thickness
  read from `22/0.5` and `2/0,8 mm` and left empty for a name without one,
  old six-column cut lists, programs numbered from 1, wired IDs reaching the
  cut list, and `Nr.` across blocks. Not yet run in Rhino or through the
  cutting software's import.

## [0.14.0] — 2026-10-16

The cut list goes to Excel: `Tools/gh_cutlist2json.py` lays it out as the
shop's Excel cut lists are, and `Tools/CutListImport.bas` builds the sheet.

### Added

- **`gh_cutlist2json.py`**, a Grasshopper component. `TABLE` from
  `gh_brep2mpr.py` (or the CSV as text), `CAT` and `MATERIAL` — the exact
  material name for each category — and `PROJECT` in; one JSON out, no file
  written. The layout follows *1. Mobilier birou copii str. Victoriei 8.xlsx*:
  the project name across A:Q, then a block per material in `CAT`'s order,
  two empty rows apart — `Material: <name>` and `COMENTARII`, the header row
  `Nr. | Lungime (L) | Latime (W) | cant. | L-1 | L-2 | W-1 | W-2` (three cells
  per edge), then one row per cut list line with the sizes and quantity
  unchanged and the panel name as its comment. The program `ID` is kept in
  the data. The JSON carries the data by material (`sections`, readable by
  Power Query) and the same rows placed on the grid with their styles,
  outlines, merges, widths and page setup (`sheet`).
- **The component refuses Item access.** On Item access Grasshopper runs a
  script once per item, which turned a 15-line cut list into 15 one-line
  JSON documents that did not import. If `TABLE`, `CAT` or `MATERIAL` is on
  Item access the component now turns red, names which, and gives no JSON.
- **`CutListImport.bas`**, an Excel VBA module: `ImportCutList` builds the
  sheet in a new workbook, `ImportCutListHere` on a new sheet of the open
  one. Text stays text, UTF-8 is read as UTF-8, and a file that is not a cut
  list — or holds several, one after another — is turned away with the
  reason. Its own JSON reader; Windows Excel only.
- `Examples/CutList/sample_cutlist.json`, a small cut list to try the importer
  on.

### Known limits

- The edge columns `L-1` … `W-2` stay empty: the cut list carries no banding
  (filled since 0.15.0).
- Where the reference workbook is uneven — the fill of its first material row
  stopping at column J, a few stray medium lines — the generated sheet keeps
  one even pattern instead.

### Tested

- The component with Grasshopper stubbed, on a sample cut list and on the
  15 lines of the Comoda test: blocks, numbering, warnings for unnamed and
  unused categories, unreadable lines, a reordered header, a byte order mark,
  and the Item-access error on each of the three inputs.
- The JSON rebuilt into an `.xlsx` with openpyxl and compared cell by cell
  with the reference: the borders drawn, fills and alignment agree except
  where the reference itself is uneven.
- The importer's JSON reader, carried over to VBScript and run under
  `cscript` against Python's reading of the same files — escapes, surrogate
  pairs, exponents, diacritics, and four broken files, each refused at the
  right character. The import itself was run in Excel by the user, on the
  regenerated Comoda cut list.

## [0.13.0] — 2026-10-16

`Tools/gh_brep2mpr.py` names setups from the operator's side, drills marks
the way the machine's woodWOP can, and carries each panel's name into the
cut list.

### Changed

- **The `-F` / `-B` in a file name are swapped: they now name the side the
  operator sees.** The head works the face that is up, so the operator faces
  the other one: a piece face up as modelled is now `-B`, one turned over is
  `-F`. Only the letters move — placement, the setups chosen and their order
  are unchanged. `INFO` uses the same letters. **A part converted before
  this comes out under the other letter**; programs already written keep
  their old names.
- **Center punch is off.** The woodWOP on the machine predates
  `BM="CP"`, so `PUNCH_DEPTH` is now `0` and a mark under 1 mm deep is
  drilled like any dead-end bore, `BM="LS"` — *slow-fast to depth* — to its
  modelled depth. `BM_PUNCH` stays; set `PUNCH_DEPTH = 1.0` again once the
  machine runs woodWOP 9.
- `TABLE` has a sixth column, `Denumire`:
  `Material;ID;Lungime;Latime;Cantitate;Denumire`. The first five are where
  they were.

### Added

- **`PNAME`, the panel name per part** — a plain list like `DIR` and `MAT`,
  optional, written to `Denumire` as given (a `;` or line break becomes a
  space). The name is not part of the identical-panel test, so copies of one
  shape still share a program; where they carry different names, the program
  gets a cut list line per name, each with that name's quantity and the same
  `ID`, and the lines of one `ID` add up to the total in the file name.
  `INFO` lists a program's names and names each folded-in copy. A `PNAME`
  list of the wrong length is reported as `DIR` and `MAT` are.

### Removed

- From `Tools/README.md`, the note about 80 mm banding marks on small panels,
  left over from before 0.12.2.

## [0.12.2] — 2026-10-15

`Tools/gh_brep2mpr.py` draws the banding marks as woodWOP draws them.

### Changed

- **A banded edge is now a blue line just outside it.** Each mark is
  `_hline1.ply`, 10 mm thick (`WIDTH="10"`), 10 mm outside its edge and the
  edge's full length, in place of the 80 mm `_s0.ply` square near it. The
  layout is copied field for field from a woodWOP 9.0.152 save,
  `Examples/Banding/0_330x163-B_1_banding-correct.mpr`: the line is carried
  in the comment (`LOCAL="1"`, `STARTLOCAL … ENDLOCAL`), so woodWOP needs no
  polygon file; `BR` is twice the edge and `HE` is `0`; the positions are
  plain numbers, the far ones written as a sum (`330+10`); each comment is
  named `Banding lower`, `left`, `upper` or `right`; and the block and its
  comments carry woodWOP's `AX`…`KO` fields, `ORI` numbering on from the
  macros and a separator line after each. Marks are written lower, left,
  upper, right. The upper edge is not in any example and is the lower one
  mirrored.
- Settings: `BAND_SIZE` is gone; `BAND_WIDTH = 10.0`, `BAND_GAP = 10.0` and
  `BAND_LOCAL` are new, and `BAND_MARKS` holds each edge's `MNM`, corner,
  run and angle.

### Removed

- The `INFO` note that a mark reaches past the middle of a small panel — a
  line along the edge cannot.

### Added

- `Examples/Banding/0_330x163-B_1_banding-correct.mpr`, the reference; the
  same part as written before the fix, `…-wrong.mpr`; and
  `6_290x114-F_1_banding.mpr`, an earlier layout with the lines inside the
  panel.

## [0.12.1] — 2026-10-15

`Tools/gh_brep2mpr.py` reads `BAND` patterns in the shop's order.

### Fixed

- **Banding patterns are read bottom, left, top, right.** On the part's
  plane seen down its Z axis (X right, Y away), clockwise from the bottom:
  character 1 is the bottom side (lowest Y), 2 the left (lowest X), 3 the
  top, 4 the right. 0.12.0 read them left, top, right, bottom, so every
  pattern marked the wrong edges — `1000` the left side instead of the
  bottom. `BAND_SIDES` now holds the new order; the directions of the sides
  and everything after them are unchanged. **Patterns written for 0.12.0
  need re-entering** — all of them but `0000` and `1111`.

## [0.12.0] — 2026-10-15

`Tools/gh_brep2mpr.py` marks the banded edges of each piece on its programs,
for the operator, and turns the marks with the piece.

### Added

- **Edge banding marks.** Two new inputs, both plain lists with one item per
  part: `BAND`, a pattern such as `0011` (text, so leading zeros survive),
  and `PLN`, the part's own plane. The pattern is read on the plane from its
  lower-left corner, clockwise looking down its Z axis: left (along the
  plane's Y), top, right, bottom (along its X). `BAND_SIDES` holds that order.
  Only the plane's axes are read — its origin may be anywhere, so a panel cut
  after its plane was set still reads correctly.
- Each banded edge is written as `<152 \Grafischer Kommentar\` (`_s0.ply`,
  80 × 80, blue) inside one `<121 \Block\` named
  `Graphischer Kommentar Kante`, at the positions and in the layout of the
  shop's own programs: `_BSX/2-40`/`10`, `_BSX/2-40`/`_BSY-60`,
  `10`/`_BSY/2-40`, `_BSX-90`/`_BSY/2-40`, `DP` counting the marks, no
  separator lines inside the block. New settings `BAND_SIDES`,
  `BAND_ANGLE_TOL = 1.0`, `BAND_MARKS`, `BAND_PLY`, `BAND_SIZE`,
  `BAND_BLOCK`.
- `Examples/Banding/` — three of those shop programs, the reference for the
  block.
- `INFO` names the banded edges of every setup, and how the pattern was
  read.

### Changed

- **The marks follow the piece through every setup.** A banded side is
  carried through the same quarter turn and the same setup map as the bores,
  so on a two-setup piece each program marks the edge that is banded in that
  placement. The marks are added after the setups are planned and are not
  among the macros: placement, setups, macros and file names are the same as
  with `BAND` unwired.
- **Banding is part of what makes two pieces the same.** Copies of one shape
  banded on different sides of the solid stay separate programs, and `INFO`
  says that the banding kept them apart. The comparison is by side of the
  solid, not by pattern text, so `1010` read against two planes turned 180°
  apart is the same piece.
- `place()` also returns whether it gave the part the quarter turn, and
  `brep_to_setups()` takes the banded sides and the part's notes.

### Refused rather than guessed

- No marks, and a `WARNING` in `INFO`, for a pattern that is not four 0s and
  1s (`11` — a pattern wired as a number — gets a note that its leading zeros
  were lost), for banding with no plane, and for a plane more than
  `BAND_ANGLE_TOL` out of the panel or off square with its sides.
- A note when a mark reaches past the middle of a panel narrower than about
  180 mm, where it may read as the opposite edge's.
- A `BAND` or `PLN` list of the wrong length is reported, as `DIR` and `MAT`
  are.

### Verification

- Not yet run. The component parses; a Rhino test over 192 generated
  panels, with a marker bore beside each banded side, was stopped before it
  reported, and the user is testing by hand. The first banded programs —
  including one that splits into `F` and `B` — should be opened in woodWOP
  and checked against the model.
- `_s0.ply` is not in the repository, so the look of a mark and the top
  edge's `_BSY-60`, copied as found, are unconfirmed.

## [0.11.0] — 2026-10-12

`Tools/gh_brep2mpr.py` folds identical solids together reliably, and says
why when two pieces of the same size stay apart.

### Fixed

- **Identical solids came out as separate programs.** Five copies of the
  323 × 78 bent-facade piece (`pieces.3dm`) gave `0_…_1` and `1_…_4` —
  byte-identical programs under two numbers. `geometry_key` rounded every
  measurement to a `DUP_TOL` grid and compared the cells. The flat bottom of
  each Ø4.5 side bore reports a bounding box 2.295 mm off the axis, so its
  edge sits at Z = 6.705 — exactly half way between two cells on a 0.01 grid
  — and one copy read 6.705000000000004 and fell into the next one. The
  2.295 is 2.25 × 1.02, so every bore with a radius on a quarter millimetre
  lands on a half step: this was systematic, not bad luck.

### Changed

- **Shapes are compared within `DUP_TOL`, as documented.** `geometry_key`
  keeps raw measurements, and only the vertex count and the count of each
  kind of face are compared exactly, to pick the candidates. The new
  `shape_mismatch` pairs every vertex and face with its closest unused
  counterpart — a bore's axis either way round — and each value may differ
  by up to `DUP_TOL`. The pairing searches a sorted window, so 40 copies of
  the test piece group in 0.1 s.

### Added

- `INFO` line for a piece that is the same size as an earlier one but still
  gets a program of its own: `same size as 0 but not folded into it:`
  followed by the material, the grain, the vertex and face counts, or the
  one measurement that is out, with both values and the gap.

### Verification

Run in Rhino 8 through RhinoCode, with the component file executed unchanged
on Breps imported into a headless document:

- `pieces.3dm` (the five copies from the report): one program ×5 — before,
  ×4 and ×1, matching the files produced in the field. `Pieces.dxf`: ×5.
- A copy moved 1.2 m across the model and one stretched 0.003 mm fold in; a
  copy stretched 0.03 mm and one mirrored end for end do not, the mirrored
  one with a note naming the vertex that has no match.
- The same solid in another material, or along the grain instead of across,
  stays apart with a note saying so; the 3dm piece against its DXF
  round-trip (22 faces against 31) is reported by its face counts.

## [0.10.0] — 2026-10-09

`Tools/gh_brep2mpr.py` places each piece so the machine can hold it, drills
through bores slow-fast-slow, and stops writing contour milling the machine
cannot do.

### Added

- **Placement for the gripper.** The machine grips the piece by its edges and
  corners, ranked in `GRIP_ZONES` as seen from the piece's back: lower-right
  corner, right edge, upper-right corner, lower edge, lower-left corner,
  upper-left corner, left edge, upper edge — right being X = 0 in the
  program. Each zone is measured on the solid with `Brep.IsPointInside`, as
  the share of it where the panel is there through its whole thickness, so
  cut corners, rebates and pockets from either face all count; drilled bores
  do not. The shares are weighted 128, 64 … down the ranking. New settings
  `GRIP`, `GRIP_ZONES`, `GRIP_CORNER = 100`, `GRIP_EDGE = 40`,
  `GRIP_GRID = 4`, `GRIP_CHECK = 3`, `GRIP_WARN = 0.9`. An open Brep is
  placed by tool access alone, with a note.
- **Turned end for end.** Besides face up (`F`) and turned over about X
  (`B`), each setup may be turned 180° in its own plane — so `B` may also be
  turned over about the short axis. Every bore and groove is tried all four
  ways. A piece with only Ø4.5 holes in its top edge now needs one setup, not
  two.
- **Through bores** are written `BM="LSL"`, woodWOP's *Slow-fast-slow
  through*, with no `TI`, as woodWOP saves them. New setting
  `BM_THRU = "LSL"`; `BM_VERT` is for dead-end bores.
- `INFO` names each setup's placement, how the piece is turned between the
  two, why a second setup was taken for the grip, and any of the first three
  zones under 90 % solid.

### Changed

- **The plan is chosen by reach, then grip, then setup count.** Holding the
  piece outranks the number of setups: the 323 × 78 test piece with an R78
  corner, all reachable face up in one clamping, now comes out as `B` turned
  over about its short axis for the edge bores, then `F` turned end for end
  for the Ø15 — the radius at the upper-left, then the lower-left, instead of
  across the right edge.
- **Of two setups, the better-held one goes first** — it can now be `B`.
  Ties still fall to face up, as modelled.
- **`CONTOUR` is off by default.** A shaped outline is no longer written as
  `]1` + `<105 \Konturfraesen\`: the machine has no router, and woodWOP
  flagged the block (`TNO=""`) as an error. `INFO` now says the piece must
  arrive cut to shape. `CONTOUR = True` restores the old output exactly.
- `place()` also returns the map back to world coordinates, and
  `setup_maps()` takes a `turned` flag. `SETUPS` is replaced by `ORIENTS` and
  `PLANS`.

### Verification

- Offline, with Rhino stubbed and point-in-solid answered by synthetic
  pieces: 12 placement cases — plain panel, a cut corner at each end, a
  rebate, an edge pocket, a blind bore, Ø4.5 in the top edge, the old
  two-setup case (still `F` then `B`), the same with a cut corner, an open
  Brep, a piece modelled along Y.
- The 323 × 78 piece rebuilt from `piece 323x78.dxf` and its MPR: the
  expected sequence above, all nine bores placed; `check_mpr.py` passes both
  programs, which hold boring blocks only.
- A dowel in the X 0 edge and a Ø35 cup hole at the X 0 / Y 0 corner leave a
  piece in one face-up setup.
- Not yet run in Grasshopper or on the machine.

## [0.9.0] — 2026-09-22

Both Grasshopper components pass ShapeDiver's review: neither reads the Rhino
document nor touches the file system.

### Removed

- **`gh_name2zpl.py` writes no file.** The `PATH` and `WRITE` inputs and the
  `FILE` output are gone, with the `os`/`io` code behind them — ShapeDiver
  forbids saving to a local path. `ZPL` is unchanged; save it downstream, as
  UTF-8 with its CRLF kept. Unwire the three parameters in existing
  definitions.
- **`gh_brep2mpr.py` no longer reads `RhinoDoc.ActiveDoc`.** The document's
  tolerance is replaced by a `TOL = 0.001` setting — the value it already
  fell back on — and the "document is not in millimetres" warning is gone
  with it. The model is taken to be in mm.

### Added

- A [ShapeDiver](Tools/README.md#shapediver) section in `Tools/README.md`.

### Verification

- No `RhinoDoc`, `open(`, `os` or `io` left in any `gh_*.py`.
- `gh_name2zpl.py` with Grasshopper stubbed: two names give two whole
  `^XA … ^XZ` labels. `gh_brep2mpr.py`'s drilling and planner checks from
  0.8.0 give the same output.

## [0.8.0] — 2026-09-22

`Tools/gh_brep2mpr.py` punches shallow marks instead of drilling them, and no
longer joins marks on opposite faces into a through bore.

### Added

- **Center punch.** A vertical dead-end bore shallower than `PUNCH_DEPTH`
  (1 mm) is written as `<102 \BohrVert\` with `BM="CP"`, woodWOP's *Center
  punch* mode, which allows for the drill's pointed tip. `TI` stays the depth
  as modelled; deeper bores and through bores keep `BM_VERT`. New settings
  `BM_PUNCH = "CP"` and `PUNCH_DEPTH = 1.0`; `0` turns punching off.
- The vertical array's dead-end bits now include **7 mm**, the punching bit.
- `Examples/WoodWop_export/0_340x252-B_1_Center-punch-mode.mpr` — woodWOP
  9.0.152's own save of the mode, the source for `BM="CP"`; the spec does not
  list it.
- `Examples/CAD-models/320x234.dxf` — a panel with marks on both faces.

### Fixed

- **Marks on opposite faces came out as one through bore.** Cylinder faces
  were joined by axis and diameter alone, from the lowest end to the highest,
  so a 0.5 mm mark on each face at the same X/Y became one 18 mm bore. Faces
  are now joined only where their extents overlap or touch; the two marks
  stay two dead-end bores and the planner gives each its own setup.

### Changed

- `Examples/WoodWop_export/0_472x420-F_1.mpr` renamed
  `0_472x420-F_1_Standard-mode.mpr`, beside its Center-punch counterpart.

### Verification

- The drilling writer on its own: 0.5 mm deep → `BM="CP" TI="0.5"`, exactly
  1 mm → `LS`, 14 mm → `LS`, through → `LS TI="18"`.
- The 320 × 234 part: two marks face up and one on the underside at the same
  X/Y give `F` with two `CP` marks and `B` with the underside mark and the Ø8
  dowels — previously `F` held two `TI="18"` through bores. Confirmed in
  Grasshopper.

## [0.7.0] — 2026-09-09

`Tools/gh_name2zpl.py`, a new Grasshopper component: the panel names become
Code 128 labels and one ZPL file that goes straight to the printer.

### Added

- **`gh_name2zpl.py`.** `NAME` in — the same tree `gh_brep2mpr.py` hands out —
  and `ZPL` out, one string holding a complete `^XA … ^XZ` format per label,
  line endings embedded. `LABEL` is the same labels one by one on `NAME`'s
  paths, for printing only some of them; `PATH` and `WRITE` write the file,
  the same boolean gate the other components use. Standard library only, and
  only `io` and `os`, and only when a file is written.
- **The barcode is the printer's.** `^BC` in auto mode, so subsets, check
  digit and quiet zones are its business and nothing is encoded here by hand.
  The component lays the label out: the name centred on top over the Code 128
  of the same name, everything in millimetres in a settings block and turned
  into dots against `DPI`.
- **The bars are sized to the stock.** The widest module from `MODULE_MAX`
  down to `MODULE_MIN` that fits between the margins, centred on that width.
  It will not go below 2 dots, where a handheld starts to miss: a name too
  long is still written out and `INFO` says by how many dots it would be
  clipped, which on the default 70 × 40 mm stock is about 20 characters —
  roughly what `<ID>_<length>x<width>-<F|B>_<qty>.mpr` comes to.
- **`QTY` becomes `^PQ`**, so a piece needing four labels is four labels and
  one format, repeated by the printer itself.
- **What a name may hold.** Code 128 carries printable ASCII, so a name with
  an accented letter gets no label rather than a wrong one, and `INFO` names
  the characters that did it. `^`, `~` and `\` are ZPL's own controls and are
  written as hex under `^FH`, `_` with them, so they come back off the scanner
  as themselves. The same name twice is printed twice and reported: two pieces
  under one name cannot be told apart at the stack.
- The centred name field ends with `\&`. `^FB` centres only lines it has been
  told are finished, so without the separator a one-line name sits at the left
  margin instead — which is what a ZPL validator reports as *"field block is
  centered but does not end with a line separator"*.

## [0.6.0] — 2026-09-08

`Tools/gh_brep2mpr.py` takes the material and the grain direction beside the
geometry, and returns the cut list along with the programs.

### Added

- **Two per-part inputs, `DIR` and `MAT`.** Plain lists as long as the list of
  parts, read straight through in the order the parts arrive on `B` — unlike
  `ID` and `QTY` there is nothing to match up by branch. `DIR` is the grain
  direction (`True`: the first dimension runs along the grain; `False`: the
  piece is laid 90° across it), taken as a boolean, a number or `"true"` /
  `"false"` as text; `MAT` is free text carried through as given. Either may
  be left unwired — all along the grain, no material named — and a list of
  the wrong length is read as far as it goes and reported in `INFO`.
- **`TABLE`, the cut list**: a header line and then one line per piece,
  `Material;ID;Lungime;Latime;Cantitate`. `ID` is where the piece sits in the
  geometry input, counting from zero, so folded-in copies share the number of
  the first of them; `Lungime` is the dimension along the grain and
  `Cantitate` the same total the file name carries. A part the converter
  throws out still gets a line, sized from its bounding box.
- `column` / `at` read a per-part list, `as_bool` accepts the three shapes a
  Grasshopper boolean arrives in, `table_row` writes one cut-list line and
  `panel_size` sizes a part the planner refused.

### Changed

- **Material and grain join the identical-panel test.** The grouping key is
  now the shape fingerprint together with the material and the direction, so
  the very same solid cut from another board, or laid across the grain, is a
  piece of its own and gets a program of its own.
- `INFO` names the material, and says when a piece is turned across the grain
  and what the cut list therefore reads.
- `DIR` changes the cut list only, never the program — the machine has no
  notion of grain, so the two sizes swap on the sheet while every hole stays
  where the model put it.

## [0.5.0] — 2026-09-08

`Tools/gh_brep2mpr.py` converts a repeated panel once. A nested sheet where
the same part appears twenty times now gives one program named for the total
quantity, instead of twenty identical files that differ only in their `_1`.

### Added

- **Identical solids are folded together.** The whole input is read before
  anything is planned, solids of the same shape are grouped, and only the
  first of each group goes through the planner and the MPR writer. Their
  quantities are added up, so `file_name` writes the total and the existing
  `<ID>_<length>x<width>-<F|B>_<quantity>.mpr` convention carries it with no
  change of form.
- `geometry_key` — the shape fingerprint the grouping runs on: bounding-box
  size, every vertex, and every face with its type and, for a cylinder, its
  radius and axis. Everything is measured from the corner of the part's own
  bounding box and quantised to `DUP_TOL`, so where a solid sits in the model
  does not matter. It touches no part of the converter, so a duplicate costs
  a bounding box and a walk over the vertices rather than a conversion.
- `MERGE_IDENTICAL` (on) and `DUP_TOL` (0.01 mm) join the settings block.
  Off converts every solid separately, as before.
- The report names what was folded in: the surviving `INFO` entry lists the
  copies and says their quantities are in its own, and each copy's branch
  gets a line naming the program that covers it. Where the copies carried
  IDs of their own — the programs are named after the first — `INFO` says so.

### Notes

- **Orientation is deliberately not normalised.** A copy turned end for end
  has its holes at the other end and is a genuinely different program, so it
  is left alone. Only position is factored out.
- `MPR` and `NAME` stay parallel to each other, but a merged copy's branch
  now carries no program — that branch appears in `INFO` only.

### Verification

Not run in Grasshopper; the two new pieces were exercised against stub
geometry outside Rhino, and the file compiles.

- `geometry_key` matches a copy translated across the sheet, ignores the
  order Rhino hands the vertices back in, and separates two panels that
  differ only in one bore's radius or one vertex's position.
- The grouping pass sums quantities (2 + 3 + 1 into one x6), keeps the input
  order of the groups, and collapses to one group per solid with
  `MERGE_IDENTICAL = False`.
- Reading `ID` and `QTY` moved out of the per-part `try` when the loop was
  split in two, and is now guarded on its own, so a bad value still falls
  back to a default instead of stopping the component.

## [0.4.0] — 2026-09-07

`Tools/gh_brep2mpr.py` reads grooves off the solid and writes them as
`<109 \Nuten\`. What the macro actually has to look like was settled against a
woodWOP export of a part this repository also holds as a mesh, which is now
kept as the reference for it.

### Added

- **Groove detection.** A flat rectangular cavity floor lying between the two
  faces becomes a sawn groove. Its short dimension is the width, its long one
  the run, and its height gives the depth. Round-ended slots, pockets and
  free-form cavities are reported and left alone, as before.
- **The grooving saw** joins the machine model: `SAW_KERF` (4 mm blade),
  `SAW_ALONG` (`"X"` — the directions the unit can run), and
  `GROOVE_MAX_WIDTH`, above which a flat cavity is read as a pocket rather
  than a groove. A groove narrower than the blade, or running a direction the
  saw cannot, is reported and left out. `GROOVE` turns the whole thing off.
- Grooves go through the same setup planner as bores. `<109 Nuten>` saws from
  the top face and has no Z reference — MPR 4.x has no below-table sawing
  macro at all, only `<131 UfluBohr>`, `<151 UflurTasche>` and
  `<113 Unterflur-Fraesen>` — so a groove in the underside needs the piece
  turned over exactly as an underside bore does, and rides along with that
  setup when the drilling already calls for one.
- `Tools/check_mpr.py` checks the new macro: `XE`/`YE` inside the part, `TI`
  not sawing through it, `NB` a real width, start and end not the same point.
- `Examples/WoodWop_export/` and `Examples/Meshes/` — the woodWOP program and
  the 3D model of one part, the ground truth for everything below.

### Fixed

- **A groove was written down its middle.** woodWOP programs a groove by one
  of its **edges** and offsets the blade a full `NB` to one side with `RK`;
  the tool wrote the centre line with `RK="NoWRK"`, putting every groove half
  a blade-width out of position. The edge is now programmed and `RK` carries
  the offset, controlled by the new `GROOVE_RK`.
- **A groove that ran out to an edge was routed round.** Such a groove
  notches the face it was sawn into, so that face's outer loop is no longer
  the bounding rectangle and `outline` followed the notch — emitting a
  `<105 Konturfraesen>` that would have cut the panel to the shape of its own
  grooving. `outline` now considers both faces: if either still goes round
  the plain rectangle the part is a rectangle and there is nothing to rout,
  and if neither does, the less interrupted of the two is the outline.
- **The flat bottom of every blind bore was reported as an unconvertible
  cavity.** A loop made only of arcs is a drill bottom and is now passed over
  in silence.
- The obstacle a flip cannot fix is reported first. A groove running the
  wrong direction said it was an underside problem in the turned-over setup;
  the same applied to a bore whose diameter was wrong as well as its face.
  Failures that classify no feature at all now quote X only, which the flip
  leaves alone, so they are worded the same in both setups and reported once.

### Verification

Against `Examples/WoodWop_export/0_472x420-F_1.mpr`, a woodWOP 9.0.152
program, and `Examples/Meshes/472x420.gltf`, the same 472 × 420 × 18 part:

- The mesh decodes into the part frame with the two Ø15 bores at (438, 50)
  and (438, 351) pinning the mapping. Rebuilt as Brep-shaped input, all ten
  bores come out identical to the export — four `BohrHoriz` on `XM`
  including the 27.655 mm depth, six `BohrVert` from Ø5 to Ø15.
- The groove agrees on position, run and side: `XA="75" YA="410" XE="472"
  YE="410" RK="WRKR" EM="MOD0"`, against a modelled floor spanning Y 410…414
  at Z 9. It disagrees on section — the model has 4 mm × 9 deep where the
  woodWOP program says 8 × 7 — which is a difference between those two files,
  not something the converter decides.
- No contour is emitted, matching the export, and no notes about the bore
  bottoms.
- The file name comes out `0_472x420-F_1.mpr`, the export's own name.
- `check_mpr.py` still passes on all 82 production programs and on everything
  generated here. The one finding in `Examples/CAD-models/Noptiera-2.mpr`
  predates this work and is in a hand-built scratch file.

### Notes

- `<109 \Nuten\` is confirmed by the export. The spec is machine-translated
  and calls it `<109 \grooveen\` — "Nuten" with *Nut* → *groove*, the same
  artefact that turns `\Konturfraesen\` into `\Contourfraesen\`.
- The `RK="WRKR"` side convention is confirmed for a run towards **+X**, the
  only direction this saw runs. The +Y case, reachable by setting
  `SAW_ALONG = "XY"`, is derived by rotating that result and is unverified.

## [0.3.0] — 2026-09-07

`Tools/gh_brep2mpr.py` now writes programs the machine can actually run: what
the drilling head is fitted with is modelled explicitly, and a part whose holes
do not all fit in one clamping comes out as more than one program.

### Added

- **A machine model.** One `MACHINE` dict holds what the head carries: the
  vertical array's dead-end bits (35, 20, 15, 10, 8, 5 mm) and through bits
  (7, 5 mm), and the horizontal bits per side — Ø8 in the top edge (Y = `BR`),
  Ø4.5 in the lower edge (Y = 0), both in the left and right edges. A measured
  diameter counts as a listed one within `DIA_TOL` (0.2 mm).
- **Setup planning.** Every bore is tried face up (`F`) and turned over (`B`),
  a 180° flip about the X axis that swaps the top and lower edges and brings
  the underside up. A bore that works only one way forces that setup; one that
  works either way — a through bore, anything in the left or right edge —
  rides along with the first setup already needed, so a part that fits in one
  clamping stays one file. Left and right carry the same bits, so no other
  rotation buys anything and none is used.
  - A piece with Ø8 *and* Ø4.5 holes in its top edge now yields two programs:
    the Ø8 face up, the Ø4.5 written for the flipped piece where they sit in
    the lower edge. Turned back, every hole is where the model put it.
  - A bore reachable in neither setup is named in `INFO` and left out.
    `STRICT = False` writes it anyway, still reported.
  - The contour is cut in the first program only; when a part needs two
    setups and has one, `INFO` warns that a piece cut free in the first setup
    may no longer be held for the second.
- **`NAME` output** — `<ID>_<length>x<width>-<F|B>_<quantity>.mpr`, a tree
  parallel to `MPR`: item *i* of a branch names item *i* of the program tree.
  Duplicate names are caught and reported rather than silently overwriting.
  `EXT` sets the extension.
- **`ID` and `QTY` inputs**, both optional and both wireable either
  branch-for-branch with `B` or as one flat list in part order. With no `ID`
  the branch path is used. The component still runs with only `B` wired.
- Contour outlines are now forced counter-clockwise, so `RI="1"` keeps its
  meaning after a flip mirrors the outline.

### Removed

- **The `LINES` output.** `MPR` is again the only program output, one string
  per program with the line ending inside it (`EOL`, CRLF by default) — as
  asked. Set `EOL` to `\n` if the export path applies CRLF itself.
- **The `FLIP` setting** and the `<131 UfluBohr>` branch. Drilling from below
  is exactly what the setup planner now handles, and it is a machining
  decision per part rather than a global switch.

### Changed

- `emit_hole` is split into `feature` (what the bore is, in a given setup
  frame), `reachable` (can the head do it, and as which bit) and `macro`
  (what to write). The planner calls the first two per setup, so the same
  classification decides the split and the output.
- `place` no longer decides which face ends up on top; it does `LONG_X` and
  the shift onto the zero point only.
- `INFO` now reports per part rather than per program: size, quantity, how
  many files, what each setup drills, and the notes.

### Verification

- Five synthetic parts through the planner, with Rhino stubbed out: a mixed
  part needing both setups, one drilled entirely on its underside (single `B`
  file), one reachable face up in one go, one where nothing is reachable, and
  a plain blank. Coordinates in the `B` files check out by hand — the Ø15
  bottom bore at X=600 Y=100 z 0…4 lands at Y=300, `TI=4`, and the Ø4.5 top
  edge bore at Y=400 lands at `YA=0`, `BM="YP"`, `ZA` mirrored.
- Both programs of the mixed part written out and passed by `check_mpr.py`:
  64 and 42 CRLF, zero bare LF, `!` last.
- Contour winding: an L-shaped outline and its mirror both come out
  counter-clockwise; a plain rectangle still yields no contour.
- `ID`/`QTY` lookup by branch, by flat index, past the end of a branch, and
  with nothing wired.

## [0.2.2] — 2026-09-04

### Fixed

- **ShapeDiver ignored its CRLF setting when exporting the component's
  output.** `MPR` was one string per branch with LF newlines already inside
  it, so an exporter that applies a line ending while joining a *list* of
  lines had nothing to join and wrote the embedded LFs verbatim — producing
  exactly the empty-blank failure of 0.1.1, one layer further out.
  - `MPR` now carries the line ending itself, CRLF by default, set by the new
    `EOL` setting.
  - New `LINES` output: the same program as one line per item with no line
    endings attached, for exporters that join and apply their own ending.
    Use `LINES` with ShapeDiver and `MPR` with anything that writes verbatim;
    using `MPR` with a converting exporter yields CR CR LF, so `EOL` can be
    set to LF for that case.
  - `render_mpr` is now a thin join over the new `mpr_lines`, which is the
    single source of the program text.

### Notes

- The "double space between blocks" seen when copying the output is not in
  the data. Checked byte for byte: neither the generated programs nor the
  production files in `Examples/PAL_8681_SM_Alb_Diamant/` contain a double
  space anywhere. The block separator is a line holding one space, required
  by the format and present in every real woodWOP program — an export path
  that trims trailing whitespace will break the file.

### Verification

- `MPR` output for `Noptiera-1.dxf`'s features: 152 CRLF, zero bare LF, and
  byte-identical to `Examples/CAD-models/MPR/Noptiera-1.mpr`.
- `LINES` holds 153 items, none containing a line ending, and joining them
  with `EOL` reproduces `MPR` exactly.

## [0.2.1] — 2026-09-04

### Changed

- `Tools/gh_brep2mpr.py` now assumes parts already lie flat in the world XY
  plane, thickness along Z, and never rotates anything out of that plane.
  - Dropped the panel-plane detection: the largest-planar-face search, the
    longest-edge search for X, the plane construction and the remapping of
    every point and direction into plane coordinates. Sizes now come straight
    from the world bounding box, and `Rhino.Geometry` is no longer needed at
    all.
  - `ORIENT` is replaced by two independent settings, `LONG_X` (turn the long
    side onto X) and `FLIP` (turn the part over when all vertical drilling
    would come from underneath). Both are rotations about Z or about X by 180
    degrees, so the part stays flat either way.
  - A part that is not lying flat is now reported in `INFO` as a `WARNING`
    naming the offending direction and the resulting `DI`, instead of being
    silently rotated. Correcting it would contradict the layout the
    definition produced, and a wrong `DI` is otherwise easy to miss.

### Verification

- Still renders a program byte-identical to
  `Examples/CAD-models/MPR/Noptiera-1.mpr` from the features `dxf2mpr.py`
  recovers from `Noptiera-1.dxf`.
- New checks: a flat part with X shorter than Y keeps its thickness in Z and
  gets its long side turned onto X; a part fed in standing on edge raises the
  warning rather than being rotated. The earlier checks (turn-over, all four
  horizontal directions, filleted outline, plain rectangle, and the three
  guards) all still pass.

## [0.2.0] — 2026-09-04

### Added

- `Tools/gh_brep2mpr.py` — Grasshopper Script component (Rhino 8, Python 3).
  Takes a data tree of raw Breps, one part per branch, and returns one MPR
  program as text per branch plus a per-part report. Self-contained: paste it
  into a single Script component, nothing needs to be on the module path.
  - Recognises everything from the geometry alone, with no attached data:
    the largest planar face gives the panel plane, its longest straight edge
    gives X, and cylindrical faces become drillings classified by which face
    they break out through.
  - Uses `Surface.TryGetCylinder` and `Curve.TryGetArc` instead of the
    NURBS fitting in `dxf2mpr.py`, so roughly 600 lines of DXF reading and
    ACIS decoding are simply not needed — Rhino already holds the Brep.
  - Same orientation handling as the CLI: laid flat, long side along X,
    turned over when all vertical drilling would come from underneath.
  - Emits text, not files, so the writing step (and its CRLF requirement)
    stays under the definition's control.

### Verification

- Driven with the exact features `dxf2mpr.py` recovers from `Noptiera-1.dxf`,
  the component renders a program **byte-identical** to
  `Examples/CAD-models/MPR/Noptiera-1.mpr`.
- Separately exercised: turn-over of a part drilled only from below; all four
  horizontal drilling directions (`XP`/`XM`/`YP`/`YM`); a filleted outline
  producing a contour with the correct `DS`; a plain rectangle correctly
  producing no contour; and the guards for closed internal bores, bores over
  `MAX_DIA`, and slanted bores.
- The RhinoCommon calls themselves are **not** covered by these tests —
  they were stubbed out. Run the component on one known part and compare
  against the DXF route before trusting it on a batch.

## [0.1.1] — 2026-09-04

### Fixed

- **Generated programs opened in woodWOP as an empty 1500 × 120 × 19 blank
  with no machining.** The files were written with LF line endings; woodWOP
  splits an MPR on CRLF, so the whole program was read as one unparseable
  line and the editor fell back to its default blank without reporting an
  error. All MPR files in `Docs`-adjacent examples — production and
  woodWOP-authored alike — are CRLF. `dxf2mpr.py` now writes CRLF.
- `check_mpr.py` could not see the fault: it read files in text mode, where
  Python normalises line endings. It now reads bytes and rejects LF-only and
  mixed-ending files.

### Changed

- `!` is written immediately after the last block, with no separator line
  before it, as real woodWOP files do.
- Contour element coordinates (`X`, `Y`, `R` of `KP`/`KL`/`KA`) are written
  with four decimals, matching woodWOP's own formatting; `Z`, `KO` and `DS`
  stay plain integers.

### Verification

- `Examples/CAD-models/MPR/Noptiera-1.mpr` is now structurally identical to
  the production file `Examples/PAL_8681_SM_Alb_Diamant/15_1.MPR`: same CRLF
  encoding, same data-head lines, same `WerkStck` block, same `BohrVert`
  parameter names in the same order.
- All 12 regenerated programs pass `check_mpr.py`, which now includes the
  line-ending check.

## [0.1.0] — 2026-09-04

First working DXF → MPR path. Motivated by `Noptiera-1.dxf` refusing to load in
woodWOP DXF-Import.

### Diagnosis

- Established why the DXF exports cannot be imported: model space contains a
  single ACIS `3DSOLID` on layer `PancakeDefault` and **no** 2D drawing
  elements. woodWOP DXF-Import Basic works only on lines, arcs, circles,
  polylines and blocks sorted onto its own layer names
  (`Docs/Bpp50BasicENU.md` §1.2, §3.3), and has no ACIS interpreter. The layer
  name carries no meaning for the converter either. Same cause in
  `Noptiera-2.dxf` (1 solid) and `Test-noptiera.dxf` (9 solids).

### Added

- `Tools/dxf2mpr.py` — batch DXF → woodWOP MPR converter, Python 3.8+,
  standard library only.
  - Reads ACIS solids in both encodings: obfuscated ASCII **SAT** (DXF up to
    AC1024) and binary **SAB/ASM** carried in the `ACDSDATA` section
    (DXF AC1027+), matched to its `3DSOLID` by entity handle.
  - Rebuilds the B-rep (body → lump → shell → face → loop → coedge → edge)
    and recovers cylinders from `cone-surface`, from NURBS `spline-surface`
    patches, and — where the surface is only a back-reference — from the
    circular edges bounding the face.
  - Emits `<100 WerkStck>`, `<102 BohrVert>`, `<131 UfluBohr>`,
    `<103 BohrHoriz>`, `<104 BohrUniv>`, and contour `]n` +
    `<105 Konturfraesen>` for outlines that are not the bounding rectangle.
  - One MPR per ACIS body, so an assembly DXF splits into `<name>_1.mpr` …
    `<name>_n.mpr`.
  - Automatic orientation for parts modelled in assembly position: thinnest
    direction rotated to Z, long side to X, part turned over when all vertical
    drilling would otherwise come from underneath, then moved to the zero
    point. Every move is reported and logged.
  - Second input route for flat DXF on woodWOP layer names
    (`Werkstk_<t>`, `ProcPart_<t>`, `V_Bohr<m>[_<d>]`, `V_Drill…`,
    `H_Bohr_<z>`, `H_Drill_<z>`, `V_Fraes_<z>T<n>`, `V_Trim…`,
    `Geometrie_<z>`, `Geometry_<z>`, `Nest_…`), including LWPOLYLINE bulge
    arcs and contour chaining.
  - CSV report (`--log`), dry run (`-n`), recursion (`-r`), and switches for
    thickness, diameter snapping, drill mode, orientation and output
    extension.
- `Tools/check_mpr.py` — pre-flight validator: file structure, coordinates
  inside the part, `ZA` within the thickness, `TI` not deeper than the part,
  plausible diameters, `Konturfraesen` referencing contour elements that
  exist, `WerkStck` agreeing with the data head.
- `Tools/dxf2mpr.cmd` — Windows drag-and-drop wrapper writing to an `MPR`
  sub-folder next to the dropped files.
- `Tools/README.md` — usage, input/output mapping tables, orientation rules,
  option list and limits.
- `Examples/CAD-models/MPR/` — 11 generated programs plus `convert-log.csv`.
- `MANIFEST.md`, `CHANGELOG.md`.

### Verification

- `check_mpr.py` reports no findings on all 82 production programs in
  `Examples/PAL_8681_SM_Alb_Diamant/` and on all 13 generated programs
  (11 from the example DXFs, 1 from `Noptiera-1.dxfbak`, 1 from a synthetic
  2D-layer DXF exercising all four layer families).
- `Noptiera-1.dxf` → 401 × 261 × 18 mm, 6 × Ø7 through + 6 × Ø8 blind 14 deep.
  All 12 positions and diameters match the hand-built woodWOP 9 program in
  `Examples/Noptiera-1.mpr` exactly. Depths differ there because that program
  was drawn on a 410 × 410 × 19 blank and drills every hole through.
- `Noptiera-2.dxf` (binary SAB) → 401 × 261 × 18 mm, 6 × Ø5 deep 9 +
  6 × Ø8 deep 14, consistent with the geometry read out of the ACIS stream.
- `Test-noptiera.dxf` → 9 parts, all laid flat to 18 mm thickness, 5–16
  macros each.
- **Not yet run on a machine.** The first converted program should be opened
  in woodWOP and dry-run before it cuts.

### Known limitations

- Only cylindrical bores become drilling macros. Countersinks, chamfers,
  spherical and toroidal faces are reported as notes and skipped.
- Cavities modelled as solid pockets or grooves are not converted;
  `<112 Tasche>` and `<109 Grooving>` are never generated. From a solid, only
  the outer outline and the bores are read.
- Feeds, speeds and tool numbers stay at `STANDARD` / woodWOP defaults.
- Binary DXF is rejected with a message rather than parsed.
- Route B does not handle `V_Tasche`, `F_Tasche`, `H_Tasche`, `Uni_Bohr`,
  `U_Bohr`, sawing or clamp/suction-cup layers; those layers are ignored and
  reported.

### Notes

- `DS` (arc direction in contour elements) follows the MPR parser constants in
  `Docs/homag-mpr4x-format-us_compress.md` §4 — `_cc` = 0 counter clockwise
  short, `_cw` = 1 clockwise short, `_CC` = 2 and `_CW` = 3 for the same over
  180°. An earlier reading inferred from `Examples/PAL_8681_SM_Alb_Diamant/15_1.MPR`
  had this reversed; the spec was taken as the authority.
- Output is written LF / cp1252. (Wrong — corrected in 0.1.1.)

## [0.0.1] — 2026-09-03

Initial working set assembled; no tooling yet.

### Added

- `Docs/homag-mpr4x-format-us_compress.md` — HOMAG MPR 4.x format spec
  (9-080-42-7190-D00).
- `Docs/Bpp50BasicENU.md` — WEEKE woodWOP DXF-Import Basic 4.7.4 manual
  (9-882-47-4264 ENU11).
- `Examples/Grasshopper/Noptiera ND01xx_test_suruburi.gh` — the parametric
  model the DXF exports come from.
- `Examples/CAD-models/` — `Noptiera-1` (DXF/DWG/backup), `Noptiera-2`
  (DXF + woodWOP scratch MPR), `Test-noptiera.dxf`.
- `Examples/PAL_8681_SM_Alb_Diamant/` — 82 production MPR programs for one
  18 mm board type, part numbers 15…121 (files dated 2026-07-23).
- `Examples/Model-associated/Test-300x600.{mpr,var,ktrx,png}` — one part in
  every woodWOP-related format.
- `Examples/Noptiera-1.mpr` — hand-built woodWOP 9 program for the same
  drilling pattern.
