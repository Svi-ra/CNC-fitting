# CNC-fitting — project manifest

Working set for getting furniture parts from CAD onto a HOMAG/WEEKE CNC in
woodWOP MPR format. It holds the two format references, a set of real and test
CAD/CAM files, and a converter that turns DXF solids directly into MPR
programs.

- **Root:** `D:\CNC-fitting`
- **Machine format:** woodWOP MPR 4.x (HOMAG/WEEKE), millimetres
- **Not a git repository.** Version history is tracked by hand in
  [CHANGELOG.md](CHANGELOG.md).

## Layout

```
CNC-fitting/
├─ CHANGELOG.md               change history
├─ MANIFEST.md                this file
├─ Docs/                      format references (2 files)
├─ Examples/                  CAD sources, reference programs, output
│  ├─ CAD-models/             the DXF/DWG sources
│  │  └─ MPR/                 converter output (generated)
│  ├─ Grasshopper/            the parametric model the DXFs come from
│  ├─ Model-associated/       one part in every woodWOP-related format
│  └─ PAL_8681_SM_Alb_Diamant/  a real 82-part production batch
└─ Tools/                     the converter and its checker
```

## Docs — format references

| File | Lines | What it is |
| --- | --- | --- |
| `Docs/homag-mpr4x-format-us_compress.md` | 5020 | HOMAG **MPR 4.x file format** spec (9-080-42-7190-D00). Data head, variable table, coordinate systems, contour elements, and every processing macro with its ID number and parameters. This is the authority for everything `dxf2mpr.py` writes. |
| `Docs/Bpp50BasicENU.md` | 2454 | WEEKE **woodWOP DXF-Import Basic 4.7.4** manual (9-882-47-4264 ENU11). Requirements on the CAD system and the drawing, and §3.3 the drawing-layer conventions (`Werkstk_<t>`, `V_Bohr…`, `H_Bohr…`, `V_Fraes…`). |

Key sections used by the tooling:

- MPR §3 parameter row format, §4 parser constants (`_cc`/`_cw`/`_CC`/`_CW`
  arc directions, `STANDARD` keyword), §7 coordinate systems, §8 contour
  elements, §9.1.1 `WerkStck`, §9.2.1–9.2.4 the drilling macros.
- DXF-Import §1.2 drawing requirements, §3.3 the full drawing-layer table.

## Examples

### `Examples/CAD-models/` — the DXF sources

| File | Format | Contents |
| --- | --- | --- |
| `Noptiera-1.dxf` | DXF AC1021 (2007), ASCII SAT | one 3D solid, 401 × 261 × 18 mm, 12 bores |
| `Noptiera-1.dxfbak` | same, earlier export | identical part, positioned at Z −18…0 |
| `Noptiera-1.dwg` | DWG | the same part |
| `Noptiera-2.dxf` | DXF AC1027 (2013), **binary SAB/ASM** in `ACDSDATA` | one 3D solid, 401 × 261 × 18 mm, 12 bores |
| `Noptiera-2.mpr` | MPR | woodWOP 9 scratch program, 410 × 410 × 19 — not a conversion of the DXF |
| `Test-noptiera.dxf` | DXF AC1021, ASCII SAT | **9 solids** — a whole nightstand in assembly position |

All of these come out of Grasshopper via the Pancake exporter: model space
holds solids only, on layer `PancakeDefault`. **woodWOP DXF-Import cannot read
any of them** — it needs 2D elements on named layers. That is what
`Tools/dxf2mpr.py` exists to work around.

### `Examples/CAD-models/MPR/` — generated output

11 MPR programs plus `convert-log.csv`, produced by:

```bash
python Tools/dxf2mpr.py Examples/CAD-models -o Examples/CAD-models/MPR --log Examples/CAD-models/MPR/convert-log.csv
```

Regenerate at any time; nothing else depends on these files.

### `Examples/Noptiera-1.mpr` — hand-built reference

A woodWOP 9.0.152 program for the same drilling pattern (410 × 410 × 19 panel,
12 × `BohrVert`, one `<121 Block>`). Its 12 drill positions and diameters match
the converter's output for `Noptiera-1.dxf` exactly; the panel size and the
depths differ because it was drawn on a different blank. Useful as a
side-by-side of hand-built vs generated MPR, not as a conversion target.

### `Examples/Model-associated/` — one part, four formats

`Test-300x600` as `.mpr` (600 × 300 × 18 program), `.var` (woodWOP variable
list, `L`/`B`/`D`), `.ktrx` (OpenCascade OCAF XML model) and `.png` (preview).
Shows how woodWOP carries a program, its variables and its 3D model together.

### `Examples/PAL_8681_SM_Alb_Diamant/` — real production batch

82 MPR programs for one board type (PAL 8681 SM Alb Diamant, 18 mm), part
numbers 15…121, sizes 100 × 45 to 1251 × 520 mm. Macro mix: 474 `BohrVert`,
297 `BohrHoriz`, 88 `Konturfraesen`, 16 `Tasche`, 82 `WerkStck`.

This is the **behavioural reference** for generated output — real files that
run on the machine. `Tools/check_mpr.py` passes on all 82.

### `Examples/Grasshopper/`

`Noptiera ND01xx_test_suruburi.gh` — the parametric definition the DXF exports
come from (`suruburi` = screws; the Ø7 through-holes are confirmat clearance,
the Ø8 blind holes are dowels).

## Tools

| File | Purpose |
| --- | --- |
| `Tools/dxf2mpr.py` | DXF → MPR batch converter. Reads ACIS solids (ASCII SAT and binary SAB) and woodWOP-layered 2D DXF. |
| `Tools/check_mpr.py` | Pre-flight validator for MPR programs — structure, coordinates inside the part, depths, diameters, contour references. |
| `Tools/dxf2mpr.cmd` | Windows drag-and-drop wrapper; writes to an `MPR` sub-folder. |
| `Tools/README.md` | Usage, the full feature→macro mapping, orientation rules, options and limits. |

Python 3.8+, standard library only. No install step.

## Conventions

**woodWOP part coordinate system (0)** — origin at the lower-left corner of the
underside; X = length (`LA`/`_BSX`), Y = width (`BR`/`_BSY`), Z = 0 at the
bottom face up to `DI`/`_BSZ`. Vertical drillings enter from the top and
`TI` is the depth; `ZA` of a horizontal drilling is the height above the
bottom face.

**MPR files** — **CRLF** line endings, cp1252, `[H` data head, a single-space
line between blocks, `!` immediately after the last block. woodWOP splits the
program on CRLF; an LF-only file opens as an empty default blank with no error
message.

**woodWOP layer names** (DXF-Import §3.3, and route B of the converter) use
`_` as the decimal point: `V_Bohr1_12_5` = mode 1, depth 12.5 mm.

## Data flow

```
Grasshopper (.gh)
      │  Pancake export
      ▼
   DXF with ACIS solids ──✗── woodWOP DXF-Import   (cannot read solids)
      │
      │  Tools/dxf2mpr.py
      ▼
   MPR ──► Tools/check_mpr.py ──► woodWOP ──► machine
```

The alternative path stays open: export 2D geometry on the §3.3 layer names
and either DXF-Import or `dxf2mpr.py --force-2d` will read it. The layer
naming is identical for both, so the two routes are interchangeable.
