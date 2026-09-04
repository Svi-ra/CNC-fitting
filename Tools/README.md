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

| | Name | Type | Access |
| --- | --- | --- | --- |
| input | `B` | Brep | **Tree** — one part per branch |
| output | `MPR` | — | one MPR program as text per branch |
| output | `INFO` | — | one report line per part |

**Parts are expected to arrive lying flat in the world XY plane**, thickness
along Z. Nothing is ever rotated out of that plane. A part fed in standing on
edge is reported in `INFO` as a `WARNING` rather than quietly corrected,
because turning it would contradict the layout the definition produced.

Beyond that it takes raw solids with no attached data and recognises the rest:
the world bounding box gives the panel size, cylindrical faces become
drillings classified by which face they break out through, and the top face
outline becomes a contour when it is not simply the bounding rectangle.

Two in-plane adjustments are on by default and are pure rotations about Z or
about X by 180 degrees, so the part stays flat either way:

| Setting | Default | Effect |
| --- | --- | --- |
| `LONG_X` | on | turn the part 90 degrees so its long side runs along X, as `LA`/`_BSX` expects |
| `FLIP` | on | turn the part over when every vertical bore would otherwise be drilled from underneath |

Set either to `False` in the `SETTINGS` block if the definition already places
parts exactly as they should be machined. The rest of that block is `SNAP`,
`MAX_DIA`, `BM_VERT`, `THICKNESS` and `CONTOUR`.

It outputs **text, not files**. When you write it out, use CRLF —
`open(path, "w", encoding="cp1252", newline="\r\n")` — for the reason in the
previous section. Put a boolean `Run` gate in front of any file writing, or a
solve on every slider drag will write the whole batch.

The component assumes the Rhino document is in millimetres and puts a warning
in `INFO` if it is not.

## Limits — read this before the first cut

* **The output has not been run on a machine.** It matches the MPR 4.x
  specification in `Docs/homag-mpr4x-format-us_compress.md` and the structure
  of the shop's existing programs, and `check_mpr.py` passes on all 82 of them
  as well as on everything this tool generates — but the first converted
  program should still be opened in woodWOP and dry-run before it cuts.
* Only cylindrical bores become drilling macros. Countersinks, chamfers,
  spherical and toroidal faces are reported as notes and skipped.
* Pockets and grooves modelled as solid cavities are **not** converted
  (`<112 Tasche>`, `<109 Grooving>` are not generated). Only the outer
  outline and bores are read from a solid.
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
