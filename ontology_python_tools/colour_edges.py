"""
Applies the shared relationship palette to existing .drawio diagrams, in place.

Only the `style` of each edge is touched (and, where it is wrong, an edge's
label). Node positions, sizes, labels and every hand-made layout change are left
exactly as they are, so this is safe to run over diagrams that have been edited
by hand.

    python colour_edges.py ../figures/*.drawio
"""

import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

import figure_palette as palette

# labels that name something the ontology does not have; the value is the
# property actually intended
LABEL_FIXES = {
    "depends_on": "dependsOn",       # v1 data property; the object property is dependsOn
}


def _set_style(style, **kv):
    parts = [p for p in (style or "").split(";") if p]
    keys = {p.split("=")[0]: i for i, p in enumerate(parts) if "=" in p}
    for k, v in kv.items():
        if k in keys:
            parts[keys[k]] = "%s=%s" % (k, v)
        else:
            parts.append("%s=%s" % (k, v))
    return ";".join(parts) + ";"


def recolour(path, backup=True):
    tree = ET.parse(path)
    root = tree.getroot()
    changed, fixed, unknown = 0, [], []

    for cell in root.findall(".//mxCell"):
        if cell.get("edge") != "1":
            continue
        label = (cell.get("value") or "").strip()
        name = palette.normalise(label)

        if name in LABEL_FIXES:
            corrected = LABEL_FIXES[name]
            cell.set("value", label.replace(name, corrected))
            fixed.append((name, corrected))
            name = corrected

        if name and name not in palette.PALETTE:
            unknown.append(name)

        colour = palette.colour(name) if name else palette.SUBCLASS
        cell.set("style", _set_style(cell.get("style"),
                                     strokeColor=colour,
                                     fontColor=colour,
                                     labelBackgroundColor="#FFFFFF"))
        changed += 1

    if backup:
        shutil.copy2(path, path + ".bak")
    tree.write(path, encoding="utf-8", xml_declaration=False)
    return changed, fixed, unknown


def main():
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        return
    total, all_fixed, all_unknown = 0, [], []
    for path in sorted(targets):
        n, fixed, unknown = recolour(path)
        total += n
        all_fixed += [(os.path.basename(path),) + f for f in fixed]
        all_unknown += [(os.path.basename(path), u) for u in unknown]
        print("  %-52s %2d edges coloured" % (os.path.basename(path), n))
    print("\n%d edges coloured across %d diagrams" % (total, len(targets)))
    if all_fixed:
        print("\nLabels corrected (they named something not in the ontology):")
        for f, was, now in all_fixed:
            print("   %s: %s -> %s" % (f, was, now))
    if all_unknown:
        print("\nStill unrecognised (drawn in the default grey):")
        for f, u in all_unknown:
            print("   %s: %s" % (f, u))


if __name__ == "__main__":
    main()
