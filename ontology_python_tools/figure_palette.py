"""
One colour per relationship type, shared by every CADO figure.

The same object property is drawn in the same colour in every diagram, so a
reader who learns a colour in one figure keeps it in the next. Colours are
grouped by family -- composition in blues, image lifecycle in oranges, storage
in teals, and so on -- but within a family each property still gets its own
value, because no figure shows more than nine relationship types at once.

`check_contrast()` verifies that the colours co-occurring in any one diagram are
far enough apart in CIE Lab to be told apart in print.
"""

SUBCLASS = "#001684"          # rdfs:subClassOf / is-a

PALETTE = {
    # -- taxonomy --------------------------------------------------
    "is-a":                            "#001684",
    "composedOf":                      "#3D5B99",
    "containsMinimalDeploymentUnit":   "#002D5B",
    # -- grouping and containment ----------------------------------
    "includesRunningInstance":         "#1A63AD",
    "groupedBy":                       "#1A32AD",
    "includesHost":                    "#993D99",
    "includesImage":                   "#1A94AD",
    # -- deployment ------------------------------------------------
    "deploys":                         "#1AAD32",
    "deployedBy":                      "#005B2D",
    "generatesGroupBy":                "#2D5B00",
    # -- image lifecycle -------------------------------------------
    "pullsImageFrom":                  "#AD941A",
    "unpacks":                         "#63AD1A",
    "convertsToContainer":             "#3D5B00",
    "runningInstanceOf":               "#996B3D",
    "savedTo":                         "#993D4C",
    # -- storage ---------------------------------------------------
    "binds":                           "#005B5B",
    "hasVolumeMount":                  "#1AAD94",
    "mountsStorage":                   "#008484",
    "reservesDiskSpaceOn":             "#1AAD7C",
    "generatesStorage":                "#1AADAD",
    # -- placement -------------------------------------------------
    "hostedBy":                        "#AD1AAD",
    "hosts":                           "#4C005B",
    # -- configuration and secrets ---------------------------------
    "hasEnvironmentVariable":          "#993D6B",
    "loginTo":                         "#840058",
    "generatesSecret":                 "#AD1A4B",
    # -- ordering --------------------------------------------------
    "dependsOn":                       "#840000",
    # -- utilisation -----------------------------------------------
    "utilizes":                        "#844200",
    "utilizedBy":                      "#99993D",
}

DEFAULT = "#37474F"


def normalise(label):
    """Map an edge label back to its property name.

    A trailing '*' marks a union domain and '(inferred)' marks a derived edge;
    neither changes which relationship the edge is.
    """
    return (label or "").replace(" (inferred)", "").strip().rstrip("*")


def colour(label):
    return PALETTE.get(normalise(label), DEFAULT)


# ---------------------------------------------------------------- contrast

def _lab(hex_colour):
    r, g, b = (int(hex_colour[i:i+2], 16) / 255.0 for i in (1, 3, 5))
    def lin(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    x = (0.4124*r + 0.3576*g + 0.1805*b) / 0.95047
    y = (0.2126*r + 0.7152*g + 0.0722*b)
    z = (0.0193*r + 0.1192*g + 0.9505*b) / 1.08883
    def f(t): return t ** (1/3) if t > 0.008856 else 7.787*t + 16/116
    fx, fy, fz = f(x), f(y), f(z)
    return 116*fy - 16, 500*(fx - fy), 200*(fy - fz)


def delta_e(a, b):
    la, aa, ba = _lab(a)
    lb, ab, bb = _lab(b)
    return ((la-lb)**2 + (aa-ab)**2 + (ba-bb)**2) ** 0.5


def check_contrast(groups, threshold=25.0):
    """groups: {figure: [labels]}. Returns pairs that are too close together."""
    problems = []
    for name, labels in groups.items():
        cols = sorted({normalise(l) for l in labels if normalise(l)})
        for i in range(len(cols)):
            for j in range(i+1, len(cols)):
                d = delta_e(colour(cols[i]), colour(cols[j]))
                if d < threshold:
                    problems.append((name, cols[i], cols[j], d))
    return problems
