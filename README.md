# CNC-fitting

Getting furniture parts from CAD onto a HOMAG/WEEKE CNC in **woodWOP MPR**
format — including a converter that reads DXF files woodWOP's own DXF-Import
cannot open.

## The problem

DXF files exported from Rhino/Grasshopper (and most 3D CAD) contain a **3D
ACIS solid** and nothing else. woodWOP DXF-Import works only on 2D lines,
arcs, circles and blocks sorted onto its own layer names, and has no ACIS
interpreter — so those files import as an empty drawing.

`Tools/dxf2mpr.py` goes straight from the solid to a finished MPR program and
skips DXF-Import entirely.

## Quick start

Python 3.8+, standard library only. Nothing to install.

```bash
python Tools/dxf2mpr.py part.dxf
```

```bash
python Tools/dxf2mpr.py C:\parts -r -o C:\out --log C:\out\convert-log.csv
python Tools/check_mpr.py C:\out -r
```

On a shop PC, drag DXF files or a folder onto `Tools/dxf2mpr.cmd`.

## What it does

Decodes the embedded ACIS stream — both the obfuscated ASCII **SAT** form
(DXF up to 2010) and the binary **SAB/ASM** form carried in the `ACDSDATA`
section (DXF 2013+) — rebuilds the B-rep, and writes:

| Feature | MPR macro |
| --- | --- |
| panel size | `<100 \WerkStck\` |
| bore along Z, open at the top | `<102 \BohrVert\` |
| bore along Z, open only at the bottom | `<131 \UfluBohr\` |
| bore along X or Y, open at an edge | `<103 \BohrHoriz\` |
| bore at any other angle | `<104 \BohrUniv\` |
| non-rectangular outline | contour `]n` + `<105 \Konturfraesen\` |

Each ACIS body becomes its own MPR, and parts modelled in assembly position
are laid flat automatically — thinnest direction to Z, long side to X, turned
over if all the drilling would otherwise come from underneath.

It also reads the *other* kind of DXF: flat geometry on woodWOP layer names
(`Werkstk_18`, `V_Bohr1_12_5`, `H_Bohr_9`, `V_Fraes_-6T3`), so both routes
stay interchangeable.

## Straight from Grasshopper

`Tools/gh_brep2mpr.py` is the same MPR writer behind a Rhino 8 Script
component: feed it a data tree of raw Breps (one part per branch, already
lying flat in XY) and it returns the MPR programs as text, with a file name
for each. No DXF, no ACIS decoding — Rhino already holds the geometry, so the
component reads cylinders straight off the Brep faces.

It also knows what the drilling head is fitted with — which diameters the
vertical array carries, and which bit sits on each side for horizontal bores.
A part whose holes cannot all be reached in one clamping comes out as two
programs, one face up and one for the piece turned over, named `-F` and `-B`.
Anything the machine still cannot reach is reported rather than quietly
written. See
[Tools/README.md](Tools/README.md#grasshopper-component).

## Documentation

| File | Contents |
| --- | --- |
| [Tools/README.md](Tools/README.md) | Full usage, mapping tables, orientation rules, options, limits |
| [MANIFEST.md](MANIFEST.md) | What every folder and file in this repository is |
| [CHANGELOG.md](CHANGELOG.md) | Change history |

## Status

Working and validated against real production data: `Tools/check_mpr.py`
reports no findings on the 82 shop programs in
`Examples/PAL_8681_SM_Alb_Diamant/` or on any generated program, and generated
output is structurally identical to those files.

**Not yet proven on a machine.** Open a converted program in woodWOP and dry
run it before it cuts. Known limits — pockets and grooves modelled as solid
cavities are not converted, and feeds/speeds/tools stay at woodWOP defaults —
are listed in [Tools/README.md](Tools/README.md).

## Note on the reference documents

`Docs/` contains manufacturer documentation — the HOMAG MPR 4.x format
specification (9-080-42-7190-D00) and the WEEKE woodWOP DXF-Import Basic
manual (9-882-47-4264 ENU11) — reproduced here as working references. They are
the property of their respective publishers and are not covered by any licence
granted over the rest of this repository.
