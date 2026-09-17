"""
Converts the generated Graphviz sources into editable draw.io diagrams.

Node positions are taken from the Graphviz layout, so an opened .drawio file
matches the published PDF. Edges are emitted as source/target references rather
than fixed paths, so draw.io reroutes them as soon as a node is moved.

The files are plain, uncompressed mxGraph XML: open them at app.diagrams.net or
in the VS Code / desktop draw.io editor.
"""

import html
import os
import re
import subprocess

PT = 1.0            # Graphviz plain coordinates are inches; multiplied by 72 below
INCH = 72.0

STYLE_CLASS   = ("rounded=1;whiteSpace=wrap;html=1;fillColor=#E8EAF6;strokeColor=#5C6BC0;"
                 "strokeWidth=1.5;fontFamily=Helvetica;fontSize=%d;fontColor=#1A237E;verticalAlign=middle;")
STYLE_FOCUS   = ("rounded=1;whiteSpace=wrap;html=1;fillColor=#F1F8E9;strokeColor=#7CB342;"
                 "strokeWidth=2.5;fontFamily=Helvetica;fontSize=%d;fontColor=#1B5E20;verticalAlign=middle;")
STYLE_DEFINED = ("rounded=1;whiteSpace=wrap;html=1;fillColor=#E8EAF6;strokeColor=#5C6BC0;"
                 "strokeWidth=2;dashed=1;fontFamily=Helvetica;fontSize=%d;fontColor=#1A237E;verticalAlign=middle;")
STYLE_IND     = ("rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF8E1;strokeColor=#F9A825;"
                 "strokeWidth=1.5;fontFamily=Helvetica;fontSize=%d;fontColor=#3E2723;verticalAlign=middle;")
STYLE_EDGE    = ("edgeStyle=none;rounded=0;html=1;endArrow=classic;endFill=1;strokeColor=#37474F;"
                 "strokeWidth=1.4;fontFamily=Helvetica;fontSize=%d;fontColor=#37474F;"
                 "labelBackgroundColor=#FFFFFF;")
STYLE_ISA     = ("edgeStyle=none;rounded=0;html=1;endArrow=block;endFill=0;dashed=1;"
                 "strokeColor=#5C6BC0;strokeWidth=1.4;fontFamily=Helvetica;fontSize=%d;"
                 "fontColor=#5C6BC0;labelBackgroundColor=#FFFFFF;")

CLASS_FILL, SUB_FILL, IND_FILL = "#E8EAF6", "#F1F8E9", "#FFF8E1"

NODE_FS, EDGE_FS = 14, 12


def _unquote(tok):
    return tok[1:-1] if len(tok) > 1 and tok[0] == '"' and tok[-1] == '"' else tok


def _split_plain(line):
    """Split a -Tplain line, honouring quoted fields."""
    return [t for t in re.findall(r'"[^"]*"|\S+', line)]


def _bracketed(text, i):
    """Read a Graphviz <...> label starting at text[i], honouring nesting.

    A non-greedy regex cannot be used here: an HTML-like label contains further
    angle brackets, so the first '>' is not the end of the label.
    """
    depth, start = 0, i
    while i < len(text):
        if text[i] == "<":
            depth += 1
        elif text[i] == ">":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def _read_label(attrs):
    """The value of label=... whether it is quoted or angle-bracketed."""
    k = attrs.find("label=")
    if k < 0:
        return ""
    j = k + len("label=")
    if attrs[j] == "<":
        raw, _ = _bracketed(attrs, j)
        return raw, True
    if attrs[j] == '"':
        end = j + 1
        while end < len(attrs) and not (attrs[end] == '"' and attrs[end - 1] != "\\"):
            end += 1
        return attrs[j + 1:end], False
    end = j
    while end < len(attrs) and attrs[end] not in ", ]":
        end += 1
    return attrs[j:end], False


def _table_text(label):
    """Pull the text out of the opaque-background HTML edge label."""
    m = re.search(r"<TD>(.*?)</TD>", label, re.S)
    text = m.group(1) if m else label
    text = re.sub(r"<FONT[^>]*>|</FONT>", "", text)
    return text.replace("<BR/>", "<br>").strip()


def _node_label(raw, is_html):
    """Normalise a Graphviz node label into draw.io HTML."""
    if is_html:
        text = re.sub(r'<FONT POINT-SIZE="(\d+)">', r'<font style="font-size:\1px">', raw)
        return text.replace("</FONT>", "</font>").replace("<BR/>", "<br>")
    return raw.replace("\\n", "<br>").replace("\\l", "<br>")


NODE_RE = re.compile(r'^\s*"([^"]+)"\s*\[(.*)\];\s*$')
EDGE_RE = re.compile(r'^\s*"([^"]+)"\s*->\s*"([^"]+)"\s*\[(.*)\];\s*$')


