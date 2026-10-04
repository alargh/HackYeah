"""Standalone: draws one overview image of the visual presets and core operations, step by step.

Only needs matplotlib:  pip install matplotlib  &&  python generate_presets_image.py [output_dir]
Writes <output_dir>/presets_overview.png (default output_dir: presentation-assets next to this file).
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc, Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

BG, CARD, EDGE = "#0e1220", "#161c2e", "#2a3350"
FG, MUTED = "#e8ecf4", "#8a93a8"
BLUE, YELLOW, GREEN, RED, PURPLE, ORANGE = "#58c4dd", "#f5c542", "#5ee0a0", "#ff6b6b", "#a78bfa", "#ff9f43"

W, H = 22.0, 17.2  # figure size in inches
fig = plt.figure(figsize=(W, H), facecolor=BG)


def axes_in(x, y_top, w, h):
    """Axes placed in inches, y measured from the top of the figure."""
    ax = fig.add_axes([x / W, 1 - (y_top + h) / H, w / W, h / H])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


# ----------------------------------------------------------------------------------------------- drawing helpers
def txt(ax, x, y, s, size=11, color=FG, **kw):
    ax.text(x, y, s, fontsize=size, color=color, ha=kw.pop("ha", "center"), va=kw.pop("va", "center"), **kw)


def dot(ax, x, y, label, color, r=0.085, size=11, ring=None):
    ax.add_patch(Circle((x, y), r, fc=color, ec="none", alpha=0.9))
    if ring:
        ax.add_patch(Circle((x, y), r + 0.035, fc="none", ec=ring, lw=2.2))
    txt(ax, x, y, label, size, BG, weight="bold")


def box(ax, x, y, w, h, label="", ec=BLUE, fc="none", size=11, color=FG, lw=1.8, ls="-", alpha=1.0):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.01,rounding_size=0.04",
                                fc=fc, ec=ec, lw=lw, ls=ls, alpha=alpha))
    if label:
        txt(ax, x, y, label, size, color, weight="bold")


def line(ax, pts, color=FG, lw=1.8, ls="-", alpha=1.0):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, alpha=alpha, solid_capstyle="round")


def arrow(ax, a, b, color=MUTED, lw=1.6, rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11, color=color, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}"))


def cross(ax, x, y, s=0.07, color=RED):
    line(ax, [(x - s, y - s), (x + s, y + s)], color, 2.2)
    line(ax, [(x - s, y + s), (x + s, y - s)], color, 2.2)


# simple oblique projection for the solids
def P(x, y, z, sx=0.5, sy=0.52, ox=0.14, oy=0.12):
    return (ox + sx * (x + 0.45 * y), oy + sy * (z + 0.3 * y))


PYR = {"A": (0, 0, 0), "B": (1, 0, 0), "C": (1, 1, 0), "D": (0, 1, 0), "S": (0.5, 0.5, 1.15), "O": (0.5, 0.5, 0)}


def pyramid(ax, edges_color=FG, labels=True, base_only=False, alpha=1.0, **proj):
    p = {k: P(*v, **proj) for k, v in PYR.items()}
    ax.add_patch(Polygon([p["A"], p["B"], p["C"], p["D"]], fc=BLUE, alpha=0.08 * alpha, ec="none"))
    front = [("A", "B"), ("B", "C")] + ([] if base_only else [("S", "A"), ("S", "B"), ("S", "C")])
    back = [("C", "D"), ("D", "A")] + ([] if base_only else [("S", "D")])
    for a, b in front:
        line(ax, [p[a], p[b]], edges_color, 1.6, alpha=alpha)
    for a, b in back:
        line(ax, [p[a], p[b]], edges_color, 1.1, "--", alpha=0.6 * alpha)
    if labels:
        for k, (dx, dy) in {"A": (-0.05, -0.04), "B": (0.03, -0.05), "C": (0.05, 0.0), "D": (-0.04, 0.03),
                            "S": (0.0, 0.05)}.items():
            if base_only and k == "S":
                continue
            txt(ax, p[k][0] + dx, p[k][1] + dy, k, 8, MUTED, style="italic")
    return p


# ----------------------------------------------------------------------------------------------- combinatorics
def arrangement_gallery(ax, s):
    if s == 0:
        for x, (l, c) in zip((0.25, 0.5, 0.75), (("A", BLUE), ("B", YELLOW), ("C", PURPLE))):
            dot(ax, x, 0.5, l, c)
        return
    perms = ["ABC", "ACB", "BAC", "BCA", "CAB", "CBA"]
    for i, w in enumerate(perms):
        x, y = 0.28 + 0.44 * (i % 2), 0.8 - 0.25 * (i // 2)
        bad = s == 2 and w[0] == "B"
        box(ax, x, y, 0.36, 0.17, w, ec=RED if bad else BLUE, size=9, alpha=0.5 if bad else 1)
        if bad:
            cross(ax, x, y, 0.06)
    if s == 2:
        txt(ax, 0.5, 0.08, "4 valid", 10, GREEN, weight="bold")


def permutation_counter(ax, s):
    fills = [["", "", ""], ["A", "", ""], ["A", "C", "B"]][s]
    for i, x in enumerate((0.22, 0.5, 0.78)):
        box(ax, x, 0.58, 0.2, 0.22, fills[i], ec=YELLOW if fills[i] else MUTED, ls="-" if fills[i] else "--")
        if s >= 1:
            txt(ax, x, 0.86, str(3 - i), 10, YELLOW)
    if s == 1:
        txt(ax, 0.5, 0.22, "choices per slot", 8.5, MUTED)
    if s == 2:
        txt(ax, 0.5, 0.2, r"$3\cdot 2\cdot 1=6$", 12, GREEN)


def block_method(ax, s):
    if s == 0:
        for x, l, c in ((0.16, "A", BLUE), (0.39, "B", YELLOW), (0.62, "C", PURPLE), (0.85, "D", ORANGE)):
            dot(ax, x, 0.55, l, c, r=0.075, ring=RED if l in "AB" else None)
        txt(ax, 0.5, 0.2, "A, B together", 8.5, RED)
    elif s == 1:
        box(ax, 0.27, 0.55, 0.38, 0.24, ec=GREEN, lw=2.2)
        dot(ax, 0.18, 0.55, "A", BLUE, r=0.065)
        dot(ax, 0.36, 0.55, "B", YELLOW, r=0.065)
        dot(ax, 0.62, 0.55, "C", PURPLE, r=0.075)
        dot(ax, 0.85, 0.55, "D", ORANGE, r=0.075)
        txt(ax, 0.5, 0.2, r"3 units $\to 3!$", 9.5, FG)
    else:
        box(ax, 0.22, 0.72, 0.3, 0.18, "AB", ec=GREEN, size=10)
        box(ax, 0.78, 0.72, 0.3, 0.18, "BA", ec=GREEN, size=10)
        txt(ax, 0.5, 0.72, r"$\leftrightarrow$", 12, MUTED)
        txt(ax, 0.5, 0.3, r"$3!\cdot 2=12$", 12, GREEN)


def case_split(ax, s):
    box(ax, 0.5, 0.82 if s else 0.5, 0.56, 0.2, "problem", ec=BLUE, size=10)
    if s >= 1:
        for x, lbl in ((0.25, "case 1"), (0.75, "case 2")):
            arrow(ax, (0.5, 0.71), (x, 0.5))
            box(ax, x, 0.4, 0.4, 0.17, lbl if s == 1 else ("6" if x < 0.5 else "4"), ec=PURPLE, size=9.5)
    if s == 2:
        txt(ax, 0.5, 0.12, r"$6+4=10$", 12, GREEN)


# ----------------------------------------------------------------------------------------------- solid geometry
def solid_reveal(ax, s):
    if s == 0:
        pyramid(ax, base_only=True)
    elif s == 1:
        pyramid(ax, alpha=0.75, labels=False)
        pyramid(ax, base_only=True, labels=True)
    else:  # turned: a second viewpoint
        pyramid(ax, sx=0.48, sy=0.55, ox=0.2)
        ax.add_patch(Arc((0.5, 0.08), 0.7, 0.12, theta1=200, theta2=340, color=MUTED, lw=1.4))
        arrow(ax, (0.79, 0.06), (0.84, 0.09), MUTED)


def space_construction(ax, s):
    p = pyramid(ax, edges_color=FG if s == 0 else "#9aa3b8")
    if s >= 1:
        line(ax, [p["S"], p["O"]], BLUE, 2.4)
        ax.add_patch(Circle(p["O"], 0.018, color=BLUE))
        txt(ax, p["O"][0] + 0.05, p["O"][1] - 0.04, "O", 8, BLUE, style="italic")
    if s == 2:
        line(ax, [p["O"], p["A"]], YELLOW, 2.4)
        line(ax, [p["S"], p["A"]], RED, 2.4)


def section_flatten(ax, s):
    if s < 2:
        p = pyramid(ax, sx=0.42 if s else 0.5, labels=s == 0)
        ax.add_patch(Polygon([p["S"], p["O"], p["A"]], fc=YELLOW, alpha=0.35, ec=YELLOW, lw=1.8))
        if s == 1:
            arrow(ax, (0.55, 0.45), (0.92, 0.45), YELLOW, 2)
            ax.add_patch(Polygon([(0.78, 0.6), (0.78, 0.3), (0.96, 0.3)], fc=YELLOW, alpha=0.25, ec=YELLOW, lw=1.4))
        return
    O, A, S = (0.25, 0.22), (0.8, 0.22), (0.25, 0.85)
    ax.add_patch(Polygon([S, O, A], fc=YELLOW, alpha=0.2, ec=YELLOW, lw=2))
    ax.add_patch(Rectangle(O, 0.06, 0.06, fc="none", ec=MUTED, lw=1.2))
    txt(ax, 0.17, 0.53, "4", 10, YELLOW)
    txt(ax, 0.52, 0.12, r"$3\sqrt{2}$", 10, YELLOW)
    txt(ax, 0.62, 0.6, r"$\sqrt{34}$", 10, GREEN)


def solid_of_revolution(ax, s):
    line(ax, [(0.38, 0.05), (0.38, 0.95)], MUTED, 1.2, "--")
    if s < 2:
        ax.add_patch(Polygon([(0.38, 0.82), (0.38, 0.22), (0.72, 0.22)], fc=BLUE, alpha=0.25, ec=BLUE, lw=2))
        if s == 1:
            ax.add_patch(Arc((0.38, 0.5), 0.5, 0.14, theta1=190, theta2=350, color=YELLOW, lw=2))
            arrow(ax, (0.6, 0.465), (0.63, 0.49), YELLOW, 2)
        return
    ax.add_patch(Polygon([(0.38, 0.82), (0.04, 0.22), (0.72, 0.22)], fc=BLUE, alpha=0.18, ec="none"))
    line(ax, [(0.04, 0.22), (0.38, 0.82), (0.72, 0.22)], BLUE, 2)
    ax.add_patch(Arc((0.38, 0.22), 0.68, 0.16, theta1=180, theta2=360, color=BLUE, lw=2))
    ax.add_patch(Arc((0.38, 0.22), 0.68, 0.16, theta1=0, theta2=180, color=BLUE, lw=1.2, ls="--"))
    txt(ax, 0.82, 0.6, "cone", 9.5, BLUE)


# ----------------------------------------------------------------------------------------------- core operations
def op_create(ax, s):
    ax.add_patch(Circle((0.5, 0.5), 0.2, fc=BLUE if s else "none", ec=BLUE, lw=2,
                        ls="--" if s == 0 else "-", alpha=[0.5, 0.45, 0.95][s]))
    if s == 2:
        txt(ax, 0.5, 0.5, "A", 14, BG, weight="bold")


def op_merge(ax, s):
    if s < 2:
        dx = 0.3 if s == 0 else 0.22
        dot(ax, 0.5 - dx, 0.5, "A", BLUE)
        dot(ax, 0.5 + dx, 0.5, "B", YELLOW)
        if s == 1:
            arrow(ax, (0.22, 0.25), (0.42, 0.38), GREEN)
            arrow(ax, (0.78, 0.25), (0.58, 0.38), GREEN)
        return
    box(ax, 0.5, 0.5, 0.6, 0.3, ec=GREEN, lw=2.2)
    dot(ax, 0.38, 0.5, "A", BLUE, r=0.075)
    dot(ax, 0.62, 0.5, "B", YELLOW, r=0.075)
    txt(ax, 0.5, 0.18, "[AB]", 10, GREEN, weight="bold")


def op_split(ax, s):
    if s == 0:
        box(ax, 0.5, 0.5, 0.5, 0.26, "[AB]", ec=GREEN, size=12)
        return
    box(ax, 0.5, 0.8, 0.36, 0.17, "[AB]", ec=GREEN, size=10, alpha=0.6 if s == 2 else 1)
    arrow(ax, (0.45, 0.7), (0.25, 0.45), PURPLE)
    arrow(ax, (0.55, 0.7), (0.75, 0.45), PURPLE)
    if s == 2:
        box(ax, 0.25, 0.32, 0.36, 0.18, "AB", ec=PURPLE, size=10)
        box(ax, 0.75, 0.32, 0.36, 0.18, "BA", ec=PURPLE, size=10)


def op_transform(ax, s):
    if s == 0:
        txt(ax, 0.5, 0.5, r"$\sqrt{16+18}$", 15, YELLOW)
    elif s == 1:
        txt(ax, 0.5, 0.68, r"$\sqrt{16+18}$", 12, YELLOW, alpha=0.4)
        arrow(ax, (0.5, 0.58), (0.5, 0.42), PURPLE)
        txt(ax, 0.5, 0.3, r"$\sqrt{34}$", 12, YELLOW, alpha=0.7)
    else:
        txt(ax, 0.5, 0.5, r"$\sqrt{34}$", 16, YELLOW)


def op_measure(ax, s):
    a, b = (0.15, 0.4), (0.85, 0.4)
    line(ax, [a, b], YELLOW if s else FG, 2.6 if s else 2)
    for x, l in ((a[0], "A"), (b[0], "B")):
        ax.add_patch(Circle((x, 0.4), 0.022, color=FG))
        txt(ax, x, 0.3, l, 9, MUTED, style="italic")
    if s >= 1:
        line(ax, [(0.15, 0.58), (0.85, 0.58)], MUTED, 1.2)
        line(ax, [(0.15, 0.53), (0.15, 0.63)], MUTED, 1.2)
        line(ax, [(0.85, 0.53), (0.85, 0.63)], MUTED, 1.2)
    if s == 2:
        txt(ax, 0.5, 0.74, "4", 14, YELLOW, weight="bold")


def op_enumerate(ax, s):
    pts = [(0.2, 0.75), (0.55, 0.82), (0.8, 0.6), (0.32, 0.45), (0.65, 0.35)]
    for i, (x, y) in enumerate(pts):
        dot(ax, x, y, str(i + 1) if s else "", [BLUE, YELLOW, PURPLE, ORANGE, GREEN][i], r=0.065, size=9)
    if s == 2:
        txt(ax, 0.5, 0.1, r"$n=5$", 13, GREEN)


def op_emphasize(ax, s):
    txt(ax, 0.5, 0.5, r"$x=12$", 16, GREEN if s == 2 else FG)
    if s == 1:
        line(ax, [(0.28, 0.36), (0.72, 0.36)], YELLOW, 2.4)
    if s == 2:
        box(ax, 0.5, 0.5, 0.62, 0.34, ec=GREEN, fc=GREEN, lw=2.4, alpha=0.15)
        box(ax, 0.5, 0.5, 0.62, 0.34, ec=GREEN, lw=2.4)


# ----------------------------------------------------------------------------------------------- layout
SECTIONS = [
    ("Combinatorics presets", BLUE, [
        ("arrangement_gallery", arrangement_gallery, "draw every arrangement, strike the forbidden ones, count the rest"),
        ("permutation_counter", permutation_counter, "fill slots one by one, multiply the choices"),
        ("block_method", block_method, "glue neighbours into a block, count units, then orders inside"),
        ("case_split", case_split, "split into disjoint cases, count each, add"),
    ]),
    ("Solid geometry presets", YELLOW, [
        ("solid_reveal", solid_reveal, "build the solid from its base, then turn it to show depth"),
        ("space_construction", space_construction, "add heights, centres and segments inside the solid"),
        ("section_flatten", section_flatten, "mark a cross-section, lift it out, compute on the flat shape"),
        ("solid_of_revolution", solid_of_revolution, "spin a plane figure around an axis into a solid"),
    ]),
    ("Core operations", GREEN, [
        ("create", op_create, "bring a new object on screen"),
        ("merge", op_merge, "group items into one block"),
        ("split", op_split, "open one thing into cases / orders"),
        ("transform", op_transform, "rewrite a formula into its next form"),
        ("measure", op_measure, "write the exact length / angle on the figure"),
        ("enumerate", op_enumerate, "number the items one by one to count them"),
        ("emphasize_result", op_emphasize, "frame the final answer"),
    ]),
]

MARGIN, GAP = 0.4, 0.3
CARD_W = (W - 2 * MARGIN - 3 * GAP) / 4
CARD_H, STEP = 3.05, 1.42


def card(x, y, name, fn, caption, accent):
    bg = axes_in(x, y, CARD_W, CARD_H)
    bg.add_patch(FancyBboxPatch((0.005, 0.005), 0.99, 0.99, boxstyle="round,pad=0,rounding_size=0.03",
                                fc=CARD, ec=EDGE, lw=1.2, transform=bg.transAxes))
    bg.text(0.05, 0.9, name, fontsize=14, color=accent, weight="bold", family="monospace", va="center")
    bg.text(0.05, 0.1, caption, fontsize=9.6, color=MUTED, va="center", wrap=True)
    pad = (CARD_W - 3 * STEP) / 4
    for i in range(3):
        sx = x + pad + i * (STEP + pad)
        bg.add_patch(Circle(((sx - x + 0.12) / CARD_W, 1 - 0.68 / CARD_H), 0.012 * CARD_H / CARD_W * 3,
                            fc=EDGE, ec="none", transform=bg.transAxes))
        bg.text((sx - x + 0.12) / CARD_W, 1 - 0.68 / CARD_H, str(i + 1), fontsize=8.5, color=FG, ha="center",
                va="center", weight="bold")
        if i:
            bg.text((sx - x - pad / 2) / CARD_W, 1 - (0.72 + STEP / 2) / CARD_H, "→", fontsize=15, color=MUTED,
                    ha="center", va="center")
        fn(axes_in(sx, y + 0.72, STEP, STEP), i)


y = 0.35
head = axes_in(MARGIN, y, W - 2 * MARGIN, 0.9)
head.text(0, 0.62, "Visual presets & operations", fontsize=26, color=FG, weight="bold", va="center")
head.text(0, 0.12, "each card reads left → right: the three steps the scene animates", fontsize=12.5, color=MUTED,
          va="center")
y += 1.15
for title, accent, cards in SECTIONS:
    sec = axes_in(MARGIN, y, W - 2 * MARGIN, 0.45)
    sec.add_patch(Rectangle((0, 0.2), 0.004, 0.6, color=accent, transform=sec.transAxes))
    sec.text(0.01, 0.5, title, fontsize=17, color=FG, weight="bold", va="center")
    y += 0.55
    for i, (name, fn, caption) in enumerate(cards):
        if i and i % 4 == 0:
            y += CARD_H + GAP
        card(MARGIN + (i % 4) * (CARD_W + GAP), y, name, fn, caption, accent)
    y += CARD_H + 0.45

out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "presentation-assets"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / "presets_overview.png"
fig.savefig(out, dpi=130, facecolor=BG)
print(f"saved {out}  (used {y:.1f} of {H} in)")
