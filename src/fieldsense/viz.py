"""Pictures for the demo. Each function returns a matplotlib Figure, so the notebook
can show it and save it (PNG for slides, SVG for the website)."""
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

# Brown (bare soil) -> pale -> deep green (dense crop). Missing days are drawn light grey.
BARCODE_CMAP = LinearSegmentedColormap.from_list(
    "barcode", ["#8c5a2b", "#d9c48c", "#c9dd8a", "#5aa040", "#1f6b2a"])
MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
MONTHS = "J F M A M J J A S O N D".split()


def plot_field_barcode(matrix, title="", labels=None, ax=None, vmin=0.1, vmax=0.9):
    """The field barcode: one stripe per year, colour = greenness on each day.

    matrix: years x 365 table from `phenology.barcode_matrix`
    labels: optional {year: text} drawn at the right of each stripe (e.g. the crop)
    """
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(11, 0.42 * len(matrix) + 1.2))
    else:
        fig = ax.figure
    cmap = BARCODE_CMAP.copy()
    cmap.set_bad("#e9e9e9")
    ax.imshow(np.ma.masked_invalid(matrix.values.astype(float)), aspect="auto", cmap=cmap,
              vmin=vmin, vmax=vmax, interpolation="nearest",
              extent=[0.5, 365.5, len(matrix) - 0.5, -0.5])
    ax.set_yticks(range(len(matrix)))
    ax.set_yticklabels(matrix.index)
    ax.set_xticks(MONTH_STARTS)
    ax.set_xticklabels(MONTHS)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    if labels:
        for i, y in enumerate(matrix.index):
            if y in labels:
                ax.text(370, i, labels[y], va="center", fontsize=8, color="#333")
    ax.set_title(title, loc="left", fontsize=11)
    if own:
        sm = plt.cm.ScalarMappable(cmap=BARCODE_CMAP, norm=plt.Normalize(vmin, vmax))
        cb = fig.colorbar(sm, ax=ax, fraction=0.025, pad=0.25 if labels else 0.02)
        cb.set_label("greenness (NDVI)")
        cb.outline.set_visible(False)
        fig.tight_layout()
    return fig


def plot_odds_icons(odds, ncols=3, color="#c0392b"):
    """Each risk as 100 squares, coloured squares = futures where it happens.

    People read "23 in 100" (a count of things) more accurately than "23%" or "p = 0.23";
    an icon array makes the count visible. Text below gives the matching count in real past years.
    """
    risks = odds["risks"]
    n = len(risks)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.6 * ncols, 4.6 * nrows))
    for ax, (name, r) in zip(np.ravel(axes), risks.items()):
        k = int(round(100 * r["share"]))
        for i in range(100):
            ax.add_patch(plt.Rectangle((i % 10, 9 - i // 10), 0.82, 0.82,
                                       color=color if i < k else "#e3e3e3", lw=0))
        ax.set_xlim(-0.2, 10); ax.set_ylim(-3.6, 10); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(f"{k} in 100", loc="left", fontsize=13, fontweight="bold")
        wrapped = "\n".join(_wrap(r["text"], 34))
        ax.text(0, -0.4, f"{wrapped}\npast years: {r['past_years']}", va="top", fontsize=8.5, color="#333")
    for ax in np.ravel(axes)[n:]:
        ax.axis("off")
    fig.suptitle(f"Next season ({odds['target_year']}): how often each risk happens across possible futures",
                 x=0.02, ha="left", fontsize=12)
    fig.tight_layout()
    return fig


def _wrap(text, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    return lines + [line]
