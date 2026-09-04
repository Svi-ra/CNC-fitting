# Changelog

All notable changes to this project are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and
refer to the tooling in `Tools/`; the reference material in `Docs/` and
`Examples/` is inventoried in [MANIFEST.md](MANIFEST.md).

Repository: https://github.com/Svi-ra/CNC-fitting

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
