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

It also knows what the machine is fitted with — which diameters the vertical
array carries, which bit sits on each side for horizontal bores, and how the
grooving saw runs. Sawn grooves are read off the solid alongside the bores. A
part that cannot all be reached in one clamping comes out as two programs, one
face up and one for the piece turned over, named `-B` and `-F` for the side
the operator sees — with the face up under the head, that is the back.
Anything the machine still cannot reach is reported rather than quietly
written.

It also places each piece so the machine can **hold** it. Each setup may be
turned end for end as well as over, and of the placements that reach the
bores, the one that keeps a cut corner, rebate or pocket away from where the
gripper takes hold wins — even at the cost of a second setup. It writes
boring and sawing only: a shaped outline is not milled, since the machine has
no router, so the piece must arrive cut to shape.

Panels of the same shape are converted once however many times they appear:
the quantities are added up and the file is named for the total. Material and
grain direction come in beside the geometry — panels of the same shape cut
from different board, or laid across the grain, stay separate pieces — and the
component also returns the cut list,
`Material;ID;Lungime;Latime;Cantitate;Denumire;L-1;L-2;W-1;W-2`. Each panel's
name comes in the same way and is kept through the folding: copies of one
shape that carry different names share a program but keep a cut list line
each. Programs are numbered from 1, and the cut list's `ID` is the number on
the file name.

Edge banding comes in the same way: a pattern per part (`0011`, `1010` …,
read clockwise on the part's own plane) becomes a graphic comment on each
banded edge, a blue line just outside it, as woodWOP draws it. The marks
are turned with the piece exactly as its bores are, so in every setup they
sit on the edge that is really banded, and they change nothing that is
machined. A code per side (`1221` …) and a map of what each code stands for
(`ABS 22/1=1` …) add the banding material: it rides the same turns as the
marks, is named on them in the report, and fills the cut list's edge
columns.
See [Tools/README.md](Tools/README.md#grasshopper-component).

The cut list goes on to Excel through a second component,
`Tools/gh_cutlist2json.py`: give it the exact material name for each
category and the project name, and it returns one JSON that lays the list
out the way the shop's Excel cut lists are — a block per material (categories
that share a material share a block), the panel names as comments, `Nr.` the
program's number, and each banded edge's material and thickness in the three
cells the cutting software imports. A third component,
`Tools/gh_json2xlsx.py`, turns that JSON into the text files of an `.xlsx`:
zipped by ShapeDiver's archive download, they open in Excel as the finished
sheet, ready to print with no macro. Two variants of it,
`Tools/gh_json2xlsx_short.py` and `Tools/gh_json2xlsx_split.py`, write the
sheet with one cell per edge, or as a workbook per material. On the desktop,
`Tools/CutListImport.bas`, imported into Excel's VBA editor, builds the same
sheet from a saved `.json`. See
[Tools/README.md](Tools/README.md#excel-cut-list).

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
