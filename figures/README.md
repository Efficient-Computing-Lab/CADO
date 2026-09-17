# Figures

Every figure here is generated from the ontology by
`ontology_python_tools/generate_figures.py`, in four formats:

| File | Purpose |
|---|---|
| `*.pdf` | vector figure, for print |
| `*.png` | raster preview, for the repository README and quick viewing |
| `*.drawio` | editable diagram — open at app.diagrams.net or in the draw.io desktop / VS Code editor |
| `*.dot` | the Graphviz source the other three are built from |

The `.drawio` files are uncompressed mxGraph XML, so they diff cleanly in git.
Node positions come from the Graphviz layout, so an opened diagram matches the
published PDF; edges carry no fixed waypoints, so draw.io reroutes them as soon
as a node is moved.

## Who owns a figure

By default the generator owns them all. That is the point: a diagram derived
from `entity.owx` cannot contradict the axioms it illustrates, which is what
went wrong in the previous version of this work.

    cd ontology_python_tools
    python3 generate_figures.py --out ../figures

Sometimes a figure needs a human touch the layout engine cannot give it —
nudging a label clear of a line, or annotating one point for the text. Editing a
`.drawio`, or exporting a `.pdf` over a generated one, **adopts** that figure.
The generator records a checksum of everything it writes (`.figure-manifest.json`),
notices the change on the next run, and leaves that figure alone instead of
overwriting the work. Adopted figures are listed at the end of each run:

    Left untouched, because they were edited by hand (1):
       - cado-group-by
    These are no longer derived from the ontology; re-check them after changing
    it, or pass --force to regenerate and discard the edits.

An adopted figure has given up the guarantee that it matches the ontology, so
check it by hand whenever the ontology changes. To hand one back to the
generator and discard the edits:

    python3 generate_figures.py --out ../figures --force

## Use case figures

The WordPress and MySQL use case is split into a *stack* view (platform,
runtime environments, registry, image placement) and an *application* view
(what is deployed, how it is grouped, what storage it binds). A single combined
diagram cannot be made legible at page width.

The four `cado-use-case-microservice-*` figures are generated from the second
A-Box, `instances_microservice.owl`.

## Legibility

Diagrams are sized so that labels stay readable once scaled to a page width.
Every figure renders its labels at 6.9pt or larger at a 6.9in text width; most
are 10pt or more. Edge labels are drawn on an opaque background so that edges
routed behind them do not strike through the text.
