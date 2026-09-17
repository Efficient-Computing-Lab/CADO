"""
Generates the CADO figures directly from the ontology.

Every diagram is derived from entity.owx and the A-Box files, so a figure cannot
disagree with the axioms it illustrates. Output is vector PDF.

Two deliberate departures from the Protege OntoGraf exports used previously:
property names are written on the edges rather than encoded as colours resolved
through a separate legend, and type sizes are set explicitly so that the figures
remain legible at print size.

    python generate_figures.py --out ../figures
"""

import argparse
import hashlib
import json
import os
import re
import sys
import subprocess

import dot_to_drawio
import figure_palette as palette

from owlready2 import get_ontology, onto_path, Or, ThingClass, sync_reasoner, World

FONT = "Helvetica"
CLASS_FILL, CLASS_LINE = "#E8EAF6", "#5C6BC0"
SUB_FILL, SUB_LINE = "#F1F8E9", "#7CB342"
IND_FILL, IND_LINE = "#FFF8E1", "#F9A825"
EDGE = "#37474F"
SUBCLASS_EDGE = "#5C6BC0"

NODE_FS, EDGE_FS, TITLE_FS = 22, 19, 26


def header(name, rankdir="LR", sep=("0.6", "0.5")):
    return [
        'digraph "%s" {' % name,
        '  graph [rankdir=%s, splines=true, overlap=false, nodesep=%s, ranksep=%s, '
        'fontname="%s", fontsize=%d, pad=0.3];' % (rankdir, sep[0], sep[1], FONT, TITLE_FS),
        '  node  [shape=box, style="rounded,filled", fontname="%s", fontsize=%d, '
        'margin="0.18,0.10", penwidth=1.6];' % (FONT, NODE_FS),
        '  edge  [fontname="%s", fontsize=%d, color="%s", fontcolor="%s", penwidth=1.4, '
        'arrowsize=0.9];' % (FONT, EDGE_FS, EDGE, EDGE),
    ]


def cls_node(name, focus=False):
    fill, line = (SUB_FILL, SUB_LINE) if focus else (CLASS_FILL, CLASS_LINE)
    label = name
    if len(name) > 22 and "_" in name:            # wrap very long class names
        parts = name.split("_")
        half = len(parts) // 2
        label = "_".join(parts[:half]) + "_\\n" + "_".join(parts[half:])
    return '  "%s" [label="%s", fillcolor="%s", color="%s"%s];' % (
        name, label, fill, line, ", penwidth=2.6" if focus else "")


def range_names(prop):
    out = []
    for r in prop.range:
        out.extend([c.name for c in r.Classes] if isinstance(r, Or) else [r.name])
    return out


def domain_names(prop):
    out = []
    for d in prop.domain:
        out.extend([c.name for c in d.Classes] if isinstance(d, Or) else [d.name])
    return out


def elabel(text, color=None):
    """An edge label with an opaque background.

    Graphviz draws edge labels transparently, so any edge routed behind a label
    strikes through the letters. Wrapping the text in a single-cell HTML table
    with a solid BGCOLOR puts the label on top of an opaque patch instead.
    """
    body = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body = body.replace("\\n", "<BR/>")
    color = color or palette.colour(text)
    body = '<FONT COLOR="%s">%s</FONT>' % (color, body)
    return ('<<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="1" CELLSPACING="0" '
            'BGCOLOR="white"><TR><TD>%s</TD></TR></TABLE>>' % body)


# ---------------------------------------------------------------------------
# Ownership of the figure files
#
# By default the generator owns every figure: the diagram is derived from the
# ontology, so it cannot drift from the axioms it illustrates. That guarantee is
# the reason the figures are generated at all.
#
# A figure may still need a human touch that the layout engine cannot give it.
# Editing its .drawio (or exporting a .pdf over the generated one) *adopts* that
# figure: the generator records a checksum for everything it writes, notices the
# change on the next run, and leaves the whole figure alone rather than
# overwriting the work. Adopted figures are listed at the end of each run, so it
# stays visible that they are no longer derived from the ontology.
#
# Use --force to hand a figure back to the generator and discard the edits.
# ---------------------------------------------------------------------------

MANIFEST_NAME = ".figure-manifest.json"
_manifest = {}
_adopted = []
_force = False


