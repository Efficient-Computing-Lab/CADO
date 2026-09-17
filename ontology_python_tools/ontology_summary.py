"""
Emits a compact summary of the CADO ontology: every class, object property and
data property with its domain, range and restrictions.

Produces Markdown (default) or LaTeX tables.

    python ontology_summary.py --classes ../ontology_files/entity.owx
    python ontology_summary.py --classes ../ontology_files/entity.owx --format latex
"""

import argparse
import os

from owlready2 import (get_ontology, onto_path, And, Or, Not, Restriction,
                       ThingClass, FunctionalProperty,
                       AsymmetricProperty, IrreflexiveProperty)

# owlready2.class_construct restriction type codes
SYMBOLS = {24: "some", 25: "only", 26: "exactly", 27: "min", 28: "max", 29: "value",
           117: "Self"}


def render(expression):
    if isinstance(expression, And):
        return " and ".join(render(c) for c in expression.Classes)
    if isinstance(expression, Or):
        return " or ".join(render(c) for c in expression.Classes)
    if isinstance(expression, Not):
        return "not (%s)" % render(expression.Class)
    if isinstance(expression, Restriction):
        keyword = SYMBOLS.get(expression.type, str(expression.type))
        cardinality = getattr(expression, "cardinality", None)
        target = getattr(expression, "value", None)
        parts = [expression.property.name, keyword]
        if cardinality is not None:
            parts.append(str(cardinality))
        if target is not None:
            parts.append(render(target))
        return " ".join(parts)
    if isinstance(expression, ThingClass):
        return expression.name
    if isinstance(expression, type):
        return "xsd:%s" % expression.__name__
    return str(expression)


def collect(tbox):
    classes, objects, datas = [], [], []

    for cls in sorted(tbox.classes(), key=lambda c: c.name):
        parents = [p.name for p in cls.is_a if isinstance(p, ThingClass)]
        restrictions = [render(p) for p in cls.is_a if isinstance(p, Restriction)]
        defined = [render(e) for e in cls.equivalent_to]
        if parents in ([], ["Thing"]) and cls.equivalent_to:
            # A defined class states its genus inside the equivalence axiom.
            for expression in cls.equivalent_to:
                if isinstance(expression, And):
                    parents = [render(c) for c in expression.Classes
                               if isinstance(c, ThingClass)]
            parents = parents or ["owl:Thing"]
        parents = [p for p in parents if p != "Thing"] or ["owl:Thing"]
        classes.append({
            "name": cls.name,
            "parent": ", ".join(parents) or "owl:Thing",
            "definition": "; ".join(defined),
            "restrictions": "; ".join(restrictions),
            "comment": (cls.comment[0] if cls.comment else ""),
        })

    for prop in sorted(tbox.object_properties(), key=lambda p: p.name):
        characteristics = []
        if AsymmetricProperty in prop.is_a:
            characteristics.append("asymmetric")
        if IrreflexiveProperty in prop.is_a:
            characteristics.append("irreflexive")
        if prop.inverse_property is not None:
            characteristics.append("inverse of %s" % prop.inverse_property.name)
        objects.append({
            "name": prop.name,
            "domain": " or ".join(render(d) for d in prop.domain) or "-",
            "range": " or ".join(render(r) for r in prop.range) or "-",
            "characteristics": ", ".join(characteristics) or "-",
            "comment": (prop.comment[0] if prop.comment else ""),
        })

    for prop in sorted(tbox.data_properties(), key=lambda p: p.name):
        datas.append({
            "name": prop.name,
            "domain": " or ".join(render(d) for d in prop.domain) or "-",
            "range": " or ".join(render(r) for r in prop.range) or "-",
            "characteristics": "functional" if FunctionalProperty in prop.is_a else "-",
            "comment": (prop.comment[0] if prop.comment else ""),
        })

    return classes, objects, datas


def markdown_table(title, rows, columns):
    lines = ["", "### %s" % title, "",
             "| " + " | ".join(c[1] for c in columns) + " |",
             "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[c[0]]).replace("|", "\\|") or "-"
                                       for c in columns) + " |")
    return "\n".join(lines)


def latex_table(title, rows, columns):
    spec = "l" * len(columns)
    lines = ["", "\\begin{table}[t]", "\\centering", "\\small",
             "\\caption{%s}" % title,
             "\\begin{tabular}{%s}" % spec, "\\hline",
             " & ".join(c[1] for c in columns) + " \\\\", "\\hline"]
    for row in rows:
        cells = [str(row[c[0]]).replace("_", "\\_").replace("&", "\\&") or "-"
                 for c in columns]
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\hline", "\\end{tabular}", "\\end{table}"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Summarise the CADO ontology")
    parser.add_argument("--classes", required=True)
    parser.add_argument("--format", choices=["markdown", "latex"], default="markdown")
    parser.add_argument("--out", help="Write to this file instead of stdout")
    args = parser.parse_args()

    onto_path.append(os.path.dirname(os.path.abspath(args.classes)))
    tbox = get_ontology(os.path.abspath(args.classes)).load()
    classes, objects, datas = collect(tbox)

    build = markdown_table if args.format == "markdown" else latex_table
    blocks = [
        build("CADO classes", classes,
              [("name", "Class"), ("parent", "Subclass of"),
               ("definition", "Equivalent to"), ("restrictions", "Restrictions")]),
        build("CADO object properties", objects,
              [("name", "Object property"), ("domain", "Domain"),
               ("range", "Range"), ("characteristics", "Characteristics")]),
        build("CADO data properties", datas,
              [("name", "Data property"), ("domain", "Domain"),
               ("range", "Range"), ("characteristics", "Characteristics")]),
    ]
    header = ("# CADO ontology summary\n\n"
              "%d classes, %d object properties, %d data properties.\n"
              % (len(classes), len(objects), len(datas)))
    text = header + "\n".join(blocks) + "\n"

    if args.out:
        with open(args.out, "w") as handle:
            handle.write(text)
        print("Wrote %s" % args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
