# Changelog

All notable changes to this project are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and
refer to the tooling in `Tools/`; the reference material in `Docs/` and
`Examples/` is inventoried in [MANIFEST.md](MANIFEST.md).

Repository: https://github.com/Svi-ra/CNC-fitting

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