def _sha(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_manifest(out_dir):
    global _manifest
    path = os.path.join(out_dir, MANIFEST_NAME)
    try:
        with open(path, encoding="utf-8") as fh:
            _manifest = json.load(fh)
    except (OSError, ValueError):
        _manifest = {}


def save_manifest(out_dir):
    with open(os.path.join(out_dir, MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(_manifest, fh, indent=2, sort_keys=True)


def adopted(path):
    """True if a human has changed anything this figure owns."""
    if _force:
        return False
    for ext in (".drawio", ".pdf"):
        target = path + ext
        recorded = _manifest.get(os.path.basename(target))
        current = _sha(target)
        if recorded and current and current != recorded:
            return True
    return False


def render(lines, path, engine="dot"):
    if adopted(path):
        _adopted.append(os.path.basename(path))
        return path + ".pdf"

    dot = "\n".join(lines + ["}"])
    dot = dot.replace("digraph", "// engine=%s\ndigraph" % engine, 1)
    src = path + ".dot"
    with open(src, "w") as handle:
        handle.write(dot)
    for fmt in ("pdf", "png"):
        subprocess.run([engine, "-T" + fmt, src, "-o", "%s.%s" % (path, fmt)], check=True)
    dot_to_drawio.to_drawio(src, path + ".drawio")     # editable version
    for ext in (".drawio", ".pdf"):
        _manifest[os.path.basename(path + ext)] = _sha(path + ext)
    return path + ".pdf"



# ----------------------------------------------------------------- class figures

# Inverse properties are documented in the summary tables; drawing both
# directions doubles the edges without adding information.
INVERSE_OF = {"utilizedBy": "utilizes", "deployedBy": "deploys",
              "groupedBy": "includesRunningInstance", "hosts": "hostedBy"}


def defined_subclasses(tbox, cls):
    """Subclasses asserted through is_a, plus those defined by equivalence."""
    subs = set(cls.subclasses())
    for other in tbox.classes():
        if other is cls or other in subs:
            continue
        for expr in getattr(other, "equivalent_to", []):
            names = [c.name for c in getattr(expr, "Classes", []) if isinstance(c, ThingClass)]
            if cls.name in names:
                subs.add(other)
    return sorted(subs, key=lambda c: c.name)



def figure_hierarchy(tbox, out):
    lines = header("hierarchy", rankdir="LR", sep=("0.30", "1.30"))
    root = tbox.container_orchestration_environment
    lines.append(cls_node("owl:Thing"))
    lines.append(cls_node(root.name, focus=True))
    lines.append('  "owl:Thing" -> "%s" [arrowhead=onormal, color="%s"];' % (root.name, SUBCLASS_EDGE))

    def walk(parent):
        for child in defined_subclasses(tbox, parent):
            lines.append(cls_node(child.name))
            style = ", style=\"rounded,filled,dashed\"" if child.equivalent_to else ""
            lines.append('  "%s" -> "%s" [arrowhead=onormal, color="%s"%s];'
                         % (parent.name, child.name, palette.SUBCLASS,
                            ", style=dashed" if child.equivalent_to else ""))
            if style:
                lines.append('  "%s" [style="rounded,filled,dashed", penwidth=2.2];' % child.name)
            walk(child)
    walk(root)
    return render(lines, os.path.join(out, "cado-class-hierarchy"))


def figure_class(tbox, cls_name, out):
    cls = getattr(tbox, cls_name)
    lines = header(cls_name, sep=("0.95", "1.10"))
    lines.append(cls_node(cls_name, focus=True))
    seen = {cls_name}

    for prop in sorted(tbox.object_properties(), key=lambda p: p.name):
        if prop.name in INVERSE_OF:
            continue
        doms = domain_names(prop)
        if cls_name not in doms:
            continue
        for target in sorted(set(range_names(prop))):
            if target not in seen:
                lines.append(cls_node(target))
                seen.add(target)
            label = prop.name
            if len(doms) > 1:
                label += "*"        # starred: domain is a union, see caption
            if target == cls_name:
                lines.append('  "%s" -> "%s" [label=%s, color="%s", headport=nw, tailport=ne];'
                             % (cls_name, target, elabel(label), palette.colour(prop.name)))
            else:
                lines.append('  "%s" -> "%s" [label=%s, color="%s"];'
                             % (cls_name, target, elabel(label), palette.colour(prop.name)))

    for sub in defined_subclasses(tbox, cls):
        if sub.name not in seen:
            lines.append(cls_node(sub.name))
            seen.add(sub.name)
        lines.append('  "%s" -> "%s" [arrowhead=onormal, color="%s", label=%s, style=dashed];'
                     % (cls_name, sub.name, palette.SUBCLASS,
                        elabel("is-a", palette.SUBCLASS)))
    # dot, not neato: dot reserves a slot for every edge label in the rank
    # structure, so no edge can be routed through a label. neato places labels
    # at edge midpoints, which in a star topology is exactly where the
    # neighbouring edges run.
    return render(lines, os.path.join(out, "cado-%s" % cls_name.replace("_", "-")),
                  engine="dot")


# ------------------------------------------------------------------ use cases

# Relations that belong to each view. Splitting them keeps every figure to one
# subject and removes the long sweeping edges that used to run past other
# figures' labels.
VIEW_PROPS = {
    "stack": {"utilizes", "pullsImageFrom", "unpacks", "convertsToContainer",
              "includesImage", "savedTo"},
    "application": {"deploys", "includesRunningInstance", "runningInstanceOf",
                    "binds", "hostedBy", "reservesDiskSpaceOn", "dependsOn"},
    "configuration": {"hasVolumeMount", "mountsStorage", "hasEnvironmentVariable"},
}

VIEWS = {
    # the platform, what it is built from, and where images come from
    "stack": ("platform", "runtime_environment", "image_registry", "image", "host"),
    # what is deployed, how it is grouped, and from which image
    "application": ("platform", "deployment_unit", "group_by", "image", "host", "storage"),
    # how the deployed units are configured
    "configuration": ("deployment_unit", "environment_variable", "volume_mount", "storage"),
}


def figure_use_case(tbox, world, platform_name, out, stem, depth=4, view=None):
    plat = world.search_one(iri="*%s" % platform_name)
    props = list(tbox.object_properties())

    show_binds = view == "application"
    allowed_props = VIEW_PROPS.get(view)

    def out_edges(ind):
        """Forward assertions only.

        Inverse properties are skipped: the reasoner materialises them, and
        following them turns the subgraph of one platform into the whole A-Box.
        `binds` is skipped for the same reason -- it is derived from the
        hasVolumeMount o mountsStorage chain and duplicates those two edges.
        """
        found = []
        for prop in props:
            if prop.name in INVERSE_OF:
                continue
            if prop.name == "binds" and not show_binds:
                continue
            if allowed_props is not None and prop.name not in allowed_props:
                continue
            for target in getattr(ind, prop.python_name, []) or []:
                if hasattr(target, "name"):
                    found.append((prop.name, target))
        return found

    # Units that a *different* target platform deploys belong to that platform's
    # figure. Without this, the Kubernetes figure absorbs the Docker containers
    # through containsMinimalDeploymentUnit and duplicates the Docker figure.
    foreign = set()
    for other in world.individuals():
        if other is plat or not isinstance(other, tbox.platform):
            continue
        if not getattr(other, "artifact_format", None):
            continue
        for unit in getattr(other, "deploys", []) or []:
            foreign.add(unit)
            for sub in (getattr(unit, "hasVolumeMount", []) or []):
                foreign.add(sub)
                for st in (getattr(sub, "mountsStorage", []) or []):
                    foreign.add(st)

    keep, frontier = {plat}, [plat]
    for _ in range(depth):
        nxt = []
        for node in frontier:
            for _p, target in out_edges(node):
                # a sibling platform is a different deployment, not part of this one
                if target in foreign:
                    continue
                if target is not plat and isinstance(target, tbox.platform) \
                        and not isinstance(node, tbox.platform):
                    continue
                if target not in keep:
                    keep.add(target)
                    nxt.append(target)
        frontier = nxt
    # grouping constructs and registries point *into* the set
    for ind in world.individuals():
        if ind in keep:
            continue
        if isinstance(ind, (tbox.group_by, tbox.image_registry)):
            if any(t in keep for _p, t in out_edges(ind)):
                keep.add(ind)

    if view:
        allowed = tuple(getattr(tbox, c) for c in VIEWS[view])
        plat_ind = plat
        keep = {i for i in keep if isinstance(i, allowed) or i is plat_ind}

    direction = "LR" if view == "configuration" else "TB"
    # dot places edge labels as virtual nodes, so they cannot overlap; the
    # separation here only has to keep labels clear of the boxes. Widening it
    # further inflates the page and shrinks everything once scaled to text width.
    lines = header(stem, rankdir=direction, sep=("0.42", "1.05"))
    # One identifying value per individual. The full set of data property
    # values is given in the A-Box and in the use-case tables; putting them all
    # in the figure makes the nodes so wide that nothing is legible at page width.
    KEY = ("container_name", "deployment_name", "image_name", "namespace_name",
           "network_name", "service_name", "volume_name", "mount_path", "variable_name")
    by_name = {p.name: p for p in tbox.data_properties()}
    data_props = [by_name[k] for k in KEY if k in by_name]

    for ind in sorted(keep, key=lambda i: i.name):
        types = [c.name for c in ind.is_a if isinstance(c, ThingClass)]
        # Wrap the individual's name: unwrapped names make nodes 3in wide, and
        # a dozen such nodes cannot be laid out legibly at page width.
        words, line, wrapped = ind.name.replace("_", " ").split(), "", []
        for word in words:
            if len(line) + len(word) + 1 > 14 and line:
                wrapped.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            wrapped.append(line)
        rows = ["<B>%s</B>" % "<BR/>".join(wrapped)]
        if types:
            primary = sorted(types, key=len)[0]
            rows.append('<FONT POINT-SIZE="17"><I>%s</I></FONT>' % primary)
        for prop in data_props:
            vals = getattr(ind, prop.python_name, None)
            if vals is None:
                continue
            vals = vals if isinstance(vals, list) else [vals]
            if vals:
                v = str(vals[0]).replace("&", "&amp;").replace("<", "&lt;")
                rows.append('<FONT POINT-SIZE="16">%s</FONT>' % v)
                break                     # one identifying value is enough
        lines.append('  "%s" [label=<%s>, fillcolor="%s", color="%s"];'
                     % (ind.name, "<BR/>".join(rows), IND_FILL, IND_LINE))

    for ind in sorted(keep, key=lambda i: i.name):
        for prop_name, target in sorted(out_edges(ind), key=lambda e: (e[0], e[1].name)):
            if prop_name in INVERSE_OF or (prop_name == "binds" and not show_binds):
                continue          # inverse, or derived by the property chain
            if target in keep:
                label = prop_name + " (inferred)" if prop_name == "binds" else prop_name
                lines.append('  "%s" -> "%s" [label=%s, color="%s"];'
                             % (ind.name, target.name, elabel(label),
                                palette.colour(prop_name)))
    return render(lines, os.path.join(out, stem))


def verify_palette(out_dir, made):
    """Guarantee: no two relationship colours that appear in the
    same diagram may be closer than the palette threshold in CIE Lab, or the
    reader cannot tell two relationships apart in print. Checked here rather
    than asserted, so a palette edit cannot quietly break it."""
    groups = {}
    for path in made:
        src = path[:-4] + ".dot" if path.endswith(".pdf") else path + ".dot"
        if not os.path.exists(src):
            continue
        text = open(src, encoding="utf-8").read()
        labels = [re.sub(r"<[^>]*>", "", cell)
                  for cell in re.findall(r"<TD>(.*?)</TD>", text, re.S)]
        groups[os.path.basename(src)] = labels
    problems = palette.check_contrast(groups)
    if problems:
        print("\nPalette check FAILED: colours too close to tell apart in print")
        for name, a, b, distance in problems:
            print("   - %s: %s vs %s (deltaE %.1f)" % (name, a, b, distance))
        return False
    print("Palette check: %d figure(s), no two co-occurring relationship "
          "colours below deltaE %.0f." % (len(groups), 25))
    return True


def main():
    ap = argparse.ArgumentParser(description="Generate the CADO figures from the ontology")
    ap.add_argument("--ontology", default="../ontology_files")
    ap.add_argument("--out", default="../figures")
    ap.add_argument("--force", action="store_true",
                    help="regenerate figures that were edited by hand, discarding the edits")
    args = ap.parse_args()

    global _force
    _force = args.force

    onto_dir = os.path.abspath(args.ontology)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    load_manifest(out)
    onto_path.append(onto_dir)

    tbox = get_ontology(os.path.join(onto_dir, "entity.owx")).load()
    made = [figure_hierarchy(tbox, out)]
    for cls in ["platform", "runtime_environment", "deployment_unit", "group_by",
                "storage", "image", "image_registry", "secret", "volume_mount"]:
        made.append(figure_class(tbox, cls, out))

    for abox, targets in [("instances.owl", [("Docker", "cado-use-case-docker"),
                                             ("Kubernetes", "cado-use-case-kubernetes")]),
                          ("instances_microservice.owl", [("Docker", "cado-use-case-microservice-docker"),
                                                          ("Kubernetes", "cado-use-case-microservice-kubernetes")])]:
        world = World()
        world.get_ontology(os.path.join(onto_dir, "entity.owx")).load()
        a = world.get_ontology(os.path.join(onto_dir, abox)).load()
        sync_reasoner(world, infer_property_values=True, debug=0)
        t = world.get_ontology(os.path.join(onto_dir, "entity.owx"))
        for platform, stem in targets:
            # The "configuration" view is defined but not emitted: the unit-to-variable
            # and unit-to-mount fans make it too wide to stay legible at page width,
            # and the same values are tabulated in the use-case tables.
            for view in ("stack", "application"):
                made.append(figure_use_case(t, world, platform, out,
                                            "%s-%s" % (stem, view), view=view))

    save_manifest(out)
    palette_ok = verify_palette(out, made)
    regenerated = [p for p in made if os.path.basename(p)[:-4] not in _adopted]
    print("Generated %d figure(s) in %s:" % (len(regenerated), out))
    for path in regenerated:
        print("   -", os.path.basename(path))
    if _adopted:
        print("\nLeft untouched, because they were edited by hand (%d):" % len(_adopted))
        for name in _adopted:
            print("   -", name)
        print("These are no longer derived from the ontology; re-check them after "
              "changing it, or pass --force to regenerate and discard the edits.")
    if not palette_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