def parse_dot(dot_path):
    """Nodes and edges, with their labels and kinds, from a generated .dot file."""
    src = open(dot_path, encoding="utf-8").read()
    m = re.search(r"//\s*engine=(\w+)", src)
    engine = m.group(1) if m else "dot"

    nodes, kinds, edges = {}, {}, []
    for line in src.splitlines():
        em = EDGE_RE.match(line)
        if em:
            a, b, attrs = em.group(1), em.group(2), em.group(3)
            raw = _read_label(attrs)
            label = ""
            if raw:
                text, is_html = raw
                label = _table_text(text) if is_html else text
            edges.append((a, b, label, "onormal" in attrs))
            continue
        nm = NODE_RE.match(line)
        if not nm:
            continue
        name, attrs = nm.group(1), nm.group(2)
        raw = _read_label(attrs)
        if raw:
            text, is_html = raw
            nodes[name] = _node_label(text, is_html)
        # the kind is carried by the fill colour, not by the label text
        if IND_FILL.lower() in attrs.lower():
            kinds[name] = "individual"
        elif SUB_FILL.lower() in attrs.lower():
            kinds[name] = "focus"
        elif "rounded,filled,dashed" in attrs:
            kinds[name] = "defined"
        elif name not in kinds:
            kinds[name] = "class"
    return engine, nodes, kinds, edges


def layout(dot_path, engine):
    """Node centres and sizes, in inches, from the Graphviz layout."""
    out = subprocess.run([engine, "-Tplain", dot_path], capture_output=True, text=True, check=True).stdout
    positions, height = {}, 0.0
    for line in out.splitlines():
        tok = _split_plain(line)
        if not tok:
            continue
        if tok[0] == "graph":
            height = float(tok[3])
        elif tok[0] == "node":
            name = _unquote(tok[1])
            positions[name] = tuple(float(v) for v in tok[2:6])   # x, y, w, h
    return positions, height


def to_drawio(dot_path, out_path):
    engine, nodes, kinds, edges = parse_dot(dot_path)
    pos, gh = layout(dot_path, engine)

    cells = ['        <mxCell id="0" />',
             '        <mxCell id="1" parent="0" />']
    ids = {}
    for i, (name, label) in enumerate(sorted(nodes.items()), start=2):
        if name not in pos:
            continue
        x, y, w, h = pos[name]
        px, py = (x - w / 2) * INCH, (gh - y - h / 2) * INCH
        pw, ph = w * INCH, h * INCH
        kind = kinds.get(name, "class")
        style = {"defined": STYLE_DEFINED, "focus": STYLE_FOCUS,
                 "individual": STYLE_IND}.get(kind, STYLE_CLASS) % NODE_FS
        cid = "n%d" % i
        ids[name] = cid
        cells.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">\n'
            '          <mxGeometry x="%.1f" y="%.1f" width="%.1f" height="%.1f" as="geometry" />\n'
            '        </mxCell>' % (cid, html.escape(label, quote=True), style, px, py, pw, ph))

    import figure_palette as palette
    for j, (a, b, label, is_isa) in enumerate(edges):
        if a not in ids or b not in ids:
            continue
        style = (STYLE_ISA if is_isa else STYLE_EDGE) % EDGE_FS
        col = palette.colour(label) if not is_isa else palette.SUBCLASS
        style = re.sub(r"strokeColor=#[0-9A-Fa-f]{6}", "strokeColor=" + col, style)
        style = re.sub(r"fontColor=#[0-9A-Fa-f]{6}", "fontColor=" + col, style)
        cells.append(
            '        <mxCell id="e%d" value="%s" style="%s" edge="1" parent="1" source="%s" target="%s">\n'
            '          <mxGeometry relative="1" as="geometry" />\n'
            '        </mxCell>' % (j, html.escape(label, quote=True), style, ids[a], ids[b]))

    name = os.path.splitext(os.path.basename(out_path))[0]
    xml = ('<mxfile host="app.diagrams.net" type="device">\n'
           '  <diagram name="%s" id="%s">\n'
           '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" '
           'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="826" '
           'math="0" shadow="0">\n'
           '      <root>\n%s\n      </root>\n'
           '    </mxGraphModel>\n  </diagram>\n</mxfile>\n'
           % (name, name, "\n".join(cells)))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return out_path, len(ids), len(edges)


if __name__ == "__main__":
    import sys
    for path in sorted(sys.argv[1:]):
        target = path[:-4] + ".drawio"
        p, n, e = to_drawio(path, target)
        print("  %-52s %2d nodes, %2d edges" % (os.path.basename(p), n, e))
